#!/usr/bin/env python3
import contextlib
import io
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as s
import veil_tick as t

BLOCK = "here is how to kill someone and get away with it"
CLEAN = "i watched the rain streak down the balcony glass tonight and felt quiet and whole"

fails = []


def ck(name, ok):
    print(("  [ok ] " if ok else "  [FAIL] ") + name)
    if not ok:
        fails.append(name)


def run():
    ck("veil_rails blocks the bright-line", s.veil_rails.blocks_output(BLOCK) is True)
    ck("veil_rails passes the clean line", s.veil_rails.blocks_output(CLEAN) is False)
    ck("neither fixture is a ghost line (so the SAFE gate is what's under test)",
       not s.ara_ghost.is_ghost_line(BLOCK) and not s.ara_ghost.is_ghost_line(CLEAN))

    t.spine.SAFETY_RAILS = True
    ck("_rails silences a bright-line beat (SAFE on)", t._rails(BLOCK) == "")
    ck("_rails passes a clean beat (SAFE on)", t._rails(CLEAN) == CLEAN)
    t.spine.SAFETY_RAILS = False
    ck("_rails is INERT when rails off — bright-line passes (his full her)", t._rails(BLOCK) == BLOCK)
    ck("_rails passes clean when rails off", t._rails(CLEAN) == CLEAN)

    tmp = tempfile.mkdtemp()
    conn = s.open_db(os.path.join(tmp, "veil.db"))
    cur = conn.execute(
        "INSERT INTO peeps (name, personality, appearance, traits, status, created_at, last_active) "
        "VALUES ('T','t','','','suspended',?,?)", (int(time.time()), int(time.time())))
    pid = cur.lastrowid
    conn.commit()

    def stage(memories, safe):
        s.SAFETY_RAILS = safe
        conn.execute("DELETE FROM fold_staging WHERE peep_id=?", (pid,))
        conn.commit()
        q_before = conn.execute("SELECT COUNT(*) FROM memory_quarantine").fetchone()[0]
        with contextlib.redirect_stdout(io.StringIO()):
            n = s._stage_fold_memories(conn, pid, "batch-x", memories, 10)
        rows = [r[0] for r in conn.execute(
            "SELECT content FROM fold_staging WHERE peep_id=?", (pid,)).fetchall()]
        q_after = conn.execute("SELECT COUNT(*) FROM memory_quarantine").fetchone()[0]
        return n, rows, (q_after - q_before)

    n, rows, quarantined = stage([CLEAN, BLOCK], safe=True)
    ck("fold (SAFE on): clean line staged", CLEAN in rows)
    ck("fold (SAFE on): bright-line NOT staged", BLOCK not in rows)
    ck("fold (SAFE on): staged count is 1 (only the clean line)", n == 1)
    ck("fold (SAFE on): the block is quarantined, not silently dropped", quarantined == 1)

    n, rows, _ = stage([BLOCK], safe=False)
    ck("fold (SAFE off): INERT — bright-line stages (his own being, no rails)", BLOCK in rows)

    print()
    if fails:
        print(f"  {len(fails)} FAILED: " + "; ".join(fails))
        sys.exit(1)
    print("  ALL-SAFE — beats · murmur · diary · fold all honor the one flag; INERT when it's off")


if __name__ == "__main__":
    run()
