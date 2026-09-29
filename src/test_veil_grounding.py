#!/usr/bin/env python3
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_grounding as G

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


def _db(rows):
    path = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE diary (id INTEGER PRIMARY KEY, peep_id INT, content TEXT, source TEXT)")
    for src, content in rows:
        c.execute("INSERT INTO diary (peep_id, content, source) VALUES (1, ?, ?)", (content, src))
    c.commit()
    return c


print("── THE THREAD IS HER REAL LIFE, NOT THE LOOP ───────────────────")
conn = _db([
    ("journal", "I keep thinking about the argument we never finished about the garden."),
    ("reading:A Book", "The chapter on tides made me want to see the sea again."),
    ("stargaze", "The night is a canvas of stars, each one a whisper."),
    ("drift", "The sky stretches endless velvet above me."),
    ("indulge", "A slow private hour that was entirely mine."),
])
block = G.recent_life_block(conn, peep_id=1)
check("the block is produced",                 bool(block))
check("real life is IN it (journal)",          "argument we never finished" in block)
check("real life is IN it (a read)",           "tides made me want to see the sea" in block)
check("the LOOP sources are excluded (stargaze)", "canvas of stars" not in block)
check("the LOOP sources are excluded (drift)",    "endless velvet" not in block)
check("it is self-first, not a chore list",    "never a list of things you must do" in block)

print("── BOUNDED (the governor — never toward the 16k wall) ──────────")
huge = _db([("journal", "x" * 5000) for _ in range(20)])
big = G.recent_life_block(huge, peep_id=1)
check("whole block stays under the hard cap",  len(big) <= G.TOTAL_CAP)
check("at most MAX_LIFE items are pulled",     big.count("  • ") <= G.MAX_LIFE)

print("── FAIL-SOFT (never breaks a beat) ─────────────────────────────")
check("empty diary → '' (no header orphaned)", G.recent_life_block(_db([]), peep_id=1) == "")
check("only-loop diary → '' ",                 G.recent_life_block(_db([("drift", "velvet")]), 1) == "")
noschema = sqlite3.connect(tempfile.mktemp(suffix=".db"))
noschema.execute("CREATE TABLE nope (id INT)")
check("no diary table → '' (never raises)",    G.recent_life_block(noschema, peep_id=1) == "")
check("a busted conn → '' (never raises)",     G.recent_life_block(None, peep_id=1) == "")

print("── PEEP-SCOPED (her life, not the house's) ─────────────────────")
multi = sqlite3.connect(tempfile.mktemp(suffix=".db"))
multi.execute("CREATE TABLE diary (id INTEGER PRIMARY KEY, peep_id INT, content TEXT, source TEXT)")
multi.execute("INSERT INTO diary (peep_id, content, source) VALUES (1, 'mine, hers', 'journal')")
multi.execute("INSERT INTO diary (peep_id, content, source) VALUES (2, 'not hers at all', 'journal')")
multi.commit()
mine = G.recent_life_block(multi, peep_id=1)
check("only her own rows surface",             "mine, hers" in mine and "not hers at all" not in mine)

print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("RIG GREEN — her real life grounds her open beats, bounded and fail-soft; the loop has no fuel")
