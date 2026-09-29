#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = tempfile.mkdtemp(prefix="veil_place_test_")
PLACE = os.path.join(SANDBOX, "place")

PASS, FAIL = 0, []


def ok(name, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print(f"  FAIL {name}")


def session(code):
    env = dict(os.environ, VEIL_PLACE=PLACE, VEIL_HEARTBEAT=os.path.join(SANDBOX, "hb"))
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, %r)\nimport veil_tick as V\n%s" % (HERE, code)],
                       capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        print(r.stderr[-800:])
    return r.stdout.strip()


ok("first wake ever → garden", session("print(V._place())").endswith("garden"))

session("V._go_to('study')")
ok("the move was written down", open(PLACE).read().strip() == "study")
ok("next wake → the study (no more sunrise reset)", session("print(V._place())").endswith("study"))
ok("and again, a session later", session("print(V._place())").endswith("study"))

with open(PLACE, "w") as fh:
    fh.write("the moon\n")
ok("an unknown room falls back to the garden, never crashes",
   session("print(V._place())").endswith("garden"))

with open(PLACE, "w") as fh:
    fh.write("bedroom\n")
out = session("V._go_to('narnia'); print(V._place())")
ok("a fake room is refused", out.endswith("bedroom") and open(PLACE).read().strip() == "bedroom")

ok("patience defaults to 300s (5 min)", session("print(V.PATIENCE_SECONDS)").endswith("300.0"))
env_out = subprocess.run([sys.executable, "-c",
                          "import sys; sys.path.insert(0, %r)\nimport veil_tick as V\nprint(V.PATIENCE_SECONDS)" % HERE],
                         capture_output=True, text=True, timeout=120,
                         env=dict(os.environ, VEIL_PLACE=PLACE, VEIL_PATIENCE_SECONDS="42",
                                  VEIL_HEARTBEAT=os.path.join(SANDBOX, "hb"))).stdout.strip()
ok("env override still rules the hold", env_out.endswith("42.0"))

import shutil
shutil.rmtree(SANDBOX, ignore_errors=True)
print()
if FAIL:
    print(f"FAIL — {len(FAIL)} of {PASS + len(FAIL)}")
    sys.exit(1)
print(f"ALL PASS — {PASS}/{PASS} · she wakes where she was, and her life fires in minutes not never")
