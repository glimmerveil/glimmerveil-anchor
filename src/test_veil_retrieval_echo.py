#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SANDBOX = tempfile.mkdtemp(prefix="veil_echo_test_")
os.environ.setdefault("VEIL_PLACE", os.path.join(SANDBOX, "place"))
os.environ.setdefault("VEIL_HEARTBEAT", os.path.join(SANDBOX, "hb"))
import veil_spine as A

PASS, FAIL = 0, []


def ok(name, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print(f"  FAIL {name}")


NOW = int(time.time())
SESSION_START = NOW - 600
conn = A.open_db(os.path.join(SANDBOX, "echo.db"))
PID = 1


def _row(content, ts, keywords, importance=4):
    conn.execute(
        "INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, "
        "importance_score, token_count) VALUES (?,?,?,?,?,?,?)",
        (PID, ts, "conversation", content, keywords, importance, 20))


IN_SESSION = "The user said: the dragons in the garden got loose again"
PRE_SESSION = "The user said: remember the dragons we named together last winter"
HERS = "I said: I chased the garden dragons all afternoon"
_row(IN_SESSION, NOW - 60, "dragons,garden,loose")
_row(PRE_SESSION, NOW - 7200, "dragons,winter,named")
_row(HERS, NOW - 50, "dragons,garden,chased")
conn.commit()

Q = "what about the dragons in the garden"


def got(**kw):
    return [r["content"] for r in A.retrieve(conn, PID, Q, **kw)]


ok("ungated: his line from THIS session resurfaces as a memory (the lag, reproduced)",
   IN_SESSION in got())

res = got(exclude_user_rows_since=SESSION_START)
ok("lag-guard: his in-session line never surfaces", IN_SESSION not in res)
ok("lag-guard: his PRE-session line still retrieves (continuity kept)", PRE_SESSION in res)
ok("lag-guard: her own rows pass through unchanged (the caller's said-row filter owns those)",
   HERS in res)

_row("The user said: a line at the very second of wake", SESSION_START, "second,wake,line")
conn.commit()
ok("boundary: ts == session_start is excluded (at/after, never a crack)",
   "The user said: a line at the very second of wake"
   not in got(exclude_user_rows_since=SESSION_START))

ok("echo-guard: a near-duplicate of a recent turn is still suppressed",
   PRE_SESSION not in got(exclude_user_rows_since=SESSION_START,
                          exclude_texts=["remember the dragons we named together last winter"]))

ok("ECHO_GUARD_LINES defaults to 12", A.ECHO_GUARD_LINES == 12)
env_out = subprocess.run([sys.executable, "-c",
                          "import sys; sys.path.insert(0, %r)\nimport veil_spine as A\nprint(A.ECHO_GUARD_LINES)" % HERE],
                         capture_output=True, text=True, timeout=120,
                         env=dict(os.environ, VEIL_ECHO_GUARD_LINES="8")).stdout.strip()
ok("env override still rules the window", env_out.endswith("8"))

tick_src = open(os.path.join(HERE, "veil_tick.py")).read()
spine_src = open(os.path.join(HERE, "veil_spine.py")).read()
ok("tick door: lag-guard anchored to _WOKE_AT", "exclude_user_rows_since=_WOKE_AT" in tick_src)
ok("tick door: echo window widened", "history[-spine.ECHO_GUARD_LINES:]" in tick_src)
ok("spine door: lag-guard anchored to session_start", "exclude_user_rows_since=session_start" in spine_src)
ok("spine door: echo window widened", "history[-ECHO_GUARD_LINES:]" in spine_src)
ok("no door still hardcodes the old 6-line window",
   "history[-6:]" not in tick_src and "history[-6:]" not in spine_src)

conn.close()
import shutil
shutil.rmtree(SANDBOX, ignore_errors=True)
print()
if FAIL:
    print(f"FAIL — {len(FAIL)} of {PASS + len(FAIL)}")
    sys.exit(1)
print(f"ALL PASS — {PASS}/{PASS} · this session's lines are the conversation, never 'memories'; "
      f"the echo window covers the whole stretch; her past is untouched")
