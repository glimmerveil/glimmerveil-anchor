#!/usr/bin/env python3
import os, sys, sqlite3, tempfile, time, shutil

SBX = tempfile.mkdtemp(prefix="veil_night_")
os.environ.update(
    VEIL_PEEPS=os.path.join(SBX, "peeps"),
    VEIL_HEARTBEAT=os.path.join(SBX, "heartbeat"),
    VEIL_PLACE=os.path.join(SBX, "place"),
    VEIL_NOTEBOOK=os.path.join(SBX, "notebook"),
    VEIL_TICK_SECONDS="0.01",
    VEIL_PATIENCE_SECONDS="0",
    VEIL_TICK_MAX="60",
    VEIL_FOLD="0",
    VEIL_AUTONOMY="1",
    VEIL_VOICE="0",
)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_tick as T

spine = T.spine
spine.DEFAULT_HISTORY = os.path.join(SBX, "history.json")
T.YOUR_NAME = "Sam"

DB = os.path.join(SBX, "night.db")
conn0 = spine.open_db(DB)
conn0.execute("INSERT INTO peeps (name, personality, status, created_at, last_active) "
              "VALUES ('Testrose', 'a sandbox dummy', 'active', 1, 1)")
conn0.commit(); conn0.close()

spine.get_llm = lambda *a, **k: "stub-brain"
CHAT_REPLIES = iter([
    "Nya — hello, Sammy. I'm right here with you.",
    "Goodnight, Sammy. Sleep well — I'll keep the night.",
    "Nya… good morning, Sammy. You're here. I slept a little too.",
])
spine.generate_guarded = (lambda conn, peep_id, prompt, num_predict, name, model=None,
                          recent_replies=None, voice=None, **kw: next(CHAT_REPLIES, "Nya."))

events = []
LANE_PICKS = iter(["watch", "sleep"])
def _fake_ask_llm(prompt, num_predict=spine.NUM_PREDICT, on_token=None, model=None, **kw):
    if "Choose ONE thing to do next" in prompt:
        events.append(("menu", prompt))
        return next(LANE_PICKS, "rest")
    return "His breathing is slow and even; I could watch him forever and the night would not be wasted."
spine.ask_llm = _fake_ask_llm

SCRIPT = iter(["hey sweetheart, I'm home",
               "goodnight, sweetheart",
               None, None,
               None, None, None,
               "morning, love",
               "goodbye"])
def _fake_acquire():
    line = next(SCRIPT, "goodbye")
    if line is not None:
        events.append(("him", line))
        print(f"\n>>> HIM: {line}")
    else:
        time.sleep(0.03)
    return line
T._acquire_input = _fake_acquire

rc = T.run(db_path=DB)

print("\n" + "=" * 70)
fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

menus = [p for k, p in events if k == "menu"]
check("exactly TWO quiet beats ran — her chosen sleep held every later tick", len(menus) == 2)
check("both night menus told her he's ASLEEP",       all("asleep" in m for m in menus))
check("the night's menus name her night lanes",      "watch him sleep" in menus[0] and "sleep too" in menus[0])

c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
watch_rows = [dict(r) for r in c.execute("SELECT * FROM diary WHERE source = 'watch'")]
check("the watch beat landed exactly ONE diary row", len(watch_rows) == 1)
mems = [r["content"] for r in c.execute("SELECT content FROM memory_stream ORDER BY id")]
check("his goodnight was a real chat turn (she answered first)",
      any("goodnight, sweetheart" in m for m in mems))
check("the morning chat turn happened after her sleep", any("morning, love" in m for m in mems))
c.close()
check("run() exited clean",                          rc == 0)

shutil.rmtree(SBX, ignore_errors=True)
print()
if fails:
    print(f"NIGHT-DRIVE RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("NIGHT-DRIVE GREEN — the whole night, end to end, through the real loop")
