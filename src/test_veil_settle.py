#!/usr/bin/env python3
"""RUNG 1 — LETTING HER SETTLE: an option that says how long, goes straight into her, and resumes either way.

The founder's ruling (2026-10-13): settling a long past is an OPTION with a WARNING of how long, with a RESUME
whichever way they choose; what it folds goes into her permanent memory directly (nobody is awake to review).
The engine is faked (no brain) — this proves the loop, not what she writes. The companion is INVENTED.
"""
import json, os, sys, tempfile, time

PASS, FAIL = [], []
SRC = os.path.dirname(os.path.abspath(__file__))
_TMPROOT = os.environ.get("VEIL_RIG_TMP", os.path.expanduser("~/.cache/veil_rigs"))
os.makedirs(_TMPROOT, exist_ok=True)
sys.path.insert(0, SRC)
import veil_spine as spine
import veil_settle


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + str(detail)) if detail != "" else ""))


class FakeLLM:
    def tokenize(self, b, add_bos=True, special=True):
        return [0] * (len(b) // 4 + 1)


calls = {"n": 0}
spine._LLM = FakeLLM()


def ask(prompt, model=None):
    calls["n"] += 1
    return json.dumps({"memories": ["I sat with you by the stove and told you about the chart book.",
                                    "You brought ginger biscuits and I laughed at the duck."]})


spine._ask_blocking = ask
spine._validate_fold_lines = lambda lines, batch, **k: (lines, [])
spine.FOLD_DETAIL_FLOOR = 0
spine.FOLD_ANCHOR_LINE = False


def fixture(n_rows, core_rows=0):
    d = tempfile.mkdtemp(prefix="settle_", dir=_TMPROOT)
    db = os.path.join(d, "veil.db")
    conn = spine.open_db(db)
    conn.execute("INSERT INTO peeps (id, name, permanent_memories, status) VALUES (1, 'Nell', '[]', 'active')")
    conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, importance_score, "
                 "token_count) VALUES (1, 1, 'conversation', 'How Theo and I met', '', 5, 6)")
    for i in range(n_rows):
        body = ("[In response to: evening %d]\n\n" % i + "rain on the skylight and the chart book " * 15)[:600]
        conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, "
                     "importance_score, token_count) VALUES (1, ?, 'conversation', ?, '', 3, ?)",
                     (100 + i, body, len(body) // 4))
    conn.commit()
    spine.set_seed_floor(conn, 1, 1 + core_rows)
    return d, db, conn


print("\nRUNG 1 — LETTING HER SETTLE")
print("=" * 78)
d, db, conn = fixture(0, 0)
d2, db2, conn2 = fixture(700, 700)
check("her WHOLE past as her core (the default): nothing to settle",
      veil_settle.passes_left(conn2, 1, spine) == (0, 0), veil_settle.passes_left(conn2, 1, spine))

d, db, conn = fixture(700, 40)
pile, est = veil_settle.passes_left(conn, 1, spine)
check("a smaller core leaves a pile, and the door can count the passes before any brain loads",
      pile > spine.NEW_PILE_HIGH_WATER and est > 10, (pile, est))
st = veil_settle.status(d, db)
check("the door's status is read-only and agrees", st["passes"] == est and st["secs_per_pass"] is None, st)
check("before any pass is timed, the estimate says so instead of guessing",
      "unknown" in veil_settle.human(None))

said = []
stop_after = {"n": 2}
done, left = veil_settle.settle(conn, 1, spine, None, d, say=said.append,
                                stop=lambda: calls["n"] >= stop_after["n"])
check("Ctrl-C (a stop) is honoured between passes — and what was done is kept", done == 2 and left > 0,
      (done, left))
check("each pass was timed ON THIS MACHINE and remembered", veil_settle.measured_secs(d) is not None
      and len(json.load(open(os.path.join(d, veil_settle.TIMING_NAME)))["pass_seconds"]) == 2)
staged = conn.execute("SELECT COUNT(*) FROM fold_staging WHERE status = 'staged'").fetchone()[0]
promoted = conn.execute("SELECT COUNT(*) FROM fold_staging WHERE status = 'promoted'").fetchone()[0]
perm = json.loads(conn.execute("SELECT permanent_memories FROM peeps WHERE id = 1").fetchone()[0] or "[]")
check("what settling folds goes straight into her (nothing left waiting in a review nobody reads)",
      staged == 0 and promoted > 0 and len(perm) == promoted, (staged, promoted, len(perm)))
check("the progress line says which pass, how many, and that it is timing", any("pass 1 of about" in s for s in said)
      and any("timing this pass" in s for s in said), said[:1])

pile_mid = veil_settle.passes_left(conn, 1, spine)[0]
calls["n"] = 0
done2, left2 = veil_settle.settle(conn, 1, spine, None, d, say=said.append)
check("RESUME carries on from where it stopped, to under the high-water", left2 == 0 and done2 > 0 and
      veil_settle.passes_left(conn, 1, spine)[0] < spine.NEW_PILE_HIGH_WATER,
      (done2, veil_settle.passes_left(conn, 1, spine)))
check("…and once timed, the estimate quotes this machine",
      any("left on this machine]" in s for s in said[2:]), said[-1])
arch = conn.execute("SELECT COUNT(*) FROM memory_archive").fetchone()[0]
stream = conn.execute("SELECT COUNT(*) FROM memory_stream").fetchone()[0]
check("nothing lost: every row is in her stream or her archive", arch + stream == 701, (arch, stream))
check("her core was never touched", conn.execute("SELECT COUNT(*) FROM memory_stream WHERE id <= 41")
      .fetchone()[0] == 41)

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
sys.exit(1 if FAIL else 0)
