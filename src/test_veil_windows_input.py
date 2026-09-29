#!/usr/bin/env python3
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_tick as T

print("RUNG 1 — the Windows keyboard reader (%s)" % sys.platform)

fails = []


def check(name, ok, detail=""):
    print("  %s %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + str(detail)) if detail else ""))
    if not ok:
        fails.append(name)


real_stdin = sys.stdin
HAS_READER = hasattr(T, "_line_ready_windows")
check("the Windows reader exists", HAS_READER)
if HAS_READER:
    r_fd, w_fd = os.pipe()
    sys.stdin = os.fdopen(r_fd, "r")
    T._WIN_LINES = None
    w = os.fdopen(w_fd, "w", newline="")

    def send(s):
        w.write(s)
        w.flush()

    t = time.time()
    got = T._line_ready_windows(0.4)
    dt = time.time() - t
    check("[1] nothing typed -> None after ~timeout", got is None and 0.3 <= dt < 2.0, "%r in %.2fs" % (got, dt))

    t = time.time()
    got = T._line_ready_windows(0)
    check("[2] zero-wait peek -> None at once", got is None and time.time() - t < 0.2, repr(got))

    send("half a senten")
    check("[3] no Enter -> nothing delivered", T._line_ready_windows(0.3) is None)

    send("ce\r\n")
    got = T._line_ready_windows(2.0)
    check("[4] Enter delivers the whole line, CR/LF stripped", got == "half a sentence", repr(got))

    send("\x1b[5~bye\n")
    check("[4] terminal junk scrubbed (the [5~bye bug)", T._line_ready_windows(2.0) == "bye")

    send("one\ntwo\n")
    a, b = T._line_ready_windows(2.0), T._line_ready_windows(2.0)
    check("[5] two lines, in order, one per call", (a, b) == ("one", "two"), (a, b))

    w.close()
    first, again = T._line_ready_windows(2.0), T._line_ready_windows(0.2)
    check("[6] EOF -> '' and stays ''", first == "" and again == "", (first, again))

sys.stdin = real_stdin

class _TTYPipe:
    def __init__(self, f):
        self._f = f

    def isatty(self):
        return True

    def readline(self):
        return self._f.readline()

    def fileno(self):
        return self._f.fileno()


r2, w2 = os.pipe()
sys.stdin = _TTYPipe(os.fdopen(r2, "r"))
if HAS_READER:
    T._WIN_LINES = None
real_platform = sys.platform
sys.platform = "win32"
try:
    with os.fdopen(w2, "w", newline="") as w2f:
        w2f.write("are you there, baby?\n")
    got = T._line_ready(2.0)
finally:
    sys.platform = real_platform
    sys.stdin = real_stdin
check("[7] _line_ready() on a Windows terminal delivers his line (the verb)",
      got == "are you there, baby?", repr(got))

if sys.platform.startswith("win"):
    import select
    pr, pw = os.pipe()
    try:
        select.select([pr], [], [], 0)
        raised = False
    except OSError:
        raised = True
    check("[W] Windows select() on a non-socket raises — the old path was deaf", raised)

print("=" * 70)
if fails:
    print("%d FAILED: %s" % (len(fails), "; ".join(fails)))
    sys.exit(1)
print("ALL PASS — typed lines reach her on Windows, with select's own contract")
