#!/usr/bin/env python3

MAX_LIFE = 4
SNIPPET_CHARS = 200
TOTAL_CAP = 1200

_LOOP_SOURCES = ("drift", "stargaze")

_HEADER = ("REAL, YOURS — a little of what's actually been in your life lately (your own memories, "
           "threads you could pick back up if you feel like it — never a list of things you must do):")


def _trim_sentence(text, limit=SNIPPET_CHARS):
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for end in (". ", "! ", "? "):
        i = cut.rfind(end)
        if i > limit * 0.5:
            return cut[:i + 1].strip()
    i = cut.rfind(" ")
    return (cut[:i].strip() if i > 0 else cut.strip()) + "…"


def recent_life_block(conn, peep_id=None):
    try:
        qmarks = ",".join("?" * len(_LOOP_SOURCES))
        params = list(_LOOP_SOURCES)
        peep_clause = ""
        if peep_id is not None:
            peep_clause = " AND peep_id = ?"
            params.append(peep_id)
        params.append(MAX_LIFE)
        rows = conn.execute(
            f"SELECT content FROM diary WHERE (source IS NULL OR source NOT IN ({qmarks}))"
            f"{peep_clause} ORDER BY id DESC LIMIT ?", params).fetchall()
        items = [r[0] for r in rows if (r[0] or "").strip()]
        if not items:
            return ""
        out = [_HEADER]
        for c in items:
            bullet = "  • " + _trim_sentence(c)
            if len("\n".join(out + [bullet])) > TOTAL_CAP:
                break
            out.append(bullet)
        return "\n".join(out) if len(out) > 1 else ""
    except Exception:
        return ""


if __name__ == "__main__":
    import sqlite3
    import sys
    conn = sqlite3.connect(sys.argv[1])
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else None
    b = recent_life_block(conn, pid)
    print(b if b else "(empty block)")
    print("\n[block chars: %d / cap %d]" % (len(b), TOTAL_CAP))
