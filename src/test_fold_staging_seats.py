#!/usr/bin/env python3
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VEIL_MODEL", "/nonexistent")
import veil_spine as spine

ANCH = ' — what I said that night: "…and you said the thing about yin and yang."'
res = []


def check(name, ok, detail=""):
    res.append(ok)
    print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE peeps (id INTEGER PRIMARY KEY, name TEXT, permanent_memories TEXT)")
    c.execute("INSERT INTO peeps (id,name,permanent_memories) VALUES (1,'Mira','[]')")
    c.execute("CREATE TABLE fold_staging (id INTEGER PRIMARY KEY AUTOINCREMENT, peep_id INT, "
              "batch_id TEXT, content TEXT, created_at INT, status TEXT, decided_at INT)")
    c.execute("CREATE TABLE memory_quarantine (orig_id INT, source_table TEXT, peep_id INT, "
              "timestamp TEXT, memory_type TEXT, content TEXT, keywords TEXT, "
              "importance_score INT, token_count INT, quarantined_at TEXT)")
    return c


def staged(c):
    return [r["content"] for r in c.execute(
        "SELECT content FROM fold_staging WHERE status='staged' ORDER BY id")]


WEAK = ["I said out loud that I feel close to the stars and wished you were here with me.",
        "I asked for a cup of tea and some cookies, feeling alive and free among the stars."]
EVENING = ["You held me close and danced with me in the garden, making every moment perfect." + ANCH,
           "I settled on the stone balcony and stretched out to stroke the balustrade." + ANCH]

c = db()
since = int(time.time())
b = 4
b -= spine._stage_fold_memories(c, 1, "batch1", WEAK, b, drain_since=since)
WEAK2 = ["I wished you were here to pet me while I watched the moonlight move.",
         "I asked the empty garden whether you would be back before the stars went out."]
b -= spine._stage_fold_memories(c, 1, "batch2", WEAK2, b, drain_since=since)
check("the cap fills first, exactly as before", len(staged(c)) == 4, f"{len(staged(c))} seats")
check("and it is all alone-time rows at that point",
      not any(spine._carries_her_words(t) for t in staged(c)))

spine._stage_fold_memories(c, 1, "batch3", EVENING, b, drain_since=since)
now_staged = staged(c)
check("her own words take the seats when the cap is spent",
      sum(1 for t in now_staged if spine._carries_her_words(t)) == 2,
      f"{sum(1 for t in now_staged if spine._carries_her_words(t))} anchored")
check("the seat COUNT never grows", len(now_staged) == 4, f"{len(now_staged)} seats")
check("the displaced rows are marked, never deleted",
      c.execute("SELECT COUNT(*) FROM fold_staging WHERE status='displaced'").fetchone()[0] == 2)
check("a displaced row can never be promoted",
      spine.promote_staged_folds(c, 1, now=since + spine.FOLD_STAGE_SECONDS + 1) == 4)

c2 = db()
since2 = int(time.time())
spine._stage_fold_memories(c2, 1, "b1", EVENING, 2, drain_since=since2)
spine._stage_fold_memories(c2, 1, "b2", ["Another evening row of hers." + ANCH], 0,
                           drain_since=since2)
check("an anchored seat is never taken by another anchored row",
      len(staged(c2)) == 2 and c2.execute(
          "SELECT COUNT(*) FROM fold_staging WHERE status='displaced'").fetchone()[0] == 0)

c3 = db()
spine._stage_fold_memories(c3, 1, "b1", WEAK, 2)
spine._stage_fold_memories(c3, 1, "b2", EVENING, 0)
check("without a drain marker it is EXACTLY today: her words stay out",
      len(staged(c3)) == 2 and not any(spine._carries_her_words(t) for t in staged(c3)))

check("the marker is the one the anchor writes",
      spine._carries_her_words(EVENING[0]) and not spine._carries_her_words(WEAK[0]))

print(f"\n{sum(res)}/{len(res)} — {'GREEN' if all(res) else 'RED'}")
raise SystemExit(0 if all(res) else 1)
