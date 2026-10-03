#!/usr/bin/env python3
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRATCH = os.environ.get("ANCHOR_DRIVE_SCRATCH") or os.path.join(REPO, "ci", ".scratch_drive")
IS_WIN = sys.platform.startswith("win")

HIS_LINE = "Hello Wren, it is Tester. Are you there with me tonight?"
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]")


def clean(s):
    return ANSI.sub("", s).replace("\r", "")


class Console:

    def __init__(self, argv, env, cwd):
        self.raw = []
        self.q = queue.Queue()
        self.done = threading.Event()
        self.exitcode = None
        if IS_WIN:
            from winpty import PtyProcess
            self.p = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(40, 140))
            threading.Thread(target=self._pump_win, daemon=True).start()
        else:
            import pty
            pid, fd = pty.fork()
            if pid == 0:
                os.chdir(cwd)
                os.execvpe(argv[0], argv, env)
            self.pid, self.fd = pid, fd
            threading.Thread(target=self._pump_posix, daemon=True).start()

    def _pump_win(self):
        while True:
            try:
                s = self.p.read(4096)
            except EOFError:
                break
            except Exception:
                if not self.p.isalive():
                    break
                time.sleep(0.05)
                continue
            if s:
                if "\x1b[6n" in s:
                    try:
                        self.p.write("\x1b[1;1R")
                    except Exception:
                        pass
                self.q.put(s)
        self.done.set()

    def _pump_posix(self):
        while True:
            try:
                b = os.read(self.fd, 4096)
            except OSError:
                break
            if not b:
                break
            self.q.put(b.decode("utf-8", "replace"))
        self.done.set()

    def drain(self):
        got = False
        while True:
            try:
                self.raw.append(self.q.get_nowait())
                got = True
            except queue.Empty:
                return got

    def text(self):
        return clean("".join(self.raw))

    def send(self, s):
        s = s + "\r"
        if IS_WIN:
            self.p.write(s)
        else:
            os.write(self.fd, s.encode("utf-8"))

    def alive(self):
        if IS_WIN:
            return self.p.isalive()
        if self.exitcode is not None:
            return False
        pid, status = os.waitpid(self.pid, os.WNOHANG)
        if pid == 0:
            return True
        self.exitcode = os.waitstatus_to_exitcode(status)
        return False

    def wait_exit(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.drain()
            if not self.alive():
                self.drain()
                if IS_WIN:
                    self.exitcode = self.p.exitstatus
                return self.exitcode
            time.sleep(0.2)
        return None

    def kill(self):
        try:
            if IS_WIN:
                self.p.terminate(force=True)
            else:
                os.kill(self.pid, 9)
        except Exception:
            pass


class Drive:
    def __init__(self, con):
        self.con = con
        self.cursor = 0
        self.steps = []

    def expect(self, needles, timeout, what):
        if isinstance(needles, str):
            needles = [needles]
        end = time.time() + timeout
        t0 = time.time()
        while True:
            self.con.drain()
            t = self.con.text()
            new = t[self.cursor:]
            hits = [(new.find(n), n) for n in needles if n in new]
            if hits:
                pos, n = min(hits)
                self.cursor += pos + len(n)
                self.steps.append("ok   %-44s %5.1fs  [%s]" % (what, time.time() - t0, n))
                return n
            if time.time() > end or (not self.con.alive() and self.con.q.empty()):
                why = "timeout %ds" % timeout if time.time() > end else "the program EXITED"
                self.steps.append("FAIL %-44s %s waiting for %r" % (what, why, needles))
                raise RuntimeError("step '%s': %s" % (what, why))
            time.sleep(0.1)

    def quiet(self, secs, ceiling, what):
        t0 = time.time()
        last = time.time()
        while time.time() - t0 < ceiling:
            if self.con.drain():
                last = time.time()
            if time.time() - last >= secs:
                self.steps.append("ok   %-44s %5.1fs  [quiet %ds]" % (what, time.time() - t0, secs))
                return
            if not self.con.alive():
                break
            time.sleep(0.2)
        self.steps.append("FAIL %-44s never went quiet in %ds" % (what, ceiling))
        raise RuntimeError("step '%s': never went quiet" % what)

    def type(self, s):
        self.con.send(s)


def walk(d):
    d.expect("create your companion", 120, "door: first run")
    d.type("c")
    d.expect("Your companion's name:", 30, "wizard: her name")
    d.type("Wren")
    d.expect("pronouns (she/her", 30, "wizard: her pronouns")
    d.type("")
    d.expect("Your name:", 30, "wizard: your name")
    d.type("Tester")
    d.expect("Your pronouns", 30, "wizard: your pronouns")
    d.type("")
    d.expect("What are you to", 30, "wizard: partner word")
    d.type("")
    d.expect("something to stand on", 30, "wizard: who she is")
    d.type("Wren is a quiet, curious librarian who loves rain on windows, old maps and "
           "strong tea, and teases gently when she is happy.")
    d.expect("look?", 30, "wizard: appearance")
    d.type("Dark hair, grey eyes, ink on her fingers.")
    d.expect("is a fine answer", 30, "wizard: wardrobe")
    d.type("a wool cardigan")
    d.expect("already knowing it", 30, "wizard: how we met")
    d.type("We met in the reading room of an old library during a thunderstorm.")
    d.expect("[y/N]:", 30, "wizard: AI-aware")
    d.type("")
    d.expect("warm or precise", 30, "wizard: register")
    d.type("")
    d.expect("personable or accurate", 30, "wizard: recall")
    d.type("")
    d.expect("[y/N]:", 30, "wizard: autonomy")
    d.type("")
    d.expect("Home [manor]:", 30, "wizard: home")
    d.type("")
    d.expect("Type YES to confirm", 30, "wizard: adults-in-the-story attestation")
    d.type("YES")
    n = d.expect(["Voice [Enter", "Enter to go back to the door"], 60, "wizard: voice step or done")
    if n == "Voice [Enter":
        d.type("")
        d.expect("Enter to go back to the door", 60, "wizard: done, she lives")
    d.type("")

    d.expect("wake her", 60, "door: she is on the roster")
    d.type("w")
    ready = ["text mode; type your message", "voice on; speak now"]
    asked = 0
    while True:
        mode = d.expect(ready + ["[Enter]"], 900,
                        "tick: ready" if asked == 0 else "tick: ritual answered (%d)" % asked)
        if mode != "[Enter]":
            break
        asked += 1
        if asked > 10:
            raise RuntimeError("the anchor ritual asked more than 10 times — it never ends")
        d.type("")
    d.steps.append("ok   %-44s        [%d ritual question(s) asked]" % ("tick: first-wake ritual", asked))
    if mode == "voice on; speak now":
        d.type("")
        d.expect("[voice OFF", 120, "tick: blank Enter -> text only")

    d.quiet(3, 60, "tick: settled before his line")
    d.type(HIS_LINE)
    d.expect("Wren:", 900, "tick: her reply header")
    d.quiet(10, 900, "tick: she finished")

    d.type("goodbye")
    d.expect("wake her", 900, "goodbye: she slept, the door is back")
    d.type("q")


def census(peeps):
    out, bad = [], []
    folders = [f for f in (os.listdir(peeps) if os.path.isdir(peeps) else [])
               if os.path.isdir(os.path.join(peeps, f))]
    out.append("peeps dir %s -> %d folder(s): %s" % (peeps, len(folders), folders))
    if len(folders) != 1:
        bad.append("expected exactly one peep folder, found %d" % len(folders))
        return out, bad
    fp = os.path.join(peeps, folders[0])
    files = sorted(os.listdir(fp))
    out.append("her folder holds: %s" % files)
    if "card.json" not in files:
        bad.append("no card.json in her folder")
    dbs = [f for f in files if f.endswith(".db")]
    if len(dbs) != 1:
        bad.append("expected one .db in her folder, found %s" % dbs)
        return out, bad
    db = os.path.join(fp, dbs[0])
    if os.path.exists(db + ".lock"):
        bad.append("goodbye did NOT release the lock: %s.lock still exists" % dbs[0])
    else:
        out.append("lock released: %s.lock absent" % dbs[0])
    c = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    try:
        rows = c.execute("SELECT id, content FROM memory_stream ORDER BY id").fetchall()
        diary = c.execute("SELECT COUNT(*) FROM diary").fetchone()[0]
    finally:
        c.close()
    his = [r[0] for r in rows if HIS_LINE in (r[1] or "")]
    out.append("memory_stream rows %d · his line in %d row(s) · diary rows %d" % (len(rows), len(his), diary))
    if not his:
        bad.append("his typed line never reached her memory — she did not HEAR it")
    else:
        after = [r for r in rows if r[0] > his[0]]
        out.append("rows after his line: %d" % len(after))
        for r in after[:3]:
            out.append("   #%d %r" % (r[0], (r[1] or "")[:160]))
        if not after:
            bad.append("no row after his line — she never answered")
    if diary < 1:
        bad.append("goodbye wrote no diary page")
    return out, bad


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if IS_WIN:
        try:
            import winpty
        except ImportError:
            print("FAIL pywinpty is not installed — the drive needs ConPTY on Windows")
            return 1
    sys.path.insert(0, os.path.join(REPO, "ci"))
    import smoke_tiny_gguf
    real = os.environ.get("ANCHOR_DRIVE_MODEL")
    if real:
        smoke_tiny_gguf.PATH = real
    else:
        smoke_tiny_gguf.fetch()

    shutil.rmtree(SCRATCH, ignore_errors=True)
    home = os.path.join(SCRATCH, "home")
    os.makedirs(home)
    env = dict(os.environ)
    for k in ("VEIL_DATA", "VEIL_PEEPS", "VEIL_DB", "VEIL_HISTORY", "VEIL_CARD_JSON",
              "VEIL_VOICE", "VEIL_SKIP_LEGAL"):
        env.pop(k, None)
    env.update({
        "HOME": home, "USERPROFILE": home,
        "LOCALAPPDATA": os.path.join(home, "AppData", "Local"),
        "APPDATA": os.path.join(home, "AppData", "Roaming"),
        "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
        "VEIL_MODEL": smoke_tiny_gguf.PATH,
        "VEIL_GPU_LAYERS": "0",
        "TERM": env.get("TERM", "xterm-256color"),
    })
    for k in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME"):
        os.makedirs(env[k], exist_ok=True)

    argv = [sys.executable, os.path.join(SRC, "veil_game.py")]
    package = os.environ.get("ANCHOR_DRIVE_PACKAGE")
    if package:
        models = os.path.join(package, "models")
        os.makedirs(models, exist_ok=True)
        for n in os.listdir(models):
            if n.endswith(".gguf") or n == "MODEL_PATH.txt":
                os.remove(os.path.join(models, n))
        if os.environ.get("ANCHOR_DRIVE_BRAIN"):
            brain = os.path.join(package, "brain")
            os.makedirs(brain, exist_ok=True)
            if not os.path.isfile(os.path.join(brain, "brain.gguf")):
                shutil.copy2(smoke_tiny_gguf.PATH, os.path.join(brain, "brain.gguf"))
        else:
            shutil.copy2(smoke_tiny_gguf.PATH, models)
        env.pop("VEIL_MODEL", None)
        for k in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            env.pop(k, None)
        launcher = os.environ.get("ANCHOR_DRIVE_LAUNCHER", "Anchor.bat")
        argv = (["cmd.exe", "/c", os.path.join(package, launcher)] if IS_WIN
                else [os.path.join(package, "python", "python.exe")])
    print("drive: %s on %s  (%s)" % (" ".join(argv), sys.platform, "ConPTY" if IS_WIN else "pty"))
    t0 = time.time()
    con = Console(argv, env, REPO)
    d = Drive(con)
    err = None
    try:
        walk(d)
        code = con.wait_exit(60)
        if code is None:
            err = "the door did not exit within 60s of 'q'"
    except Exception as e:
        err = str(e)
        code = None
    finally:
        if con.alive():
            con.kill()
        con.drain()
        with open(os.path.join(SCRATCH, "transcript.txt"), "w", encoding="utf-8") as f:
            f.write(con.text())

    print("\n".join(d.steps))
    print("walk: %.0fs · door exit code %s" % (time.time() - t0, code))
    peeps = os.path.join(home, "anchor", "peeps")
    lines, bad = census(peeps)
    print("\n".join(lines))
    if err:
        bad.insert(0, err)
    if code not in (0, None) or (code is None and not err):
        bad.append("door exit code %s" % code)
    tail = con.text()[-3000:]
    if bad:
        print("\n---- last 3000 chars of the console (ANSI stripped) ----\n" + tail)
        print("----")
        for b in bad:
            print("FAIL " + b)
        return 1
    print("PASS a stranger's first night, end to end, typed into a real console on %s" % sys.platform)
    return 0


if __name__ == "__main__":
    sys.exit(main())
