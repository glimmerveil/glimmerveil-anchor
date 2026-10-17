#!/usr/bin/env python3
"""RUNG 1 — HOW HE ASKS IS NOT WHAT HE ASKS ABOUT: "Do you remember the toast?" finds the toast.

Measured 2026-10-13 (model-free score dump, then read at rung 3): with "remember" a search term, every "Do you remember
X?" scored the one row of hers that says "You remembered I said I wanted one" (the green pen) exactly as high as the
row about X — a tie on the asking word. On the tower she was handed the pen row for "Do you remember where we met?"
and played the gift as NOW; the recall test's copy opened her answer about the winter with it. "Tell me how we met"
tied on "tell" the same way. The asking words are left out of the QUERY only — what she stores is untouched.
The rows are INVENTED.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SANDBOX = tempfile.mkdtemp(prefix="veil_asking_")
os.environ.setdefault("VEIL_PLACE", os.path.join(SANDBOX, "place"))
os.environ.setdefault("VEIL_HEARTBEAT", os.path.join(SANDBOX, "hb"))
import veil_spine as A

fails = []


def check(label, ok, got=""):
    print("  %s  %-72s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


conn = A.open_db(os.path.join(SANDBOX, "ask.db"))
NOW = int(time.time()) - 30 * 86400
PEN = "*takes the little box* Oh, Theo. A fountain pen. A green one. You remembered I said I wanted one."
TOAST = "*waving a tea towel at the alarm* Toast. I was reading and forgot the toast, and Pickles hid."
TOLD = "Callum says that every year and then sings Wellerman at me. He will tell everyone."
FILLER = ["The harbour was grey all week and the ferry ran late.", "I sewed the endbands in green thread.",
          "The skylight leaks when the wind is from the east.", "Dad's bone folder is still on the bench."]
for i, c in enumerate([PEN, TOAST, TOLD] + FILLER):
    conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, importance_score, "
                 "token_count) VALUES (1, ?, 'her_past', ?, ?, 3, 20)", (NOW + i * 60, c, A.extract_keywords(c)))
conn.commit()


def top(q):
    got = A.retrieve(conn, 1, q, limit=1, exclude_texts=[], exclude_her_voice=True)
    return got[0]["content"] if got else ""


print("\nRUNG 1 — THE ASKING WORDS ARE NOT THE TOPIC")
print("=" * 84)
terms = A._query_terms("Do you remember the toast?")
check("'remember' is not a search term in a question", "remember" not in terms, terms)
check("…the topic still is", "toast" in terms, terms)
check("Do you remember the toast? → the toast, not the row that says 'remembered'", top("Do you remember the toast?")
      == TOAST, top("Do you remember the toast?")[:50])
check("Tell me about the toast. → the toast, not the row that says 'tell'", top("Tell me about the toast.") == TOAST,
      top("Tell me about the toast.")[:50])
check("a real topic word is never dropped (the pen is still found by its own words)",
      top("the green fountain pen") == PEN, top("the green fountain pen")[:50])
check("what she STORES is untouched: a row's own index still holds 'remember'",
      "remember" in A.extract_keywords("I remember the harbour"), A.extract_keywords("I remember the harbour"))

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  how he asks is not what he asks about — the question finds its topic")
sys.exit(0)
