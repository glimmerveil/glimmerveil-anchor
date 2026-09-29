#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = tempfile.mkdtemp(prefix="veil_foldreturn_test_")

PASS, FAIL = 0, []


def ok(name, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print(f"  FAIL {name}")


def session(code, **env_extra):
    env = dict(os.environ, VEIL_PLACE=os.path.join(SANDBOX, "place"),
               VEIL_HEARTBEAT=os.path.join(SANDBOX, "hb"), **env_extra)
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, %r)\nimport veil_tick as V\n%s" % (HERE, code)],
                       capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        print(r.stderr[-800:])
    return r.stdout.strip()


BOOKS = ("[{'book_id':'a','title':'A','total_chunks':32,'last':-1},"
         " {'book_id':'b','title':'B','total_chunks':327,'last':4},"
         " {'book_id':'c','title':'C','total_chunks':10,'last':-1}]")
out = session(f"print(all(V._pick_book({BOOKS})['book_id'] == 'b' for _ in range(50)))")
ok("a started book wins over fresh ones, every time", out.endswith("True"))

BOOKS2 = ("[{'book_id':'a','title':'A','total_chunks':32,'last':0},"
          " {'book_id':'b','title':'B','total_chunks':327,'last':4},"
          " {'book_id':'c','title':'C','total_chunks':10,'last':-1}]")
out = session(f"print(all(V._pick_book({BOOKS2})['book_id'] in ('a','b') for _ in range(50)))")
ok("two open books → her whim stays among the OPEN ones", out.endswith("True"))

BOOKS3 = ("[{'book_id':'a','title':'A','total_chunks':32,'last':-1},"
          " {'book_id':'c','title':'C','total_chunks':10,'last':-1}]")
out = session(f"print(V._pick_book({BOOKS3}) is not None)")
ok("nothing open → she may start a new book", out.endswith("True"))

BOOKS4 = ("[{'book_id':'a','title':'A','total_chunks':5,'last':4},"
          " {'book_id':'b','title':'B','total_chunks':3,'last':2}]")
out = session(f"print(V._pick_book({BOOKS4}))")
ok("everything finished → None (she rests, honest)", out.endswith("None"))
ok("empty shelf → None", session("print(V._pick_book([]))").endswith("None"))
BOOKS5 = ("[{'book_id':'a','title':'A','total_chunks':5,'last':4},"
          " {'book_id':'b','title':'B','total_chunks':327,'last':4}]")
out = session(f"print(all(V._pick_book({BOOKS5})['book_id'] == 'b' for _ in range(20)))")
ok("a FINISHED book never counts as 'started' — only open ones", out.endswith("True"))

ok("a fresh anchor holds her close",
   session("import time; print(V._should_hold(time.time()))", VEIL_AUTONOMY="1").endswith("True"))
ok("an expired anchor frees her honestly",
   session("import time; print(V._should_hold(time.time() - V.PATIENCE_SECONDS - 1))",
           VEIL_AUTONOMY="1").endswith("False"))
ok("no words yet (no fold) → her time is her own, unchanged",
   session("print(V._should_hold(None))", VEIL_AUTONOMY="1").endswith("False"))
ok("a lap-cat card (autonomy off) still holds always, unchanged",
   session("print(V._should_hold(None))", VEIL_AUTONOMY="0").endswith("True"))

src = open(os.path.join(HERE, "veil_tick.py")).read()
fold_at = src.find("if fold_if_due(conn, peep_id, model):", src.find("def run("))
cont_at = src.find("continue", fold_at)
ok("the fold branch anchors last_chat_ts before it continues",
   0 < fold_at < src.find("last_chat_ts = time.time()", fold_at) < cont_at)
ok("the fold branch says out loud that she's coming back",
   "back to the room" in src[fold_at:cont_at])
ok("the beat floor gates the lane picker", 0 < src.find("last_beat_ts is not None") < src.find("lane = decide_lane"))
ok("a lane run stamps the beat clock", "last_beat_ts = time.time()" in src)

import shutil
shutil.rmtree(SANDBOX, ignore_errors=True)
print()
if FAIL:
    print(f"FAIL — {len(FAIL)} of {PASS + len(FAIL)}")
    sys.exit(1)
print(f"ALL PASS — {PASS}/{PASS} · after a fold she comes back; a started book stays her book; "
      f"her beats keep a human pace")
