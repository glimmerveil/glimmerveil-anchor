#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sqlite3
import veil_spine as spine

FAILS = []
PASSES = []


def check(name, ok, detail=""):
    (PASSES if ok else FAILS).append((name, detail))
    mark = "ok " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if (detail and not ok) else ""))


def capture(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rv = fn()
    return rv, buf.getvalue()


def _live_pid():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    return p


def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _reset(db_path):
    for suffix in (".lock", ".folding"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass
    spine._LOCK_PATH = None


def main():
    tmp = tempfile.mkdtemp(prefix="veil_foldlock_")
    db_path = os.path.join(tmp, "veil.db")
    conn = sqlite3.connect(db_path)
    lock_path = db_path + ".lock"
    fold_path = db_path + ".folding"

    live = _live_pid()
    dead = _dead_pid()

    try:
        _reset(db_path)
        with open(lock_path, "w") as f:
            f.write(str(live.pid))
        rv, out = capture(lambda: spine._acquire_single_instance_lock(conn))
        check("A: live holder, not folding → refused", rv is False)
        check("A: prints the 'already running' line", "Another session is already running" in out, out.strip())
        check("A: offers the kill command", f"kill -TERM {live.pid}" in out and f"kill -9 {live.pid} ;" in out,
              out.strip())
        check("A: does NOT claim she's folding", "folding her memories" not in out, out.strip())

        _reset(db_path)
        with open(lock_path, "w") as f:
            f.write(str(live.pid))
        with open(fold_path, "w") as f:
            f.write(str(live.pid))
        rv, out = capture(lambda: spine._acquire_single_instance_lock(conn))
        check("B: folding holder → refused", rv is False)
        check("B: tells him she's folding", "folding her memories right now" in out, out.strip())
        check("B: does NOT offer a kill command", f"kill -TERM {live.pid}" not in out
              and f"kill -9 {live.pid}" not in out, out.strip())
        check("B: does NOT use the ghost 'already running' line", "Another session is already running" not in out, out.strip())
        check("B: the breadcrumb is left intact (fold still running)", os.path.exists(fold_path))

        _reset(db_path)
        with open(lock_path, "w") as f:
            f.write(str(live.pid))
        with open(fold_path, "w") as f:
            f.write(str(dead))
        rv, out = capture(lambda: spine._acquire_single_instance_lock(conn))
        check("C: mismatched flag → still refused", rv is False)
        check("C: mismatched flag → treated as NOT folding (kill advice)",
              f"kill -TERM {live.pid}" in out, out.strip())

        _reset(db_path)
        with open(lock_path, "w") as f:
            f.write(str(dead))
        with open(fold_path, "w") as f:
            f.write(str(dead))
        rv, out = capture(lambda: spine._acquire_single_instance_lock(conn))
        check("D: dead holder → reclaimed (True)", rv is True)
        with open(lock_path) as f:
            check("D: lock now held by us", f.read().strip() == str(os.getpid()))
        check("D: stale .folding flag cleared on reclaim", not os.path.exists(fold_path))
        spine._LOCK_PATH = None

        _reset(db_path)
        rv, _ = capture(lambda: spine._acquire_single_instance_lock(conn))
        check("F: a fresh wake takes the lock", rv is True and os.path.exists(lock_path))
        spine._release_single_instance_lock()
        check("F: goodbye removes our lock file", not os.path.exists(lock_path),
              "the lock survived goodbye — on Windows: removed while still open?")

        _reset(db_path)
        with open(lock_path, "w") as f:
            f.write(str(live.pid))
        spine._LOCK_PATH = lock_path
        spine._release_single_instance_lock()
        check("G: another session's lock is left alone", os.path.exists(lock_path))

        _reset(db_path)
        p = spine._mark_folding(conn)
        check("E: _mark_folding wrote the flag", bool(p) and os.path.exists(p))
        with open(p) as f:
            check("E: flag holds our pid", f.read().strip() == str(os.getpid()))
        spine._clear_folding(p)
        check("E: _clear_folding removed it", not os.path.exists(p))
        try:
            spine._clear_folding(p)
            spine._clear_folding(None)
            check("E: clearing a missing/None flag is a no-op", True)
        except Exception as e:
            check("E: clearing a missing/None flag is a no-op", False, repr(e))

    finally:
        live.terminate()
        try:
            live.wait(timeout=5)
        except Exception:
            live.kill()
        conn.close()
        _reset(db_path)

    print()
    print(f"  {len(PASSES)} passed, {len(FAILS)} failed")
    if FAILS:
        print("\nFAILURES:")
        for name, detail in FAILS:
            print(f"  - {name}: {detail}")
        sys.exit(1)
    print("  the mid-fold door holds — no one is told to kill her through a fold.")


if __name__ == "__main__":
    main()
