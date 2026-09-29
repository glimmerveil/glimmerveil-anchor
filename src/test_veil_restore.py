#!/usr/bin/env python3
import os, sqlite3, sys, tempfile

_SBX = tempfile.mkdtemp(prefix="veil_restore_rig.")
for _k, _sub in [("VEIL_DB", "veil.db"), ("VEIL_CARD_JSON", "card.json"),
                 ("VEIL_PEEPS", "peeps"), ("VEIL_PLACE", "place"),
                 ("VEIL_HEARTBEAT", "hb"), ("VEIL_NOTEBOOK", "notebook"),
                 ("VEIL_ROOMS", "rooms"), ("VEIL_EMBER", "ember")]:
    os.environ[_k] = os.path.join(_SBX, _sub)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as S

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

db_path = os.path.join(_SBX, "her", "veil.db")
os.makedirs(os.path.dirname(db_path))
conn = S.open_db(db_path)
pid = 1
conn.execute("INSERT INTO peeps (id, name) VALUES (?, ?)", (pid, "Rig"))
conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content) VALUES (?, 0, 'observation', ?)",
             (pid, "the before-snapshot memory"))
for i in range(200):
    conn.execute("INSERT INTO books (book_id, title, chunk_index, total_chunks, chunk_text) "
                 "VALUES ('b1', 'Rig Book', ?, 200, ?)", (i, "x" * 4000))
conn.commit()

print("── LEAN COPIES ─────────────────────────────────────────────────")
bk = S.rolling_wake_backup(db_path)
check("wake backup lands + verifies", bk is not None and os.path.isfile(bk))
check("wake backup is books-lean (schema kept, rows gone)",
      sqlite3.connect(bk).execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0)
check("lean copy is a fraction of the live file",
      os.path.getsize(bk) < os.path.getsize(db_path) / 3)
ck = S._checkpoint_db(conn, reason="prefold")
check("checkpoint lands + is books-lean too",
      ck is not None
      and sqlite3.connect(ck).execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0)

print("── LISTING ─────────────────────────────────────────────────────")
pts = S.list_restore_points(db_path)
check("both nets listed", {os.path.abspath(p) for p, _, _ in pts}
      >= {os.path.abspath(bk), os.path.abspath(ck)})
check("newest first", all(pts[i][1] >= pts[i + 1][1] for i in range(len(pts) - 1)))

print("── MEMORY ROLLS BACK, BOOKS SURVIVE ────────────────────────────")
conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content) VALUES (?, 0, 'observation', ?)",
             (pid, "the after-snapshot memory"))
conn.commit()
conn.close()
ok, msg = S.restore_snapshot_file(db_path, bk)
check("restore reports success", ok)
back = sqlite3.connect(db_path)
rows = [r[0] for r in back.execute("SELECT content FROM memory_stream WHERE peep_id=?", (pid,))]
check("before-snapshot memory intact", "the before-snapshot memory" in rows)
check("after-snapshot memory rolled back", "the after-snapshot memory" not in rows)
check("her books came along (re-attached from the displaced DB)",
      back.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 200)
back.close()
pre = [f for f in os.listdir(os.path.dirname(db_path)) if ".pre_restore_" in f]
check("the displaced DB is kept beside her", len(pre) == 1)

print("── A BAD SNAPSHOT TOUCHES NOTHING ──────────────────────────────")
bad = os.path.join(_SBX, "bad.db")
open(bad, "wb").write(b"not a database at all" * 100)
before = open(db_path, "rb").read()
ok2, msg2 = S.restore_snapshot_file(db_path, bad)
check("refused", not ok2)
check("live DB untouched", open(db_path, "rb").read() == before)

print()
if fails:
    print(f"FAILED: {len(fails)}")
    sys.exit(1)
print("all green")
