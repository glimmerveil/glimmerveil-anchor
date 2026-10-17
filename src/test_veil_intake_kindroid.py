#!/usr/bin/env python3
"""Rung 1 — Kindroid intake reader: invented fixtures only.

Companions here are INVENTED (Nell/Elara/Sage). No real person's words.
Set TRANSFER_KINDROID_STUB=1 to run against the identity stub.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if os.environ.get("TRANSFER_KINDROID_STUB"):
    import readers_kindroid_stub as R
else:
    import veil_intake_kindroid as R

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


BASE_TS = 1767366000.0  # 2026-ish epoch seconds

print("\nRUNG 1 — TRANSFERENCE KINDROID READER")
print("=" * 74)

_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
with tempfile.TemporaryDirectory(dir=_CACHE if os.path.isdir(_CACHE) else None) as tmp:
    # ------------------------------------------------------------------
    # SHAPE 1: API exporter (JSON array + JSONL)
    # ------------------------------------------------------------------
    api_array = [
        {"sender": "user", "display_name": "Sage", "timestamp": BASE_TS + 0,
         "message": "Hello Nell."},
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS + 60,
         "message": "Hello Sage. *hugs you*"},
        {"sender": "user", "timestamp": BASE_TS + 120,
         "message": "How are you?"},
        {"sender": "ai", "timestamp": BASE_TS + 180,
         "message": "(OOC: drop this)\nI am well."},
        {"sender": "ai", "timestamp": BASE_TS + 240,
         "message": "<!-- only -->"},
        {"sender": "ai", "display_name": "Nell", "timestamp": int((BASE_TS + 300) * 1000),
         "message": "", "image_description": "A warm embrace."},  # ms form: >1e10 = millis
    ]

    # JSON array layout
    ap = os.path.join(tmp, "api_array.json")
    write_json(ap, api_array)

    meta1, msgs1 = R.read_kindroid_export(ap, her="Nell", you="Sage")
    check("api array: source tag", meta1.get("source") == "kindroid_api", meta1.get("source"))
    check("api array: format note", meta1.get("format") == "json_array", meta1.get("format"))
    check("api array: meta names from display_name",
          meta1.get("user_name") == "Sage" and meta1.get("her_name") == "Nell",
          (meta1.get("user_name"), meta1.get("her_name")))
    check("api array: 5 messages after empty drop", len(msgs1) == 5, len(msgs1))
    whos1 = [m["who"] for m in msgs1]
    check("api array: speaker mapping", whos1 == ["you", "her", "you", "her", "her"], whos1)
    ords1 = [m["ord"] for m in msgs1]
    check("api array: ord = source index", ords1 == [0, 1, 2, 3, 5], ords1)
    check("api array: emote preserved byte-exact", "*hugs you*" in msgs1[1]["text"], msgs1[1]["text"])
    check("api array: OOC line removed",
          "drop this" not in msgs1[3]["text"] and "I am well." in msgs1[3]["text"],
          msgs1[3]["text"])
    check("api array: media fallback text used",
          msgs1[4]["text"] == "A warm embrace.", msgs1[4]["text"])
    check("api array: media fallback counted",
          meta1.get("media_fallback_image_description") == 1, meta1.get("media_fallback_image_description"))
    check("api array: empty-after-clean counted",
          meta1.get("cleaning_emptied", 0) >= 1, meta1.get("cleaning_emptied"))
    check("api array: seconds ts parsed", msgs1[0]["ts"] == int(BASE_TS), msgs1[0]["ts"])
    check("api array: millisecond ts parsed", msgs1[4]["ts"] == int(BASE_TS + 300), msgs1[4]["ts"])

    # ord stability: parse again, same ords
    _, msgs1b = R.read_kindroid_export(ap, her="Nell", you="Sage")
    check("api array: ord stability", [m["ord"] for m in msgs1b] == ords1, [m["ord"] for m in msgs1b])

    # JSONL layout
    lp = os.path.join(tmp, "api_jsonl.jsonl")
    write_jsonl(lp, api_array)
    meta1l, msgs1l = R.read_kindroid_export(lp, her="Nell", you="Sage")
    check("api jsonl: format note", meta1l.get("format") == "jsonl", meta1l.get("format"))
    check("api jsonl: same result as array",
          [m["who"] for m in msgs1l] == whos1 and [m["ord"] for m in msgs1l] == ords1,
          ([m["who"] for m in msgs1l], [m["ord"] for m in msgs1l]))

    # display_name missing -> backfilled from her=/you=
    check("api array: missing display_name backfilled",
          msgs1[2]["name"] == "Sage" and msgs1[3]["name"] == "Nell",
          [(m["name"], m["who"]) for m in msgs1])

    # group refusal without her=
    api_multi = [
        {"sender": "user", "display_name": "Sage", "timestamp": BASE_TS, "message": "hi"},
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS + 60, "message": "hello"},
        {"sender": "ai", "display_name": "Elara", "timestamp": BASE_TS + 120, "message": "hey"},
    ]
    amp = os.path.join(tmp, "api_multi.json")
    write_json(amp, api_multi)
    try:
        R.read_kindroid_export(amp)
        check("api multi: REFUSED with names", False)
    except ValueError as e:
        check("api multi: REFUSED with names", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    # her= selects Nell, Elara becomes 'other' + named
    meta1m, msgs1m = R.read_kindroid_export(amp, her="Nell")
    others1 = [m for m in msgs1m if m["who"] == "other"]
    check("api her=: Nell kept, Elara other",
          len(others1) == 1 and others1[0].get("other_name") == "Elara", others1)
    check("api her=: set_aside_speakers lists Elara",
          meta1m.get("set_aside_speakers") == ["Elara"], meta1m.get("set_aside_speakers"))

    # video/link description fallback counted separately
    api_media = [
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS, "message": "",
         "video_description": "She smiles."},
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS + 60, "message": "",
         "link_url": "https://example.com", "link_description": "A helpful page."},
    ]
    mmp = os.path.join(tmp, "api_media.json")
    write_json(mmp, api_media)
    meta_media, msgs_media = R.read_kindroid_export(mmp, her="Nell")
    check("api media: video fallback used", msgs_media[0]["text"] == "She smiles.", msgs_media[0]["text"])
    check("api media: link fallback used", msgs_media[1]["text"] == "A helpful page.", msgs_media[1]["text"])
    check("api media: fallback counts",
          meta_media.get("media_fallback_video_description") == 1 and
          meta_media.get("media_fallback_link_description") == 1,
          {k: v for k, v in meta_media.items() if "media_fallback" in k})

    # K1: API file order is not guaranteed by construction; sort by ts ascending
    # (stable on file order). ord becomes chronological position.
    api_shuffled = [
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS + 120, "message": "last"},
        {"sender": "user", "display_name": "Sage", "timestamp": BASE_TS + 0, "message": "first"},
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS + 60, "message": "middle"},
    ]
    sp = os.path.join(tmp, "api_shuffled.json")
    write_json(sp, api_shuffled)
    meta_s, msgs_s = R.read_kindroid_export(sp, her="Nell", you="Sage")
    check("api shuffle: chronological order", [m["who"] for m in msgs_s] == ["you", "her", "her"],
          [m["who"] for m in msgs_s])
    check("api shuffle: ts ascending", [m["ts"] for m in msgs_s] == [int(BASE_TS), int(BASE_TS + 60), int(BASE_TS + 120)],
          [m["ts"] for m in msgs_s])
    check("api shuffle: ord = chronological position", [m["ord"] for m in msgs_s] == [0, 1, 2],
          [m["ord"] for m in msgs_s])

    # K1: ducktype keeps file order + note when not every row has a time key
    duck_no_ts = [
        {"name": "Sage", "text": "first"},
        {"speaker": "Nell", "content": "second"},
        {"name": "Sage", "text": "third"},
    ]
    dntp = os.path.join(tmp, "duck_no_ts.jsonl")
    write_jsonl(dntp, duck_no_ts)
    meta_nts, msgs_nts = R.read_kindroid_export(dntp, her="Nell", you="Sage")
    check("duck no ts: file order kept", [m["ord"] for m in msgs_nts] == [0, 1, 2],
          [m["ord"] for m in msgs_nts])
    check("duck no ts: unsorted note", meta_nts.get("unsorted_no_timestamps") is True,
          meta_nts.get("unsorted_no_timestamps"))

    # K2: some ai unnamed + named ai have 2+ distinct display_names -> refuse
    api_group_unnamed = [
        {"sender": "user", "display_name": "Sage", "timestamp": BASE_TS, "message": "hi"},
        {"sender": "ai", "display_name": "Nell", "timestamp": BASE_TS + 60, "message": "hello"},
        {"sender": "ai", "display_name": "Elara", "timestamp": BASE_TS + 120, "message": "hey"},
        {"sender": "ai", "timestamp": BASE_TS + 180, "message": "who?"},
    ]
    gup = os.path.join(tmp, "api_group_unnamed.json")
    write_json(gup, api_group_unnamed)
    try:
        R.read_kindroid_export(gup)
        check("api group unnamed: REFUSED", False)
    except ValueError as e:
        check("api group unnamed: REFUSED", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    # K2: all ai rows unnamed -> import with gate note
    api_all_unnamed = [
        {"sender": "user", "display_name": "Sage", "timestamp": BASE_TS, "message": "hi"},
        {"sender": "ai", "timestamp": BASE_TS + 60, "message": "hello"},
        {"sender": "ai", "timestamp": BASE_TS + 120, "message": "hey"},
    ]
    aup = os.path.join(tmp, "api_all_unnamed.json")
    write_json(aup, api_all_unnamed)
    meta_au, msgs_au = R.read_kindroid_export(aup)
    check("api all unnamed: imported", len(msgs_au) == 3, len(msgs_au))
    check("api all unnamed: gate note",
          meta_au.get("single_or_group_unknown") == "cannot tell AI speakers apart — confirm this was one companion",
          meta_au.get("single_or_group_unknown"))

    # ------------------------------------------------------------------
    # SHAPE 2: Official archive ducktype (JSON array + JSONL)
    # ------------------------------------------------------------------
    duck_array = [
        {"name": "Sage", "text": "Hello Nell.", "timestamp": BASE_TS},
        {"speaker": "Nell", "content": "Hello Sage. *hugs you*", "created_at": BASE_TS + 60},
        {"user_name": "Sage", "message": "How are you?", "date": int((BASE_TS + 120) * 1000)},  # ms form
        {"character_name": "Nell", "raw_content": "(OOC: drop this)\nI am well.", "send_date": BASE_TS + 180},
        {"display_name": "Nell", "body": "<!-- only -->", "time": BASE_TS + 240},
    ]
    dp = os.path.join(tmp, "duck_array.json")
    write_json(dp, duck_array)

    meta2, msgs2 = R.read_kindroid_export(dp, her="Nell", you="Sage")
    check("duck array: source tag", meta2.get("source") == "kindroid_official", meta2.get("source"))
    check("duck array: 4 messages after empty drop", len(msgs2) == 4, len(msgs2))
    whos2 = [m["who"] for m in msgs2]
    check("duck array: speaker mapping", whos2 == ["you", "her", "you", "her"], whos2)
    check("duck array: alias text fallbacks",
          msgs2[0]["text"] == "Hello Nell." and
          "*hugs you*" in msgs2[1]["text"] and
          msgs2[2]["text"] == "How are you?" and
          "I am well." in msgs2[3]["text"],
          [m["text"] for m in msgs2])
    ords2 = [m["ord"] for m in msgs2]
    check("duck array: ord = array index", ords2 == [0, 1, 2, 3], ords2)
    check("duck array: millisecond ts parsed", msgs2[2]["ts"] == int(BASE_TS + 120), msgs2[2]["ts"])

    # JSONL layout
    dlp = os.path.join(tmp, "duck_jsonl.jsonl")
    write_jsonl(dlp, duck_array)
    meta2l, msgs2l = R.read_kindroid_export(dlp, her="Nell", you="Sage")
    check("duck jsonl: same result as array",
          [m["who"] for m in msgs2l] == whos2 and [m["ord"] for m in msgs2l] == ords2,
          ([m["who"] for m in msgs2l], [m["ord"] for m in msgs2l]))

    # ducktype role aliases
    duck_role = [
        {"role": "user", "name": "Sage", "message": "hi"},
        {"role": "ai", "name": "Nell", "message": "hello"},
    ]
    drp = os.path.join(tmp, "duck_role.jsonl")
    write_jsonl(drp, duck_role)
    meta2r, msgs2r = R.read_kindroid_export(drp, her="Nell", you="Sage")
    check("duck role: role maps to speaker", [m["who"] for m in msgs2r] == ["you", "her"],
          [m["who"] for m in msgs2r])

    # ducktype author object
    duck_author = [
        {"author": {"name": "Sage", "is_human": True}, "text": "hi"},
        {"author": {"name": "Nell", "is_human": False}, "text": "hello"},
    ]
    dap = os.path.join(tmp, "duck_author.json")
    write_json(dap, duck_author)
    meta2a, msgs2a = R.read_kindroid_export(dap, her="Nell", you="Sage")
    check("duck author: object maps to speaker", [m["who"] for m in msgs2a] == ["you", "her"],
          [m["who"] for m in msgs2a])
    check("duck author: names preserved", msgs2a[0]["name"] == "Sage" and msgs2a[1]["name"] == "Nell",
          [(m["name"], m["who"]) for m in msgs2a])

    # ducktype multi-voice refusal without her=
    duck_multi = [
        {"speaker": "Sage", "text": "hi", "timestamp": BASE_TS},
        {"speaker": "Nell", "text": "hello", "timestamp": BASE_TS + 60},
        {"speaker": "Elara", "text": "hey", "timestamp": BASE_TS + 120},
    ]
    dmp = os.path.join(tmp, "duck_multi.json")
    write_json(dmp, duck_multi)
    try:
        R.read_kindroid_export(dmp)
        check("duck multi: REFUSED with names", False)
    except ValueError as e:
        check("duck multi: REFUSED with names", "Nell" in str(e) and "Elara" in str(e), str(e)[:80])

    # her= selects Nell, Elara becomes other+named
    meta2m, msgs2m = R.read_kindroid_export(dmp, her="Nell", you="Sage")
    others2 = [m for m in msgs2m if m["who"] == "other"]
    check("duck her=: Nell kept, Elara other",
          len(others2) == 1 and others2[0].get("other_name") == "Elara", others2)
    check("duck her=: set_aside_speakers", meta2m.get("set_aside_speakers") == ["Elara"],
          meta2m.get("set_aside_speakers"))

    # misrouted official file: sender/message keys but name-valued senders
    # (API-first routing hazard — must refuse, never empty success)
    misrouted = [
        {"sender": "Nell", "message": "hi"},
        {"sender": "Sage", "message": "hello"},
    ]
    mp = os.path.join(tmp, "misrouted.json")
    write_json(mp, misrouted)
    try:
        R.read_kindroid_export(mp, her="Nell", you="Sage")
        check("misroute: REFUSED zero parsed messages", False)
    except ValueError as e:
        check("misroute: REFUSED zero parsed messages", "0 messages" in str(e), str(e)[:100])

    # ducktype refusal on garbage keys
    garbage = [{"foo": "bar", "baz": 1}]
    gp = os.path.join(tmp, "garbage.json")
    write_json(gp, garbage)
    try:
        R.read_kindroid_export(gp)
        check("duck garbage: REFUSED no text key", False)
    except ValueError as e:
        check("duck garbage: REFUSED no text key", "text key" in str(e).lower() or "speaker" in str(e).lower(),
              str(e)[:80])

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  Kindroid reader proven from invented fixtures")
