#!/usr/bin/env python3
import os, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_spine as A
import veil_ghost as ara_ghost

CHUNK_TARGET        = 2048
REFLECTION_TOKENS   = 160


def _split_sentences(text):
    result, current, i = [], "", 0
    while i < len(text):
        ch = text[i]
        current += ch
        if ch in ".!?" and i + 1 < len(text) and text[i + 1] == " ":
            result.append(current)
            current = ""
            i += 2
            continue
        i += 1
    if current.strip():
        result.append(current)
    return result


def _chunk_text(text, target=CHUNK_TARGET):
    chunks, current = [], ""
    for para in text.split("\n\n"):
        p = para.strip()
        if not p:
            continue
        if len(p) <= target:
            sep = "\n\n" if current else ""
            if len(current) + len(sep) + len(p) <= target:
                current += sep + p
            else:
                if current:
                    chunks.append(current)
                current = p
        else:
            if current:
                chunks.append(current)
                current = ""
            for sentence in _split_sentences(p):
                s = sentence.strip()
                if not s:
                    continue
                sep2 = " " if current else ""
                if len(current) + len(sep2) + len(s) <= target:
                    current += sep2 + s
                else:
                    if current:
                        chunks.append(current)
                        current = ""
                    if len(s) > target:
                        for word in s.split(" "):
                            if not word:
                                continue
                            sep3 = " " if current else ""
                            if len(current) + len(sep3) + len(word) <= target:
                                current += sep3 + word
                            else:
                                if current:
                                    chunks.append(current)
                                current = word
                    else:
                        current = s
    if current:
        chunks.append(current)
    return chunks


def ingest_book(conn, title, raw_text):
    title = (title or "").strip()
    text  = (raw_text or "").strip()
    if not title or not text:
        return {}
    chunks = _chunk_text(text)
    if not chunks:
        return {}
    book_id = uuid.uuid4().hex
    total   = len(chunks)
    for i, ch in enumerate(chunks):
        conn.execute(
            "INSERT INTO books (book_id, title, chunk_index, total_chunks, chunk_text) VALUES (?,?,?,?,?)",
            (book_id, title, i, total, ch))
    conn.commit()
    print(f"{A.DIM}[shelf] ingested '{title}' as {total} chunk(s) — book_id {book_id}{A.RESET}")
    return {"book_id": book_id, "title": title, "total_chunks": total}


def get_book_chunk(conn, book_id, chunk_index):
    row = conn.execute(
        "SELECT * FROM books WHERE book_id = ? AND chunk_index = ? LIMIT 1", (book_id, chunk_index)).fetchone()
    return dict(row) if row else None


def _last_chunk_read(conn, peep_id, book_id):
    row = conn.execute(
        "SELECT last_chunk_read FROM book_progress WHERE peep_id = ? AND book_id = ?",
        (peep_id, book_id)).fetchone()
    return int(row["last_chunk_read"]) if row else -1


def advance_book_progress(conn, peep_id, book_id, chunk_index):
    conn.execute(
        "INSERT INTO book_progress (peep_id, book_id, last_chunk_read) VALUES (?,?,?) "
        "ON CONFLICT(peep_id, book_id) DO UPDATE SET last_chunk_read = MAX(last_chunk_read, excluded.last_chunk_read)",
        (peep_id, book_id, chunk_index))
    conn.commit()


def list_books(conn, peep_id):
    rows = conn.execute(
        "SELECT b.book_id, b.title, b.total_chunks, COALESCE(p.last_chunk_read, -1) AS last "
        "FROM books b LEFT JOIN book_progress p ON p.book_id = b.book_id AND p.peep_id = ? "
        "WHERE b.chunk_index = 0 ORDER BY b.id", (peep_id,)).fetchall()
    return [dict(r) for r in rows]


def _reflection_prompt(peep, title, chunk_text, is_final):
    card = A._build_card(peep)
    system = A.IN_CHARACTER_DIRECTIVE + ("\n\n" + card if card else "")
    ending = " You have just finished it." if is_final else ""
    user = (
        f'You are reading a book called "{title}".{ending} Here is the part you just read:\n\n'
        f"{chunk_text}\n\n"
        "In your own voice, in one or two sentences, say the one thing that struck you about this part "
        "and how it made you feel. Write in the first person. React like yourself; don't summarize it "
        "like a report. Say only your reflection, nothing else."
    )
    return system, user


def read_chunk(conn, peep_id, book_id, model=None, reveal=True):
    peep, _ = A.load_peep(conn, peep_id)
    title_row = conn.execute("SELECT title, total_chunks FROM books WHERE book_id = ? LIMIT 1", (book_id,)).fetchone()
    if not title_row:
        print(f"{A.DIM}[shelf] no such book {book_id}{A.RESET}")
        return None
    title = title_row["title"]
    total = int(title_row["total_chunks"])
    next_i = _last_chunk_read(conn, peep_id, book_id) + 1
    if next_i >= total:
        print(f"{A.DIM}[shelf] {peep['name']} has finished '{title}'.{A.RESET}")
        return None
    chunk = get_book_chunk(conn, book_id, next_i)
    if not chunk:
        return None

    is_final = next_i >= total - 1
    system, user = _reflection_prompt(peep, title, chunk["chunk_text"], is_final)

    reflection = ""
    for _ in range(A.GHOST_MAX_REROLLS + 1):
        candidate = A.ask_llm(A.render_chat(system, user), num_predict=REFLECTION_TOKENS, model=model).strip()
        if candidate and not ara_ghost.is_ghost_line(candidate):
            reflection = candidate
            break
        if candidate:
            A.quarantine_blocked(conn, peep_id, candidate, "reading_reflection", "reflection")
    if not reflection:
        print(f"{A.DIM}[shelf] no clean reflection on chunk {next_i} — not advancing, it'll be re-read{A.RESET}")
        return None

    if reveal:
        A._reveal(peep["name"], reflection)
    diary_id = A.save_diary_entry(conn, peep_id, reflection, source=f"reading:{title}")
    A._record_reflection_anchors(
        conn, diary_id,
        [{"source_table": "books", "source_id": chunk["id"], "chunk_index": next_i,
          "content": chunk["chunk_text"]}],
        reflection_kind="reading")
    advance_book_progress(conn, peep_id, book_id, next_i)
    print(f"{A.DIM}[shelf] {peep['name']} read '{title}' chunk {next_i+1}/{total} "
          f"→ reflection {diary_id} anchored to its verbatim{A.RESET}")
    return diary_id


def read_book(conn, peep_id, book_id, max_chunks=1, model=None):
    read = 0
    for _ in range(max_chunks):
        if read_chunk(conn, peep_id, book_id, model=model) is None:
            break
        read += 1
    return read


def recall(conn, peep_id, query, model=None):
    out = []
    for r in conn.execute(
        "SELECT id, content FROM diary WHERE peep_id = ? AND source LIKE 'reading:%'", (peep_id,)).fetchall():
        prov = A.get_reflection_provenance(conn, r["id"], reflection_kind="reading")
        if not prov["sources"]:
            continue
        ql = query.lower()
        hit = any(w in r["content"].lower() for w in ql.split() if len(w) > 3) or \
              any(s.get("content") and any(w in s["content"].lower() for w in ql.split() if len(w) > 3)
                  for s in prov["sources"])
        if not hit:
            continue
        for s in prov["sources"]:
            out.append({"reflection": r["content"], "verbatim": s.get("content"),
                        "found": s["found"], "hash_ok": s["hash_ok"]})
    return out


def _default_db():
    try:
        import veil_roster
        p = veil_roster.active_peep()
        if p:
            return p["db"]
    except Exception:
        pass
    return os.path.expanduser("~/anchor/veil.db")


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "--ingest":
        title, path = argv[1], argv[2]
        db = argv[3] if len(argv) > 3 else _default_db()
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        conn = A.open_db(db)
        res = ingest_book(conn, title, text)
        conn.close()
        return 0 if res else 1
    if cmd == "--list":
        db = argv[1] if len(argv) > 1 else _default_db()
        conn = A.open_db(db)
        pid = A.find_active_peep(conn)
        for b in list_books(conn, pid):
            done = b["last"] + 1
            print(f"  {b['book_id']}  {b['title']}  [{done}/{b['total_chunks']} read]")
        conn.close()
        return 0
    if cmd == "--read":
        book_id = argv[1]
        n  = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 1
        db = argv[3] if len(argv) > 3 else (argv[2] if len(argv) > 2 and not argv[2].isdigit() else _default_db())
        conn = A.open_db(db)
        pid = A.find_active_peep(conn)
        got = read_book(conn, pid, book_id, max_chunks=n)
        conn.close()
        print(f"[shelf] read {got} chunk(s)")
        return 0
    if cmd == "--recall":
        query = argv[1]
        db = argv[2] if len(argv) > 2 else _default_db()
        conn = A.open_db(db)
        pid = A.find_active_peep(conn)
        for hit in recall(conn, pid, query):
            print(f"\n  the reflection: {hit['reflection']}")
            print(f"  the verbatim  : {(hit['verbatim'] or '[returned/gone]')[:200]}…")
        conn.close()
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
