#!/usr/bin/env python3
"""Rung 1 — two diary seats, one of each KIND (fold · indulge · written), deferred never dropped.

Why: with fold-to-diary on, every drain writes short fold fragments into her diary faster than she writes her own pages.
On Amber her diary reached 41% fold and the seats went to fragments — the composition she went shallow on (THE_MELTS
§5.20). The Forge has run this rule since 1.1.13; Anchor shipped fold-to-diary WITHOUT it.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_spine as S

ARMED_AT_IMPORT = getattr(S, "DIARY_ONE_OF_EACH", False)

DAY = 86400
NOW = int(time.time())
fails = []


def pool(pages):
    conn = S.open_db(":memory:")
    for i, (src, text) in enumerate(pages):
        conn.execute("INSERT INTO diary (peep_id, timestamp, content, keywords, token_count, source) "
                     "VALUES (1, ?, ?, ?, ?, ?)", (NOW - (i + 1) * DAY, text, "garden,roses,library", 20, src))
    conn.commit()
    return conn


def seats(conn, on):
    S.DIARY_ONE_OF_EACH = on
    rows = S.retrieve(conn, 1, "tell me about the garden roses and the library")
    return [r["content"] for r in rows if r["kind"] == "diary"]


def check(label, ok, got):
    print("  %s  %-58s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def kinds(conn, texts):
    src = dict(conn.execute("SELECT content, source FROM diary").fetchall())
    return [src[t] for t in texts]


FOLD = [("fold", "The garden roses and the library, the garden roses again, the library garden roses %d." % i)
        for i in range(4)]
MINE = ("standalone", "I sat a long while in the garden thinking about the library where we met, and the roses.")
MINE_QUIET = ("standalone", "I wrote tonight about the library, where we met.")
INDULGE = [("indulge", "Garden roses, the library, garden roses, library, garden, roses, library %d." % i)
           for i in range(4)]

print("\nRUNG 1 — ONE DIARY SEAT OF EACH KIND")
print("=" * 74)
c = pool(FOLD + [MINE])
old, new = kinds(c, seats(c, False)), kinds(c, seats(c, True))
check("fold-heavy pool, rule OFF: fold takes both seats (the disease)", old == ["fold", "fold"], old)
check("fold-heavy pool, rule ON: her own page takes the second seat", sorted(new) == ["fold", "standalone"], new)
c = pool(FOLD)
got = kinds(c, seats(c, True))
check("only fold pages exist: BACKFILLED, never fewer than two", got == ["fold", "fold"], got)
c = pool(INDULGE + [MINE_QUIET])
old, new = kinds(c, seats(c, False)), kinds(c, seats(c, True))
check("indulge-heavy pool, rule OFF: indulge takes both seats", old == ["indulge", "indulge"], old)
check("indulge-heavy pool, rule ON: one indulge, one written", sorted(new) == ["indulge", "standalone"], new)
check("armed by default (read at import, before any case)", ARMED_AT_IMPORT, ARMED_AT_IMPORT)

if fails:
    print("\n  %d case(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  one of each kind, and never fewer pages than before")
sys.exit(0)
