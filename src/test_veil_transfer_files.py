#!/usr/bin/env python3
"""Rung 1 — THE OTHER PLATFORMS' DOOR (2026-10-17): detect_format + read_any + the cardless draft.

Fixtures are INVENTED content in each exporter's REAL shape, read from the exporters' own source:
  CAI Tools tavern .jsonl   irsat000/CAI-Tools @2adcba6 scripts/content.js:1260-1297 (CreateTavernChatBlob)
  cai-chat-exporter JSON    Lianne0106/cai-chat-exporter @bfec718 cai_export.py:188-199 (turns_to_json, newest first)
  Kindroid exporter         tomsegura2/Kindroid-Chat-Exporter @bae1478 app.py (JSON array; .jsonl one object per line)
  DiscordChatExporter JSON  Tyrrrz/DiscordChatExporter @276471f Core/Exporting/JsonMessageWriter.cs (WritePreambleAsync,
                            WriteUserAsync: {guild, channel, dateRange, exportedAt, messages, messageCount})
The sniffer must name each shape, and must REFUSE (None -> a --format hint) on anything it cannot place — it never
guesses whose words are whose.
  python3 test_veil_transfer_files.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_transfer as T  # noqa: E402

PASS, FAIL = [], []
_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
TMP = tempfile.mkdtemp(prefix="vt_files_", dir=_CACHE if os.path.isdir(_CACHE) else None)


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail else ""))


def put(name, text):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


tavern = "\n".join(json.dumps(x) for x in (
    {"user_name": "You", "character_name": "Elara", "create_date": 1760000000000},
    {"name": "You", "is_user": True, "is_name": True, "send_date": 1760000000001, "mes": "Hey, you."},
    {"name": "Elara", "is_user": False, "is_name": True, "send_date": 1760000000002, "mes": "*smiles* There you are."}))
neo = json.dumps({"chat_id": "c1", "exported_at": "2026-10-17T00:00:00+00:00", "message_count": 2, "messages": [
    {"turn_key": {"chat_id": "c1", "turn_id": "t2"}, "create_time": "2026-01-02T00:00:01Z",
     "author": {"author_id": "9", "name": "Elara", "is_human": False}, "primary_candidate_id": "x2",
     "candidates": [{"candidate_id": "x2", "raw_content": "*smiles* There you are.", "is_final": True}]},
    {"turn_key": {"chat_id": "c1", "turn_id": "t1"}, "create_time": "2026-01-02T00:00:00Z",
     "author": {"author_id": "1", "name": "Sam", "is_human": True}, "primary_candidate_id": "x1",
     "candidates": [{"candidate_id": "x1", "raw_content": "Hey, you.", "is_final": True}]}]})
canonical = json.dumps([{"name": "Sam", "message": "Hey, you.", "isHuman": True},
                        {"name": "Elara", "message": "*smiles* There you are.", "isHuman": False}])
kindroid = json.dumps([{"display_name": "Sam", "id": "a", "sender": "user", "timestamp": 1760000000000, "message": "Hey."},
                       {"display_name": "Lisa", "id": "b", "sender": "ai", "timestamp": 1760000060000, "message": "*waves*"}])
kindroid_l = "\n".join(json.dumps(x) for x in json.loads(kindroid))
_dauth = lambda i, n, bot: {"id": i, "name": n, "discriminator": "0000", "nickname": n, "color": None, "isBot": bot}
_dmsgs = [{"id": "1", "type": "Default", "timestamp": "2026-01-02T00:00:00+00:00", "content": "hey, you",
           "author": _dauth("100", "sam", False)},
          {"id": "2", "type": "Default", "timestamp": "2026-01-02T00:00:05+00:00", "content": "*smiles* there you are",
           "author": _dauth("200", "Elara", True)}]
discord = json.dumps({"guild": {"id": "0", "name": "Direct Messages"}, "channel": {"id": "9", "type": "DirectTextChat"},
                      "dateRange": {"after": None, "before": None}, "exportedAt": "2026-10-17T00:00:00+00:00",
                      "messages": _dmsgs, "messageCount": 2})

print("\nRUNG 1 — THE OTHER PLATFORMS' DOOR")
check("CAI Tools tavern .jsonl -> cai-tavern", T.detect_format(put("Elara_tavern_Chat.jsonl", tavern)) == "cai-tavern")
check("cai-chat-exporter JSON wrapper (newest first) -> cai-turns", T.detect_format(put("chat.json", neo)) == "cai-turns")
check("CAI canonical turns array -> cai-turns", T.detect_format(put("canon.json", canonical)) == "cai-turns")
check("Kindroid exporter JSON array -> kindroid", T.detect_format(put("Lisa_Chat_Export_20261017.json", kindroid)) == "kindroid")
check("Kindroid exporter .jsonl -> kindroid", T.detect_format(put("lisa.jsonl", kindroid_l)) == "kindroid")
check("DiscordChatExporter JSON (its guild/channel envelope) -> discord",
      T.detect_format(put("Direct Messages - Elara [9].json", discord)) == "discord")
check("Discord messages without the envelope -> discord (author carries isBot/discriminator)",
      T.detect_format(put("dm_msgs.json", json.dumps(_dmsgs))) == "discord")
check("a CAI turn is never mistaken for Discord (both have an 'author')",
      T.detect_format(put("chat2.json", neo)) == "cai-turns")
check("a .zip is Character.AI's own data export", T.detect_format(put("export.zip", "PK")) == "cai-official")
check("an unknown JSON shape is NOT guessed", T.detect_format(put("odd.json", json.dumps([{"who": "x", "said": "y"}]))) is None)
check("a .txt / .md / .html is a transcript -> text", [T.detect_format(put(n, "Sam: hey\nElara: hi\n")) for n in
      ("chat.txt", "chat.md", "page.html")] == ["text"] * 3)
try:
    T.read_any(put("chat2.txt", "Sam: hey\nElara: hi\nSam: so\nElara: yes\n"))
    check("…and the text reader still names no one: REFUSED, the voices listed", False, "no refusal")
except SystemExit as e:
    check("…and the text reader still names no one: REFUSED, the voices listed", "Sam" in str(e) and "Elara" in str(e),
          str(e))
try:
    T.read_any(put("Elara_alt_tavern_Chat.jsonl", tavern), alternate="you")
    check("--alternate on a file that says who spoke is REFUSED", False, "no refusal")
except SystemExit as e:
    check("--alternate on a file that says who spoke is REFUSED", "--alternate" in str(e), str(e))
check("garbage is NOT guessed", T.detect_format(put("x.json", "{not json")) is None)
try:
    T.read_any(put("odd2.json", json.dumps([{"who": "x"}])))
    check("read_any on an unknown file REFUSES with a --format hint", False, "no refusal")
except SystemExit as e:
    check("read_any on an unknown file REFUSES with a --format hint", "--format" in str(e) and "cai-tavern" in str(e), str(e))
try:
    T.read_any(put("odd3.json", "[]"), fmt="myspace")
    check("an unknown --format is refused by name", False)
except SystemExit as e:
    check("an unknown --format is refused by name", "myspace" in str(e), str(e))
# The readers MEASURE (no real dates, OOC set aside, system notices) — the door must SAY it (10-17: it said nothing).
import io, contextlib  # noqa: E402
ooc = "\n".join(json.dumps(x) for x in (
    [{"user_name": "You", "character_name": "Elara", "create_date": 1760000000000}]
    + [r for i in range(12) for r in (
        {"name": "You", "is_user": True, "is_name": True, "send_date": 1760000000000 + 3 * i, "mes": f"Evening {i}."},
        {"name": "You", "is_user": True, "is_name": True, "send_date": 1760000000001 + 3 * i, "mes": "(OOC: brb)"},
        {"name": "Elara", "is_user": False, "is_name": True, "send_date": 1760000000002 + 3 * i, "mes": f"*smiles* {i}."})]))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    T.check_any(put("Elara_ooc_tavern_Chat.jsonl", ooc), her="Elara")
said = buf.getvalue()
check("check-file SAYS a CAI Tools export has no real dates", "no real dates" in said, said[-300:])
check("check-file SAYS how many OOC lines were set aside", "12 out-of-character" in said, said[-300:])
_dsys = _dmsgs + [{"id": "3", "type": "ChannelPinnedMessage", "timestamp": "2026-01-02T00:00:09+00:00", "content": "",
                   "author": _dauth("200", "Elara", True)}]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    T.check_any(put("dm_sys.json", json.dumps({"guild": {}, "channel": {}, "messages": _dsys})), her="200", you="100")
said = buf.getvalue()
check("check-file SAYS a Discord system notice was set aside", "1 system notice" in said, said[-300:])

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    T.check_any(put("Lisa_notes.json", json.dumps(json.loads(kindroid) * 12)), her="Lisa", you="Sam")
said = buf.getvalue()
check("a reader's INTERNAL tags never reach the person (no '· json_array.')",
      not any(l.strip() in ("· json_array.", "· jsonl.") for l in said.splitlines()), said)

check("main() knows check-file / draft-file and documents them",
      "check-file" in (T.__doc__ or "") and "draft-file" in (T.__doc__ or ""))

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAILED:", f)
sys.exit(1 if FAIL else 0)
