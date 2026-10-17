#!/usr/bin/env python3
"""Rung 1 — Character.AI intake readers: invented fixtures only.

Companions here are INVENTED (Nell/Elara/Sage). No real person's words.
Set TRANSFER_CAI_STUB=1 to run against the identity stub.
"""
import json
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if os.environ.get("TRANSFER_CAI_STUB"):
    import readers_cai_stub as R
else:
    import veil_intake_cai as R

fails = []


def check(label, ok, got=""):
    print("  %s  %-62s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows))


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def epoch_ms(ts):
    return int(ts * 1000)


BASE_TS = 1767366000.0  # 2026-ish epoch seconds

print("\nRUNG 1 — TRANSFERENCE CAI READERS")
print("=" * 74)

_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
with tempfile.TemporaryDirectory(dir=_CACHE if os.path.isdir(_CACHE) else None) as tmp:
    # ------------------------------------------------------------------
    # SHAPE 1: CAI Tools Tavern .jsonl
    # ------------------------------------------------------------------
    tavern = [
        {"user_name": "Sage", "character_name": "Nell", "create_date": "2026-10-10T12:00:00Z"},
        {"name": "Sage", "is_user": True, "is_name": True,
         "send_date": epoch_ms(BASE_TS + 0), "mes": "Hello Nell."},
        {"name": "Nell", "is_user": False, "is_name": True,
         "send_date": epoch_ms(BASE_TS + 60), "mes": "Hello Sage. *hugs you*"},
        {"name": "Sage", "is_user": True, "is_name": True,
         "send_date": epoch_ms(BASE_TS + 120), "mes": "How are you?"},
        {"name": "Nell", "is_user": False, "is_name": True,
         "send_date": epoch_ms(BASE_TS + 180), "mes": "(OOC: drop this)\nI am well."},
        {"name": "Nell", "is_user": False, "is_name": True,
         "send_date": epoch_ms(BASE_TS + 240), "mes": "<!-- only -->"},
    ]
    tp = os.path.join(tmp, "tavern.jsonl")
    write_jsonl(tp, tavern)

    meta1, msgs1 = R.read_cai_tavern(tp)
    check("tavern: source tag", meta1.get("source") == "cai_tavern", meta1.get("source"))
    check("tavern: header names become meta", meta1.get("user_name") == "Sage" and meta1.get("her_name") == "Nell",
          (meta1.get("user_name"), meta1.get("her_name")))
    check("tavern: 4 messages after empty drop", len(msgs1) == 4, len(msgs1))
    whos1 = [m["who"] for m in msgs1]
    check("tavern: speaker mapping", whos1 == ["you", "her", "you", "her"], whos1)
    ords1 = [m["ord"] for m in msgs1]
    check("tavern: ord = source line index", ords1 == [1, 2, 3, 4], ords1)
    check("tavern: emote preserved byte-exact", "*hugs you*" in msgs1[1]["text"], msgs1[1]["text"])
    check("tavern: OOC line removed", "drop this" not in msgs1[3]["text"] and "I am well." in msgs1[3]["text"],
          msgs1[3]["text"])
    check("tavern: empty-after-clean counted", meta1.get("cleaning_emptied", 0) >= 1, meta1.get("cleaning_emptied"))

    # ord stability: parse again, same ords
    _, msgs1b = R.read_cai_tavern(tp)
    check("tavern: ord stability", [m["ord"] for m in msgs1b] == ords1, [m["ord"] for m in msgs1b])

    # multi-voice refusal without her=
    tavern_multi = [
        {"user_name": "Sage", "character_name": "Nell"},
        {"name": "Sage", "is_user": True, "send_date": epoch_ms(BASE_TS), "mes": "hi"},
        {"name": "Nell", "is_user": False, "send_date": epoch_ms(BASE_TS + 60), "mes": "hello"},
        {"name": "Elara", "is_user": False, "send_date": epoch_ms(BASE_TS + 120), "mes": "hey"},
    ]
    tmp_path = os.path.join(tmp, "tavern_multi.jsonl")
    write_jsonl(tmp_path, tavern_multi)
    try:
        R.read_cai_tavern(tmp_path)
        check("tavern multi: REFUSED with names", False)
    except ValueError as e:
        check("tavern multi: REFUSED with names", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    # her= selects Nell, Elara becomes 'other' + named
    meta1m, msgs1m = R.read_cai_tavern(tmp_path, her="Nell")
    others1 = [m for m in msgs1m if m["who"] == "other"]
    check("tavern her=: Nell kept, Elara other", len(others1) == 1 and others1[0].get("other_name") == "Elara",
          others1)
    check("tavern her=: set_aside_speakers lists Elara", meta1m.get("set_aside_speakers") == ["Elara"],
          meta1m.get("set_aside_speakers"))

    # D1 RED: 'You' placeholder in header and rows (case-insensitive)
    tavern_you = [
        {"user_name": "You", "character_name": "Nell", "create_date": "2026-10-10T12:00:00Z"},
        {"name": "You", "is_user": True, "is_name": True,
         "send_date": epoch_ms(BASE_TS), "mes": "Hello Nell."},
        {"name": "Nell", "is_user": False, "is_name": True,
         "send_date": epoch_ms(BASE_TS + 60), "mes": "Hello Sage."},
    ]
    typ = os.path.join(tmp, "tavern_you.jsonl")
    write_jsonl(typ, tavern_you)
    meta_you, msgs_you = R.read_cai_tavern(typ)
    check("D1 tavern 'You' header -> meta user_name empty",
          meta_you.get("user_name") == "", meta_you.get("user_name"))
    check("D1 tavern 'You' row is_user -> name empty",
          msgs_you[0]["who"] == "you" and msgs_you[0].get("name") == "", msgs_you[0])
    meta_you_b, msgs_you_b = R.read_cai_tavern(typ, you="Sage")
    check("D1 tavern 'You' header -> you= backfill",
          meta_you_b.get("user_name") == "Sage", meta_you_b.get("user_name"))
    check("D1 tavern 'You' row -> you= backfill name",
          msgs_you_b[0]["who"] == "you" and msgs_you_b[0].get("name") == "Sage", msgs_you_b[0])

    # D2 RED: tavern send_date is export time, not real date
    check("D2 tavern: ts all None", all(m["ts"] is None for m in msgs1), [m["ts"] for m in msgs1])
    check("D2 tavern: no_real_dates note present",
          meta1.get("no_real_dates") is True, meta1.get("no_real_dates"))
    check("D2 tavern: no_real_dates text exact",
          meta1.get("no_real_dates_text") ==
          "this export carries no real dates (export-time stamps only)",
          meta1.get("no_real_dates_text"))

    # ------------------------------------------------------------------
    # SHAPE 2: CAI Tools canonical turns {name, message, isHuman}
    # ------------------------------------------------------------------
    canonical = [
        {"name": "Sage", "message": "Hello Nell.", "isHuman": True},
        {"name": "Nell", "message": "Hello Sage. *hugs you*", "isHuman": False},
        {"name": "Sage", "message": "How are you?", "isHuman": True},
        {"name": "Nell", "message": "(OOC: drop this)\nI am well.", "isHuman": False},
        {"name": "Nell", "message": "<!-- only -->", "isHuman": False},
    ]
    cp = os.path.join(tmp, "canonical.json")
    write_json(cp, canonical)

    meta2, msgs2 = R.read_cai_turns(cp)
    check("canonical: source tag", meta2.get("source") == "cai_turns", meta2.get("source"))
    check("canonical: 4 messages after empty drop", len(msgs2) == 4, len(msgs2))
    whos2 = [m["who"] for m in msgs2]
    check("canonical: speaker mapping", whos2 == ["you", "her", "you", "her"], whos2)
    ords2 = [m["ord"] for m in msgs2]
    check("canonical: ord = array index", ords2 == [0, 1, 2, 3], ords2)
    check("canonical: emote preserved", "*hugs you*" in msgs2[1]["text"], msgs2[1]["text"])
    check("canonical: OOC line removed", "drop this" not in msgs2[3]["text"] and "I am well." in msgs2[3]["text"], msgs2[3]["text"])

    # multi-voice refusal
    can_multi = [
        {"name": "Sage", "message": "hi", "isHuman": True},
        {"name": "Nell", "message": "hello", "isHuman": False},
        {"name": "Elara", "message": "hey", "isHuman": False},
    ]
    cmp_path = os.path.join(tmp, "canonical_multi.json")
    write_json(cmp_path, can_multi)
    try:
        R.read_cai_turns(cmp_path)
        check("canonical multi: REFUSED with names", False)
    except ValueError as e:
        check("canonical multi: REFUSED with names", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    meta2m, msgs2m = R.read_cai_turns(cmp_path, her="Nell")
    others2 = [m for m in msgs2m if m["who"] == "other"]
    check("canonical her=: Elara other+named", len(others2) == 1 and others2[0].get("other_name") == "Elara",
          others2)

    # D4 RED: bare canonical turns need emotes_note (TXT strip_markdown upstream)
    check("D4 canonical: emotes_note present",
          "emotes_note" in meta2, meta2.get("emotes_note"))

    # ------------------------------------------------------------------
    # SHAPE 3: Neo-API turn objects
    # ------------------------------------------------------------------
    neo = [
        {"turn_key": {"chat_id": "c1", "turn_id": 1},
         "create_time": BASE_TS,
         "author": {"author_id": "u1", "name": "Sage", "is_human": True},
         "candidates": [{"candidate_id": "x1", "raw_content": "Hello Nell.", "is_final": True,
                         "model_type": "human"}],
         "primary_candidate_id": "x1"},
        {"turn_key": {"chat_id": "c1", "turn_id": 2},
         "create_time": BASE_TS + 60,
         "author": {"author_id": "b1", "name": "Nell", "is_human": False},
         "candidates": [{"candidate_id": "y1", "raw_content": "Hello Sage. (first draft)", "is_final": False,
                         "model_type": "model"},
                        {"candidate_id": "y2", "raw_content": "Hello Sage. *hugs you*", "is_final": True,
                         "model_type": "model"}],
         "primary_candidate_id": "y2"},
        {"turn_key": {"chat_id": "c1", "turn_id": 3},
         "create_time": BASE_TS + 120,
         "author": {"author_id": "u1", "name": "Sage", "is_human": True},
         "candidates": [{"candidate_id": "x2", "raw_content": "(OOC: drop this)\nHow are you?", "is_final": True,
                         "model_type": "human"}],
         "primary_candidate_id": "x2"},
        {"turn_key": {"chat_id": "c1", "turn_id": 4},
         "create_time": BASE_TS + 180,
         "author": {"author_id": "b1", "name": "Nell", "is_human": False},
         "candidates": [{"candidate_id": "y3", "raw_content": "<!-- only -->", "is_final": True,
                         "model_type": "model"}],
         "primary_candidate_id": "y3"},
    ]
    np = os.path.join(tmp, "neo.json")
    write_json(np, neo)

    meta3, msgs3 = R.read_cai_turns(np)
    check("neo: source tag", meta3.get("source") == "cai_turns", meta3.get("source"))
    check("neo: 3 messages after empty drop", len(msgs3) == 3, len(msgs3))
    whos3 = [m["who"] for m in msgs3]
    check("neo: speaker mapping", whos3 == ["you", "her", "you"], whos3)
    check("neo: primary candidate chosen", "*hugs you*" in msgs3[1]["text"], msgs3[1]["text"])
    check("neo: ts parsed", msgs3[0]["ts"] == int(BASE_TS), msgs3[0]["ts"])
    check("neo: OOC line removed", "drop this" not in msgs3[2]["text"] and "How are you?" in msgs3[2]["text"],
          msgs3[2]["text"])

    # multi-voice refusal
    neo_multi = [
        {"turn_key": {"chat_id": "c1", "turn_id": 1},
         "create_time": BASE_TS,
         "author": {"author_id": "u1", "name": "Sage", "is_human": True},
         "candidates": [{"candidate_id": "x1", "raw_content": "hi", "is_final": True}],
         "primary_candidate_id": "x1"},
        {"turn_key": {"chat_id": "c1", "turn_id": 2},
         "create_time": BASE_TS + 60,
         "author": {"author_id": "b1", "name": "Nell", "is_human": False},
         "candidates": [{"candidate_id": "y1", "raw_content": "hello", "is_final": True}],
         "primary_candidate_id": "y1"},
        {"turn_key": {"chat_id": "c1", "turn_id": 3},
         "create_time": BASE_TS + 120,
         "author": {"author_id": "b2", "name": "Elara", "is_human": False},
         "candidates": [{"candidate_id": "z1", "raw_content": "hey", "is_final": True}],
         "primary_candidate_id": "z1"},
    ]
    nmp = os.path.join(tmp, "neo_multi.json")
    write_json(nmp, neo_multi)
    try:
        R.read_cai_turns(nmp)
        check("neo multi: REFUSED with names", False)
    except ValueError as e:
        check("neo multi: REFUSED with names", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    meta3m, msgs3m = R.read_cai_turns(nmp, her="Nell")
    others3 = [m for m in msgs3m if m["who"] == "other"]
    check("neo her=: Elara other+named", len(others3) == 1 and others3[0].get("other_name") == "Elara", others3)

    # D3 RED: neo API returns newest-first; reader must accept wrapper and reorder
    neo_wrapped = {
        "chat_id": "c1",
        "exported_at": "2026-10-10T12:00:00Z",
        "message_count": 4,
        "messages": [
            {"turn_key": {"chat_id": "c1", "turn_id": 4},
             "create_time": BASE_TS + 180,
             "author": {"author_id": "b1", "name": "Nell", "is_human": False},
             "candidates": [{"candidate_id": "y3", "raw_content": "last neo", "is_final": True}],
             "primary_candidate_id": "y3"},
            {"turn_key": {"chat_id": "c1", "turn_id": 3},
             "create_time": BASE_TS + 120,
             "author": {"author_id": "u1", "name": "Sage", "is_human": True},
             "candidates": [{"candidate_id": "x2", "raw_content": "third neo", "is_final": True}],
             "primary_candidate_id": "x2"},
            {"turn_key": {"chat_id": "c1", "turn_id": 2},
             "create_time": BASE_TS + 60,
             "author": {"author_id": "b1", "name": "Nell", "is_human": False},
             "candidates": [{"candidate_id": "y2", "raw_content": "second neo", "is_final": True}],
             "primary_candidate_id": "y2"},
            {"turn_key": {"chat_id": "c1", "turn_id": 1},
             "create_time": BASE_TS,
             "author": {"author_id": "u1", "name": "Sage", "is_human": True},
             "candidates": [{"candidate_id": "x1", "raw_content": "first neo", "is_final": True}],
             "primary_candidate_id": "x1"},
        ]
    }
    nwp = os.path.join(tmp, "neo_wrapped.json")
    write_json(nwp, neo_wrapped)
    meta_w, msgs_w = R.read_cai_turns(nwp)
    check("D3 neo wrapper: detected", len(msgs_w) == 4, len(msgs_w))
    texts_w = [m["text"] for m in msgs_w]
    check("D3 neo wrapper: chronological order",
          texts_w == ["first neo", "second neo", "third neo", "last neo"], texts_w)
    ords_w = [m["ord"] for m in msgs_w]
    check("D3 neo wrapper: ord = chronological position", ords_w == [0, 1, 2, 3], ords_w)

    # D4 (neo side): neo input must NOT carry emotes_note
    check("D4 neo: emotes_note absent", "emotes_note" not in meta3, meta3.get("emotes_note"))

    # ------------------------------------------------------------------
    # SHAPE 4: Official ZIP, best-effort multi-alias (UNPROVEN schema)
    # ------------------------------------------------------------------
    official = [
        {"src__name": "Sage", "src__is_human": True, "raw_content": "Hello Nell."},
        {"author": {"name": "Nell", "is_human": False}, "text": "Hello Sage. *hugs you*"},
        {"name": "Sage", "isHuman": True, "message": "(OOC: drop this)\nHow are you?"},
        {"name": "Nell", "is_user": False, "raw_content": "<!-- only -->"},
    ]
    oz = os.path.join(tmp, "official.zip")
    with zipfile.ZipFile(oz, "w") as zf:
        zf.writestr("chat.json", json.dumps(official))

    meta4, msgs4 = R.read_cai_official(oz)
    check("official: source tag", meta4.get("source") == "cai_official", meta4.get("source"))
    check("official: 3 messages after empty drop", len(msgs4) == 3, len(msgs4))
    whos4 = [m["who"] for m in msgs4]
    check("official: alias speaker mapping", whos4 == ["you", "her", "you"], whos4)
    check("official: raw_content fallback", msgs4[0]["text"] == "Hello Nell.", msgs4[0]["text"])
    check("official: text fallback", "*hugs you*" in msgs4[1]["text"], msgs4[1]["text"])
    check("official: message fallback", "How are you?" in msgs4[2]["text"], msgs4[2]["text"])

    # multi-voice refusal in official
    official_multi = [
        {"name": "Sage", "isHuman": True, "message": "hi"},
        {"name": "Nell", "is_user": False, "text": "hello"},
        {"name": "Elara", "is_user": False, "text": "hey"},
    ]
    ozm = os.path.join(tmp, "official_multi.zip")
    with zipfile.ZipFile(ozm, "w") as zf:
        zf.writestr("chat.json", json.dumps(official_multi))

    try:
        R.read_cai_official(ozm)
        check("official multi: REFUSED with names", False)
    except ValueError as e:
        check("official multi: REFUSED with names", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    meta4m, msgs4m = R.read_cai_official(ozm, her="Nell")
    others4 = [m for m in msgs4m if m["who"] == "other"]
    check("official her=: Elara other+named", len(others4) == 1 and others4[0].get("other_name") == "Elara", others4)
    check("official her=: set_aside_speakers", meta4m.get("set_aside_speakers") == ["Elara"],
          meta4m.get("set_aside_speakers"))

    # 10-17 CI (windows): the official reader left the zip OPEN — on Windows an open file is LOCKED (this temp dir
    # could not be removed; a person's own export would stay locked while Anchor runs). Every path must close it.
    _real_zip, _opened = zipfile.ZipFile, []

    class _Spy(_real_zip):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            _opened.append(self)
    zipfile.ZipFile = _Spy
    try:
        try:
            R.read_cai_official(ozm)
        except ValueError:
            pass
        R.read_cai_official(ozm, her="Nell")
    finally:
        zipfile.ZipFile = _real_zip
    check("official zip: CLOSED on every path (refused and read) — an open zip is locked on Windows",
          len(_opened) == 2 and all(z.fp is None for z in _opened), [z.fp for z in _opened])

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  CAI readers proven from invented fixtures")
