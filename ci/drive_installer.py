#!/usr/bin/env python3
# The installer, proven on a throwaway Windows runner: install silently (per-user, no admin) -> drive the
# first night through the INSTALLED Anchor.bat (ci/drive_e2e.py) -> install again over it (an upgrade) ->
# uninstall silently -> her folder and models\ must be exactly as they were, the program files gone.
# CI only: it installs and uninstalls on this machine and puts a test companion in the real profile.
import hashlib
import os
import shutil
import subprocess
import sys
import time
import winreg

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO, "dist", "GlimmerveilAnchor")
SCRATCH = os.environ.get("ANCHOR_DRIVE_SCRATCH") or os.path.join(REPO, "ci", ".scratch_drive")
APPID = "{B1C098F0-9733-46F2-8CFB-E2F55EA3EA99}_is1"
UNINST_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APPID
APP = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Glimmerveil Anchor")
LNK = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs",
                   "Glimmerveil Anchor.lnk")
HER_HOME = os.path.join(os.environ.get("USERPROFILE", ""), "anchor")
CANARY = os.path.join(APP, "models", "my-own-brain-notes.txt")
STEPS = []


def ok(what, detail=""):
    STEPS.append("ok   %-52s %s" % (what, detail))
    print(STEPS[-1], flush=True)


def fail(what):
    STEPS.append("FAIL " + what)
    print("\n".join(STEPS))
    raise SystemExit("FAIL " + what)


def tree(root):
    out = {}
    for d, _, files in os.walk(root):
        for n in files:
            p = os.path.join(d, n)
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[os.path.relpath(p, root)] = h.hexdigest()
    return out


def manifest():
    out = ["anchor.ico"]
    for d, _, files in os.walk(SOURCE):
        for n in files:
            rel = os.path.relpath(os.path.join(d, n), SOURCE)
            if not rel.lower().startswith("models" + os.sep):
                out.append(rel)
    return out


def uninst_entry():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINST_KEY) as k:
            return {n: winreg.QueryValueEx(k, n)[0] for n in ("UninstallString", "InstallLocation", "DisplayName")}
    except OSError:
        return None


def install(setup, what, extra):
    log = os.path.join(REPO, "dist", "setup-%d.log" % len(STEPS))
    argv = [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CURRENTUSER", "/NORESTART", "/LOG=" + log] + extra
    t0 = time.time()
    rc = subprocess.run(argv, timeout=900).returncode
    if rc != 0:
        if os.path.isfile(log):
            print(open(log, encoding="utf-8", errors="replace").read()[-4000:])
        fail("%s: setup exit code %d" % (what, rc))
    ok(what, "%.0fs" % (time.time() - t0))


def shortcut():
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); "
          "$s.TargetPath; $s.WorkingDirectory; $s.IconLocation" % LNK)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return [x.strip() for x in r.stdout.splitlines()]


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("refusing: this installs and uninstalls Anchor on this machine — CI runners only")
    setup = os.path.abspath(sys.argv[1])
    if os.path.exists(HER_HOME):
        raise SystemExit("refusing: %s already exists — never write over a real companion" % HER_HOME)
    if os.path.exists(APP) or uninst_entry():
        raise SystemExit("refusing: Anchor is already installed here (%s)" % APP)
    files = manifest()
    print("installer %s · %d program files expected · default dir %s" % (setup, len(files), APP))

    # 1 · a stranger's install: no /DIR, so the default dir is what the .iss says it is
    install(setup, "install: silent, per-user, default dir", [])
    missing = [f for f in files if not os.path.isfile(os.path.join(APP, f))]
    if missing:
        fail("install: %d program file(s) missing, e.g. %s" % (len(missing), missing[:5]))
    ok("install: every program file is in place", "%d files" % len(files))
    e = uninst_entry()
    if not e or os.path.normcase(e["InstallLocation"].rstrip("\\")) != os.path.normcase(APP):
        fail("install: Apps & Features entry missing or wrong: %r" % (e,))
    ok("install: listed in Apps & Features (HKCU)", e["DisplayName"])
    target, workdir, icon = (shortcut() + ["", "", ""])[:3]
    if (os.path.normcase(target) != os.path.normcase(os.path.join(APP, "Anchor.bat"))
            or os.path.normcase(workdir) != os.path.normcase(APP) or "anchor.ico" not in icon.lower()):
        fail("install: Start-menu shortcut wrong: target %r, dir %r, icon %r" % (target, workdir, icon))
    ok("install: Start-menu shortcut -> Anchor.bat, in the app dir", icon)

    # 2 · her first night, through the installed copy
    with open(CANARY, "w", encoding="utf-8") as f:
        f.write("the user's own file in models\\ — the uninstaller must never touch it\n")
    env = dict(os.environ, ANCHOR_DRIVE_PACKAGE=APP)
    if subprocess.run([sys.executable, os.path.join(REPO, "ci", "drive_e2e.py")], env=env).returncode != 0:
        fail("drive: the first night through the installed Anchor.bat")
    ok("drive: a first night through the installed Anchor.bat")

    # her folder, where a real user's lives: the runner's own %USERPROFILE%\anchor\peeps
    peeps = os.path.join(SCRATCH, "home", "anchor", "peeps")
    shutil.copytree(peeps, os.path.join(HER_HOME, "peeps"))
    her = {"real": (os.path.join(HER_HOME, "peeps"), tree(os.path.join(HER_HOME, "peeps"))),
           "drive": (peeps, tree(peeps))}
    models = tree(os.path.join(APP, "models"))
    if not any(n.endswith(".gguf") for n in models) or os.path.basename(CANARY) not in models:
        fail("drive: models\\ should hold the toy brain and the canary, holds %s" % sorted(models))
    ok("her: folder in %USERPROFILE%\\anchor\\peeps", "%d files: %s" % (len(her["real"][1]), sorted(her["real"][1])))
    ok("models\\ holds", str(sorted(models)))

    def intact(when):
        for name, (root, before) in her.items():
            now = tree(root) if os.path.isdir(root) else {}
            if now != before:
                fail("%s: her folder (%s, %s) changed: missing %s, altered %s" % (
                    when, name, root, sorted(set(before) - set(now)),
                    sorted(k for k in before if k in now and now[k] != before[k])))
        now = tree(os.path.join(APP, "models")) if os.path.isdir(os.path.join(APP, "models")) else {}
        lost = sorted(k for k in models if now.get(k) != models[k])
        if lost:
            fail("%s: models\\ lost or changed %s" % (when, lost))
        ok("%s: her folder and models\\ are byte-for-byte as they were" % when)

    # 3 · an upgrade: a newer installer over the old one, the documented command line
    install(setup, "upgrade: install again over it, /DIR=", ["/DIR=" + APP])
    intact("upgrade")

    # 4 · uninstall
    e = uninst_entry()
    if not e:
        fail("uninstall: no Apps & Features entry to uninstall from")
    unins = e["UninstallString"].strip('"')
    t0 = time.time()
    rc = subprocess.run([unins, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=900).returncode
    while (uninst_entry() or os.path.exists(unins)) and time.time() - t0 < 300:
        time.sleep(1)  # the uninstaller hands over to a copy of itself in %TEMP%; wait for that one
    if rc != 0:
        fail("uninstall: exit code %d" % rc)
    ok("uninstall: silent", "%.0fs" % (time.time() - t0))
    intact("uninstall")

    left = [f for f in files if os.path.exists(os.path.join(APP, f))]
    if left:
        fail("uninstall: %d program file(s) left behind, e.g. %s" % (len(left), left[:5]))
    if uninst_entry() or os.path.exists(unins) or os.path.exists(LNK):
        fail("uninstall: still listed / uninstaller still there / shortcut still there")
    ok("uninstall: every program file, the shortcut and the listing are gone")
    rest = sorted(os.path.relpath(os.path.join(d, n), APP) for d, _, fs in os.walk(APP) for n in fs) \
        if os.path.isdir(APP) else []
    other = [r for r in rest if not r.lower().startswith("models" + os.sep) and "__pycache__" not in r]
    if other:
        fail("uninstall: left something that is neither models\\ nor Python's own cache: %s" % other[:10])
    ok("uninstall: what stays in the app dir is models\\ + Python's bytecode cache",
       "%d models file(s), %d cache file(s)" % (len(rest) - len([r for r in rest if "__pycache__" in r]),
                                                len([r for r in rest if "__pycache__" in r])))

    print("\n" + "\n".join(STEPS))
    print("PASS install -> first night -> upgrade -> uninstall, and her folder survived")
    return 0


if __name__ == "__main__":
    sys.exit(main())
