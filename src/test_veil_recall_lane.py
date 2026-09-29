#!/usr/bin/env python3
import os, sys, tempfile, time

_SBX = tempfile.mkdtemp(prefix="veil_recall_rig.")
for _k, _sub in [("VEIL_DB", "veil.db"), ("VEIL_CARD_JSON", "card.json"),
                 ("VEIL_PEEPS", "peeps"), ("VEIL_PLACE", "place"),
                 ("VEIL_HEARTBEAT", "hb"), ("VEIL_NOTEBOOK", "notebook"),
                 ("VEIL_ROOMS", "rooms"), ("VEIL_EMBER", "ember")]:
    os.environ[_k] = os.path.join(_SBX, _sub)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card as C
import veil_spine as S

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

def _card(**kw):
    base = dict(her_name="Wren", your_name="Rook", who_she_is="A" * 50, legal_ack=True)
    base.update(kw)
    return C.VeilCard(**base)

conn = S.open_db(os.path.join(_SBX, "rig.db"))
conn.execute("INSERT INTO peeps (id, name) VALUES (1, 'Wren')")
old = int(time.time()) - 40 * 86400
for i, txt in enumerate(["The user said: the lighthouse trip was perfect",
                         "Wren said: I kept the lighthouse ticket in my pocket all day",
                         "The user said: we watched the lighthouse beam until midnight"]):
    conn.execute("INSERT INTO memory_archive (peep_id, timestamp, memory_type, content, keywords, "
                 "importance_score, token_count, compression_date, compression_pass) "
                 "VALUES (1, ?, 'conversation', ?, 'lighthouse', 4, 12, '2026-06-06T00:00:00', 1)",
                 (old + i,  txt))
conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, "
             "importance_score, token_count) VALUES (1, ?, 'conversation', "
             "'We remembered the lighthouse fondly', 'lighthouse', 3, 8)", (old,))
conn.commit()

print("── PERSONABLE IS THE FLOOR ─────────────────────────────────────")
check("spine default is closed", S.ARCHIVE_RECALL is False)
check("dataclass default is personable", _card().recall == "personable")
open(os.path.join(_SBX, "old.json"), "w").write(
    '{"her_name":"Mira","your_name":"Sam","who_she_is":"' + "A" * 50 + '","legal_ack":true}')
check("pre-law card json (no field) loads personable", C.load(os.path.join(_SBX, "old.json")).recall == "personable")
got = S.retrieve(conn, 1, "the lighthouse")
check("personable retrieval never touches the archive", all(m["kind"] != "archive" for m in got))

print("── ACCURATE OPENS THE LANE, CAPPED AT 1 ────────────────────────")
C.apply_to_spine(S, _card(recall="accurate"))
check("accurate card arms the lane", S.ARCHIVE_RECALL is True)
got = S.retrieve(conn, 1, "the lighthouse")
arch = [m for m in got if m["kind"] == "archive"]
check("an archive row is retrieved", len(arch) >= 1)
check("word-for-word (verbatim content, untouched)", any("lighthouse" in m["content"] for m in arch))
check("capped at 1 archive row per turn", len(arch) == 1)

print("── FRAMED AS LIVED, NEVER AS A BOOK ────────────────────────────")
frame = S._frame_retrieved(got)
check("rides 'Something you remember'", "Something you remember:" in frame)
check("never framed as external verbatim", "you read this" not in frame and "a book" not in frame)
check("'archive' is not an external kind", "archive" not in S.EXTERNAL_VERBATIM_KINDS)

print("── VALIDATED + WARM FLOOR RESTORED ─────────────────────────────")
check("unknown recall never births", any("recall" in p for p in _card(recall="perfect").validate()))
check("accurate validates clean", _card(recall="accurate").validate() == [])
S.ARCHIVE_RECALL = False
got = S.retrieve(conn, 1, "the lighthouse")
check("closing the lane closes it fully", all(m["kind"] != "archive" for m in got))

print()
if fails:
    print(f"RED — {len(fails)} failing: " + ", ".join(fails))
    sys.exit(1)
print("GREEN — the recall lane holds: personable is Mira untouched, accurate reads her exact past.")
