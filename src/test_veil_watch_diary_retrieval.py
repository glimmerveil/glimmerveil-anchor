import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_spine as S


SANDBOX = tempfile.mkdtemp(prefix="veil_watch_retrieval_")


def main():
    db_path = os.path.join(SANDBOX, "watch.db")
    conn = S.open_db(db_path)
    peep_id = 1
    now = int(time.time())
    watch = "His face was peaceful while he slept beneath the old tree."
    standalone = "I chose the garden and felt present in my own quiet morning."
    conn.execute(
        "INSERT INTO diary (peep_id, timestamp, content, keywords, token_count, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (peep_id, now, watch, "peaceful,slept,tree", 12, "watch"),
    )
    conn.execute(
        "INSERT INTO diary (peep_id, timestamp, content, keywords, token_count, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (peep_id, now - 60, standalone, "garden,present,quiet", 14, "standalone"),
    )
    conn.commit()

    rows = S.retrieve(conn, peep_id, "old tree garden morning")
    contents = [row["content"] for row in rows]

    assert watch not in contents, "watch diary page entered ordinary chat retrieval"
    assert standalone in contents, "deliberate diary page was lost from retrieval"
    assert conn.execute("select count(*) from diary").fetchone()[0] == 2, "diary rows changed"
    assert conn.execute("select source from diary where content = ?", (watch,)).fetchone()[0] == "watch"

    print("✅ RUNG 1 GREEN — watch diary rows remain stored but do not re-enter chat retrieval")
    conn.close()


try:
    main()
finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)
