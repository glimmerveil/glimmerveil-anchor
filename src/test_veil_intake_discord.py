#!/usr/bin/env python3
"""Rung 1 — Discord intake reader: invented fixtures only.

Companions here are INVENTED (Nell/Elara/Sage style). No real person's words.
Snowflake ids are invented — never real Discord ids.
Set TRANSFER_DISCORD_STUB=1 to run against the identity stub.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if os.environ.get("TRANSFER_DISCORD_STUB"):
    import readers_discord_stub as R
else:
    import veil_intake_discord as R

fails = []


def check(label, ok, got=""):
    print("  %s  %-62s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def make_export(messages, guild=None, channel=None):
    return {
        "guild": guild or {"id": "123", "name": "Test Guild", "iconUrl": ""},
        "channel": channel or {"id": "456", "type": "GuildTextChat",
                               "categoryId": "0", "category": "General",
                               "name": "test-chat", "topic": "invented"},
        "dateRange": {"after": None, "before": None},
        "exportedAt": "2026-10-17T00:00:00+00:00",
        "messages": messages,
        "messageCount": len(messages),
    }


BASE_TS = "2026-10-17T12:00:00+00:00"

print("\nRUNG 1 — TRANSFERENCE DISCORD READER")
print("=" * 74)

_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
with tempfile.TemporaryDirectory(prefix="vt_discord_", dir=_CACHE if os.path.isdir(_CACHE) else None) as tmp:
    # ------------------------------------------------------------------
    # SHAPE 1: id-keyed mapping + basic contract
    # ------------------------------------------------------------------
    msgs1 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS, "timestampEdited": None,
         "callEndedTimestamp": None, "isPinned": False,
         "content": "Hello Nell.",
         "author": {"id": "1001", "name": "sage_user", "discriminator": "0000",
                    "nickname": "Sage", "color": "#000000", "isBot": False,
                    "roles": [], "avatarUrl": ""},
         "attachments": [], "embeds": [], "stickers": [], "reactions": [],
         "mentions": [], "inlineEmojis": []},
        {"id": "2", "type": "Default", "timestamp": "2026-10-17T12:01:00+00:00",
         "timestampEdited": None, "callEndedTimestamp": None, "isPinned": False,
         "content": "Hello Sage. *hugs you*",
         "author": {"id": "1002", "name": "nell_bot", "discriminator": "0000",
                    "nickname": "Nell", "color": "#000000", "isBot": False,
                    "roles": [], "avatarUrl": ""},
         "attachments": [], "embeds": [], "stickers": [], "reactions": [],
         "mentions": [], "inlineEmojis": []},
    ]
    p1 = os.path.join(tmp, "solo.json")
    write_json(p1, make_export(msgs1))

    meta1, out1 = R.read_discord_export(p1, her="1002", you="1001")
    check("solo: source tag", meta1.get("source") == "discord", meta1.get("source"))
    check("solo: title from guild/channel", meta1.get("title") == "Test Guild / #test-chat", meta1.get("title"))
    check("solo: meta names", meta1.get("user_name") == "Sage" and meta1.get("her_name") == "Nell",
          (meta1.get("user_name"), meta1.get("her_name")))
    check("solo: 2 messages", len(out1) == 2, len(out1))
    whos1 = [m["who"] for m in out1]
    check("solo: speaker mapping", whos1 == ["you", "her"], whos1)
    ords1 = [m["ord"] for m in out1]
    check("solo: ord = array position", ords1 == [0, 1], ords1)
    check("solo: emote preserved byte-exact", out1[1]["text"] == "Hello Sage. *hugs you*", out1[1]["text"])

    # ord stability double-parse
    _, out1b = R.read_discord_export(p1, her="1002", you="1001")
    check("solo: ord stability", [m["ord"] for m in out1b] == ords1, [m["ord"] for m in out1b])

    # author map includes both
    am1 = meta1.get("author_map") or {}
    check("solo: author map has both", set(am1.keys()) == {"1001", "1002"}, list(am1.keys()))

    # ------------------------------------------------------------------
    # SHAPE 2: nickname:/name: forms + instability warning
    # ------------------------------------------------------------------
    meta2, out2 = R.read_discord_export(p1, her="nickname:Nell", you="name:sage_user")
    check("nickname/name forms: her mapped", meta2.get("her_name") == "Nell", meta2.get("her_name"))
    check("nickname/name forms: you mapped", meta2.get("user_name") == "Sage", meta2.get("user_name"))
    check("nickname/name forms: who order", [m["who"] for m in out2] == ["you", "her"],
          [m["who"] for m in out2])

    # bare name form also works (nickname first)
    meta2b, out2b = R.read_discord_export(p1, her="Nell", you="Sage")
    check("bare name forms: mapped", [m["who"] for m in out2b] == ["you", "her"],
          [m["who"] for m in out2b])

    # ------------------------------------------------------------------
    # SHAPE 3: multi-author refusal (3+) listing id+nickname+name
    # ------------------------------------------------------------------
    msgs3 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS, "content": "hi",
         "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "hello",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
        {"id": "3", "type": "Default", "timestamp": BASE_TS, "content": "hey",
         "author": {"id": "1003", "name": "elara_user", "nickname": "Elara", "isBot": False}},
    ]
    p3 = os.path.join(tmp, "multi.json")
    write_json(p3, make_export(msgs3))
    try:
        R.read_discord_export(p3)
        check("multi 3+: REFUSED", False)
    except ValueError as e:
        txt = str(e)
        check("multi 3+: REFUSED", "1001" in txt and "Sage" in txt and "sage_user" in txt and
              "1002" in txt and "1003" in txt, txt[:200])

    # ------------------------------------------------------------------
    # SHAPE 4: exactly 2 authors without her= -> refuse
    # ------------------------------------------------------------------
    msgs4 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS, "content": "hi",
         "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "hello",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
    ]
    p4 = os.path.join(tmp, "duo_no_hint.json")
    write_json(p4, make_export(msgs4))
    try:
        R.read_discord_export(p4)
        check("duo no her: REFUSED", False)
    except ValueError as e:
        txt = str(e)
        check("duo no her: REFUSED (her is never guessed; both authors listed)", "never guess" in txt and "1001" in txt and "1002" in txt,
              txt[:200])

    # ------------------------------------------------------------------
    # SHAPE 5: her=/you= selection + other+named
    # ------------------------------------------------------------------
    meta5, out5 = R.read_discord_export(p3, her="1002", you="1001")
    check("her=you= with third: her kept",
          any(m["who"] == "her" and m["name"] == "Nell" for m in out5), out5)
    others5 = [m for m in out5 if m["who"] == "other"]
    check("her=you= with third: other named Elara",
          len(others5) == 1 and others5[0].get("other_name") == "Elara", others5)
    check("her=you= with third: set_aside_speakers lists Elara",
          meta5.get("set_aside_speakers") == ["Elara"], meta5.get("set_aside_speakers"))

    # ------------------------------------------------------------------
    # SHAPE 6: bot drop + count
    # ------------------------------------------------------------------
    msgs6 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS, "content": "hi",
         "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "beep",
         "author": {"id": "9001", "name": "botty", "nickname": "Botty", "isBot": True}},
        {"id": "3", "type": "Default", "timestamp": BASE_TS, "content": "hello",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
    ]
    p6 = os.path.join(tmp, "bot.json")
    write_json(p6, make_export(msgs6))
    meta6, out6 = R.read_discord_export(p6, her="1002", you="1001")
    check("bot: dropped", meta6.get("bot_dropped") == 1, meta6.get("bot_dropped"))
    check("bot: the other bot is never you or her", all(m["who"] == "other" for m in out6 if m["name"] == "Botty"),
          [(m["who"], m["name"]) for m in out6])
    check("bot: only 2 rows of you+her", len([m for m in out6 if m["who"] in ("you", "her")]) == 2, len(out6))
    check("bot: named in set_aside_speakers", "Botty" in meta6.get("set_aside_speakers", []), meta6.get("set_aside_speakers"))

    # ------------------------------------------------------------------
    # SHAPE 7: attachment/embed/sticker fallback + counted
    # (skipped under stub — stub reads content only, so these rows become empty.)
    # ------------------------------------------------------------------
    if not os.environ.get("TRANSFER_DISCORD_STUB"):
        msgs7 = [
            {"id": "1", "type": "Default", "timestamp": BASE_TS, "content": "",
             "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False},
             "attachments": [{"id": "a1", "url": "https://example.com/a.png", "fileName": "a.png", "fileSizeBytes": 123}],
             "embeds": [], "stickers": []},
            {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "",
             "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False},
             "attachments": [],
             "embeds": [{"title": "A thing", "description": "She smiles.", "url": "https://x.com/y"}],
             "stickers": []},
            {"id": "3", "type": "Default", "timestamp": BASE_TS, "content": "",
             "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False},
             "attachments": [], "embeds": [],
             "stickers": [{"id": "s1", "name": "Wave"}]},
        ]
        p7 = os.path.join(tmp, "fallback.json")
        write_json(p7, make_export(msgs7))
        meta7, out7 = R.read_discord_export(p7, her="1002", you="1001")
        check("fallback: attachment used", "a.png" in out7[0]["text"], out7[0]["text"])
        check("fallback: embed used", out7[1]["text"] == "A thing She smiles. https://x.com/y", out7[1]["text"])
        check("fallback: sticker used", out7[2]["text"] == "Wave", out7[2]["text"])
        check("fallback: counts", meta7.get("fallback_attachment") == 1 and
              meta7.get("fallback_embed") == 1 and meta7.get("fallback_sticker") == 1,
              {k: v for k, v in meta7.items() if k.startswith("fallback_")})

    # ------------------------------------------------------------------
    # SHAPE 8: system message imported with note
    # ------------------------------------------------------------------
    msgs8 = [
        {"id": "1", "type": "RecipientAdd", "timestamp": BASE_TS,
         "content": "Nell added Sage to the thread.",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "hi",
         "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}},
    ]
    p8 = os.path.join(tmp, "system.json")
    write_json(p8, make_export(msgs8))
    meta8, out8 = R.read_discord_export(p8, her="1002", you="1001")
    check("system: a system notice is set aside, NEVER imported as her words (GetFallbackContent)", len(out8) == 1 and out8[0]["who"] == "you", [(m["who"], m["text"]) for m in out8])
    check("system: counted", meta8.get("system_messages") == 1, meta8.get("system_messages"))

    # ------------------------------------------------------------------
    # SHAPE 9: cleaning integration (OOC out, *hug* byte-exact)
    # ------------------------------------------------------------------
    msgs9 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS,
         "content": "(OOC: drop this)\nI am well.",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS,
         "content": "<!-- only -->",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
    ]
    p9 = os.path.join(tmp, "clean.json")
    write_json(p9, make_export(msgs9))
    meta9, out9 = R.read_discord_export(p9, her="1002")
    check("clean: OOC line removed", "drop this" not in out9[0]["text"] and "I am well." in out9[0]["text"],
          out9[0]["text"])
    check("clean: emptied counted", meta9.get("cleaning_emptied", 0) >= 1, meta9.get("cleaning_emptied"))
    check("clean: emote untouched", out9[0]["text"] == "I am well.", out9[0]["text"])

    # ------------------------------------------------------------------
    # SHAPE 10: .txt refusal
    # ------------------------------------------------------------------
    p10 = os.path.join(tmp, "export.txt")
    with open(p10, "w", encoding="utf-8") as f:
        f.write("[2026-10-17] Sage\nHello Nell.\n")
    try:
        R.read_discord_export(p10)
        check("txt: REFUSED", False)
    except ValueError as e:
        txt = str(e)
        check("txt: REFUSED", ".txt" in txt and "JSON" in txt, txt[:200])

    # ------------------------------------------------------------------
    # SHAPE 11: single human author infers her (solo companion)
    # ------------------------------------------------------------------
    msgs11 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS, "content": "hi",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "hello",
         "author": {"id": "1002", "name": "nell_bot", "nickname": "Nell", "isBot": False}},
    ]
    p11 = os.path.join(tmp, "solo_her_only.json")
    write_json(p11, make_export(msgs11))
    # 10-17 review: her is NEVER inferred (a lone author used to be taken as her — with a companion BOT dropped, that
    # lone author was the PERSON, and his words became hers). Unnamed -> refused; named -> read.
    try:
        R.read_discord_export(p11)
        check("never inferred: unnamed her is REFUSED", False)
    except ValueError as e:
        check("never inferred: unnamed her is REFUSED", "never guess" in str(e), str(e)[:120])
    meta11, out11 = R.read_discord_export(p11, her="1002")
    check("named: her rows present", all(m["who"] == "her" for m in out11), out11)
    check("named: her_name set", meta11.get("her_name") == "Nell", meta11.get("her_name"))

    # ------------------------------------------------------------------
    # SHAPE 12: duplicate-nickname hint refuses (never first-match)
    # ------------------------------------------------------------------
    msgs12 = [
        {"id": "1", "type": "Default", "timestamp": BASE_TS, "content": "hi",
         "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}},
        {"id": "2", "type": "Default", "timestamp": BASE_TS, "content": "hello",
         "author": {"id": "1002", "name": "nell_one", "nickname": "Nell", "isBot": False}},
        {"id": "3", "type": "Default", "timestamp": BASE_TS, "content": "hey",
         "author": {"id": "1003", "name": "nell_two", "nickname": "Nell", "isBot": False}},
    ]
    p12 = os.path.join(tmp, "dupnick.json")
    write_json(p12, make_export(msgs12))
    try:
        R.read_discord_export(p12, her="nickname:Nell", you="1001")
        check("dupnick: REFUSED ambiguous hint", False)
    except ValueError as e:
        check("dupnick: REFUSED ambiguous hint",
              "1002" in str(e) and "1003" in str(e), str(e)[:120])

    # ------------------------------------------------------------------
    # SHAPE 13 (10-17 review — the main fix): a Discord companion usually IS a bot account. Named, she is her.
    # ------------------------------------------------------------------
    msgs13 = []
    for k in range(3):
        msgs13.append({"id": "u%d" % k, "type": "Default", "timestamp": BASE_TS, "content": "Evening %d." % k,
                       "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}})
        msgs13.append({"id": "b%d" % k, "type": "Reply", "timestamp": BASE_TS, "content": "*smiles* Evening %d, Sage." % k,
                       "author": {"id": "7007", "name": "elara_bot", "nickname": "Elara", "isBot": True}})
    msgs13.append({"id": "m", "type": "Default", "timestamp": BASE_TS, "content": "Now playing: lofi",
                   "author": {"id": "9001", "name": "musicbot", "nickname": "DJ", "isBot": True}})
    p13 = os.path.join(tmp, "botcompanion.json")
    write_json(p13, make_export(msgs13))
    try:
        R.read_discord_export(p13)
        check("bot companion unnamed: REFUSED with a hint naming the bots", False)
    except ValueError as e:
        check("bot companion unnamed: REFUSED, both bots listed", "7007" in str(e) and "9001" in str(e), str(e)[:160])
    meta13, out13 = R.read_discord_export(p13, her="7007")
    check("her=bot: ACCEPTED — her replies are hers", [m["who"] for m in out13 if m["name"] == "Elara"] == ["her"] * 3,
          [(m["who"], m["name"]) for m in out13])
    check("her=bot: the person is you, inferred as the one human left", [m["who"] for m in out13 if m["name"] == "Sage"] == ["you"] * 3)
    check("her=bot: Reply rows are SPEECH, kept whole", all(m["text"].startswith("*smiles*") for m in out13 if m["who"] == "her"))
    check("her=bot: the music bot is set aside and named", "DJ" in meta13.get("set_aside_speakers", []), meta13.get("set_aside_speakers"))

    # SHAPE 14 (10-17 review): a REVERSE-order export (ChannelExporter IsReverseMessageOrder) comes home in order
    msgs14 = []
    for k in range(4):
        msgs14.append({"id": "u%d" % k, "type": "Default", "timestamp": "2026-01-0%dT10:00:00+00:00" % (k + 1),
                       "content": "Mine %d." % k, "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}})
        msgs14.append({"id": "h%d" % k, "type": "Default", "timestamp": "2026-01-0%dT11:00:00+00:00" % (k + 1),
                       "content": "Hers %d." % k, "author": {"id": "7007", "name": "elara_bot", "nickname": "Elara", "isBot": True}})
    msgs14.reverse()
    p14 = os.path.join(tmp, "reverse.json")
    write_json(p14, make_export(msgs14))
    meta14, out14 = R.read_discord_export(p14, her="7007")
    check("reverse export: oldest first", out14[0]["text"] == "Mine 0." and out14[-1]["text"] == "Hers 3.",
          [m["text"] for m in out14][:3])

    # SHAPE 15 (10-17, from the exporter's own rule): system = kinds 1..18 or 46 ONLY (Message.cs:43-46). A kind outside
    # the enum is written as its bare NUMBER (Kind.ToString(), JsonMessageWriter.cs:443) — a bot companion answering a
    # slash command is kind 20, "20". Her words. A whitelist of speech kinds threw every one of them away.
    msgs15 = []
    for k in range(3):
        msgs15.append({"id": "u%d" % k, "type": "Default", "timestamp": "2026-01-0%dT10:00:00+00:00" % (k + 1),
                       "content": "/talk evening %d" % k, "author": {"id": "1001", "name": "sage_user", "nickname": "Sage", "isBot": False}})
        msgs15.append({"id": "h%d" % k, "type": "20" if k != 1 else "23", "timestamp": "2026-01-0%dT10:00:05+00:00" % (k + 1),
                       "content": "*looks up* Evening %d." % k,
                       "interaction": {"id": "i%d" % k, "name": "talk", "user": {"id": "1001", "name": "sage_user"}},
                       "author": {"id": "7007", "name": "elara_bot", "nickname": "Elara", "isBot": True}})
    for kind in ("RecipientAdd", "ChannelPinnedMessage", "12", "ThreadCreated", "PollResult", "46"):
        msgs15.append({"id": "s" + kind, "type": kind, "timestamp": "2026-01-05T00:00:00+00:00",
                       "content": "Elara pinned a message.", "author": {"id": "7007", "name": "elara_bot", "nickname": "Elara", "isBot": True}})
    p15 = os.path.join(tmp, "slash.json")
    write_json(p15, make_export(msgs15))
    meta15, out15 = R.read_discord_export(p15, her="7007")
    check("slash-command replies (kind 20 / 23, written as numbers) are HERS", [m["who"] for m in out15].count("her") == 3,
          [(m["who"], m["text"][:20]) for m in out15])
    check("every system kind (1..18 by name or number, 46) set aside and counted", meta15.get("system_messages") == 6
          and not any("pinned" in m["text"] for m in out15), meta15.get("system_messages"))

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  Discord reader proven from invented fixtures")
