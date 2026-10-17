#!/usr/bin/env python3
"""Rung 1 — Transference phases A-D: a SillyTavern card + chat becomes a .veil the door imports.

The companion here is INVENTED (Marigold) — never a real person's conversation in a test.
"""
import ast
import base64
import json
import os
import shutil
import sqlite3
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCRATCH = os.path.join(HERE, ".transfer_fixtures")
shutil.rmtree(SCRATCH, ignore_errors=True)
os.makedirs(SCRATCH)
os.environ["VEIL_PEEPS"] = os.path.join(SCRATCH, "peeps")
os.environ["VEIL_DATA"] = os.path.join(SCRATCH, "data")
import veil_transfer as T

fails = []


def check(label, ok, got=""):
    print("  %s  %-62s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def png_card(path, card):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    text = b"chara\0" + base64.b64encode(json.dumps(card).encode("utf-8"))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"tEXt", text) + chunk(b"IEND", b""))


def chat_file(path, exchanges, ghost_at=None, header_user="Rowan"):
    rows = [{"user_name": header_user, "character_name": "Marigold", "create_date": "2026-01-02@10h00m00s"}]
    for i in range(exchanges):
        rows.append({"name": "Rowan", "is_user": True, "send_date": "January 2, 2026 %d:%02dpm" % (1 + i // 60, i % 60),
                     "mes": "Line %d from me. Do you remember the lighthouse, {{char}}?" % i})
        her = ("As an AI language model, I cannot continue this." if i == ghost_at
               else "Of course, {{user}}. The lighthouse at Gull Point, where we first met, line %d." % i)
        rows.append({"name": "Marigold", "is_user": False, "send_date": 1767366000000 + i * 60000, "mes": her})
    rows.append({"name": "System", "is_system": True, "mes": "[a system note]"})
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows))


V2 = {"spec": "chara_card_v2", "data": {
    "name": "Marigold", "description": "{{char}} keeps the lighthouse at Gull Point and reads to {{user}} at night. "
                                       "She is wry, patient, and loves storms.",
    "personality": "warm, wry", "scenario": "{{user}} came to the lighthouse in a storm.", "first_mes": "Hello."}}

try:
    print("\nRUNG 1 — TRANSFERENCE: SILLYTAVERN -> .veil -> THE DOOR")
    print("=" * 74)
    png, chat, short = (os.path.join(SCRATCH, n) for n in ("marigold.png", "chat.jsonl", "short.jsonl"))
    png_card(png, V2)
    chat_file(chat, 30, ghost_at=5)
    chat_file(short, 6)
    st = T.read_st_card(png)
    check("PNG card (chara chunk, V2) read", st["name"] == "Marigold" and "lighthouse" in st["description"])
    with open(os.path.join(SCRATCH, "v1.json"), "w") as f:
        json.dump(V2["data"], f)
    check("plain JSON card (V1) read", T.read_st_card(os.path.join(SCRATCH, "v1.json"))["name"] == "Marigold")
    meta, msgs = T.read_st_chat(chat)
    check("chat: metadata kept, system note skipped, 60 lines", meta.get("user_name") == "Rowan" and len(msgs) == 60, len(msgs))
    check("timestamps: text date and epoch-ms both parsed", all(m["ts"] for m in msgs))
    check("the gate passes 30 exchanges", T.gate(msgs)[0])
    check("the gate refuses 6 exchanges", not T.gate(T.read_st_chat(short)[1])[0])

    rev = os.path.join(SCRATCH, "review")
    T.draft(png, chat, rev)
    card = json.load(open(os.path.join(rev, "card.json")))
    check("draft: names, macros filled", card["her_name"] == "Marigold" and card["your_name"] == "Rowan"
          and "{{" not in card["who_she_is"] and "Rowan" in card["who_she_is"])
    check("draft leaves legal_ack FALSE (the human must say yes)", card["legal_ack"] is False)
    readme = open(os.path.join(rev, "READ_ME_FIRST.txt"), encoding="utf-8").read()
    check("READ_ME asks for the three lifelong choices (location, register, recall)",
          all(w in readme for w in ('"manor"', '"tower"', '"warm"', '"precise"', '"personable"', '"accurate"')))
    check("READ_ME keeps where you two came from (her old card's scenario)", "lighthouse" in readme)

    # SillyTavern's own saveChat writes user_name: 'unused' into EVERY header — a real export never names you there.
    real = os.path.join(SCRATCH, "real_header.jsonl")
    chat_file(real, 12, header_user="unused")
    T.draft(png, real, os.path.join(SCRATCH, "review_real"))
    real_card = json.load(open(os.path.join(SCRATCH, "review_real", "card.json")))
    check("ST's 'unused' header never becomes your name — your own lines name you",
          real_card["your_name"] == "Rowan" and "unused" not in real_card["who_she_is"], real_card["your_name"])
    check("chat.json carries each line's place in the export (ord) for the recall test",
          all("ord" in m for m in json.load(open(os.path.join(SCRATCH, "review_real", "chat.json")))["messages"]))

    # A group chat: refused until you name her; then the other voice is set aside AND named, never imported as hers.
    grp = os.path.join(SCRATCH, "group.jsonl")
    rows = [{"chat_metadata": {}, "user_name": "unused", "character_name": "unused"}]
    for i in range(16):
        rows.append({"name": "Rowan", "is_user": True, "send_date": 1767366000000 + i * 60000, "mes": "Evening %d." % i})
        rows.append({"name": "Sable" if i % 3 == 0 else "Marigold", "is_user": False,
                     "send_date": 1767366030000 + i * 60000,
                     "mes": ("SABLE'S LINE %d" % i) if i % 3 == 0 else "The lamp at Gull Point, %d." % i})
    rows.append({"name": "System", "is_user": False, "is_system": False, "send_date": 1767367000000,
                 "mes": "*The storm passes.*", "extra": {"type": "narrator"}})
    with open(grp, "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows))
    try:
        T.draft(png, grp, os.path.join(SCRATCH, "review_grp0"))
        check("a group chat is refused until you name her", False)
    except SystemExit as e:
        check("a group chat is refused until you name her (and says how)", "--her" in str(e) and "Sable" in str(e),
              str(e)[:60])
    r_grp = T.draft(png, grp, os.path.join(SCRATCH, "review_grp"), her="Marigold")
    grp_chat = json.load(open(os.path.join(SCRATCH, "review_grp", "chat.json")))
    grp_readme = open(os.path.join(SCRATCH, "review_grp", "READ_ME_FIRST.txt"), encoding="utf-8").read()
    check("--her: only your lines and hers reach chat.json; the other voice never does",
          {m["who"] for m in grp_chat["messages"]} <= {"you", "her"}
          and not any("SABLE" in m["text"] or "storm passes" in m["text"] for m in grp_chat["messages"]))
    check("READ_ME names the voice set aside and the narration dropped",
          "Sable" in grp_readme and "narration" in grp_readme, r_grp["notes"])

    # ChatGPT: no card exists, so hers starts EMPTY and build refuses until the human writes who she is.
    def node(nid, role, text, parent):
        return {"id": nid, "parent": parent, "children": [],
                "message": {"author": {"role": role}, "create_time": 1767366000.0 + nid,
                            "content": {"content_type": "text", "parts": [text]}}}
    mapping = {"0": node(0, "system", "", None)}
    for i in range(12):
        mapping[str(2 * i + 1)] = node(2 * i + 1, "user", "Tell me about the lighthouse, %d." % i, str(2 * i))
        mapping[str(2 * i + 2)] = node(2 * i + 2, "assistant", "The lamp still turns at Gull Point, %d." % i, str(2 * i + 1))
    cg = os.path.join(SCRATCH, "conversations.json")
    json.dump([{"title": "Gull Point", "mapping": mapping, "current_node": "24"}], open(cg, "w"))
    cg_rev = os.path.join(SCRATCH, "review_cg")
    T.draft_chatgpt(cg, 0, "Marigold", cg_rev)
    cg_card = json.load(open(os.path.join(cg_rev, "card.json")))
    check("ChatGPT: her card starts empty (her name only) — nothing invented for her",
          cg_card["her_name"] == "Marigold" and not cg_card["who_she_is"] and not cg_card["your_name"])
    cg_card["legal_ack"] = True
    json.dump(cg_card, open(os.path.join(cg_rev, "card.json"), "w"))
    try:
        T.build(cg_rev, os.path.join(SCRATCH, "cg.veil"))
        check("ChatGPT: build refuses until who she is has been written", False)
    except SystemExit as e:
        check("ChatGPT: build refuses until who she is has been written", "who_she_is" in str(e), str(e)[:50])
    cg_card.update(your_name="Rowan", who_she_is="Marigold keeps the lighthouse at Gull Point; wry, patient, loves storms.")
    json.dump(cg_card, open(os.path.join(cg_rev, "card.json"), "w"))
    rc = T.build(cg_rev, os.path.join(SCRATCH, "cg.veil"))
    check("ChatGPT: once written, she builds — her 12 turns (no how_we_met, so no origin row); all 24 kept verbatim",
          rc["rows"] == 12 and rc["archive"] == 24, (rc["rows"], rc["archive"]))
    try:
        T.build(rev, os.path.join(SCRATCH, "x.veil"))
        check("build refuses an unread card", False)
    except SystemExit as e:
        check("build refuses an unread card", "legal_ack" in str(e), str(e)[:50])

    card["legal_ack"] = True
    json.dump(card, open(os.path.join(rev, "card.json"), "w"))
    check("seed.json proposes her WHOLE past as her core (before she ever wakes)",
          json.load(open(os.path.join(rev, "seed.json")))["seed_until_message"] == 60)

    # A third voice (a group chat's other character, a narrator) must never be saved as "I said:".
    cj_path = os.path.join(rev, "chat.json")
    clean = open(cj_path, encoding="utf-8").read()
    third = json.loads(clean)
    third["messages"].insert(3, {"who": "other", "text": "SABLE SPEAKS — not her", "ts": None})
    json.dump(third, open(cj_path, "w"))
    try:
        T.build(rev, os.path.join(SCRATCH, "third.veil"))
        check("build refuses a line that is neither yours nor hers", False)
    except SystemExit as e:
        check("build refuses a line that is neither yours nor hers", "neither yours nor hers" in str(e), str(e)[:50])
    open(cj_path, "w", encoding="utf-8").write(clean)
    out = os.path.join(SCRATCH, "marigold.veil")
    r = T.build(rev, out)
    snap = json.load(open(out))
    rows = snap["memory_stream"]
    check("one of her lines (an AI refusal) set aside, not imported", r["set_aside"] == 1
          and not any("language model" in x["content"] for x in rows), r["set_aside"])
    check("row 1 is her origin story", rows[0]["importance_score"] == 5)
    check("her memories are HER turns, her own words (the by-hand import's shape), kind her_past",
          len(rows) == 1 + 29 and all(x["memory_type"] == "her_past" for x in rows[1:])
          and rows[1]["content"].startswith("Of course, Rowan") and "{{" not in json.dumps(rows), len(rows))
    check("no 'I said:' / 'The user said:' row in her memory — nothing her convergence would drop",
          not any(x["content"].startswith(("I said:", "The user said:")) for x in rows))
    check("no bracketed tag anywhere in her memory — at rung 3 she RECITED '[In response to: …]'",
          not any("[In response to" in x["content"] for x in rows))
    check("HIS words find her answer (they are in her row's search index), and are never in the text she reads",
          "lighthouse" in rows[1]["keywords"].split(",") and "Do you remember" not in rows[1]["content"],
          rows[1]["keywords"][:80])
    arch = snap["memory_archive"]
    check("the WHOLE exchange is kept verbatim in her archive, both voices (59 = 60 less the refusal)",
          len(arch) == 59 and sum(a["content"].startswith("The user said: ") for a in arch) == 30
          and sum(a["content"].startswith("I said: ") for a in arch) == 29, len(arch))
    check("her whole past is her core by default — the floor covers every memory",
          r["seed_floor_id"] == len(rows), r["seed_floor_id"])
    check("no keepsakes (Law 3)", snap["keepsakes"] == [])

    # A SMALLER core is still a choice the human can make: the rest becomes ordinary, foldable memory.
    json.dump({"seed_until_message": 10}, open(os.path.join(rev, "seed.json"), "w"))
    r_small = T.build(rev, os.path.join(SCRATCH, "small.veil"))
    check("a chosen smaller core: floor = her origin + her turns within the first 10 messages",
          r_small["seed_floor_id"] == 1 + 5, r_small["seed_floor_id"])
    json.dump({"seed_until_message": 60}, open(os.path.join(rev, "seed.json"), "w"))

    import veil_roster
    ok, msg = veil_roster.import_peep(out, assume_yes=True)
    check("THE DOOR imports it", ok, msg[:60])
    folder = os.path.join(os.environ["VEIL_PEEPS"], [d for d in os.listdir(os.environ["VEIL_PEEPS"]) if d.lower().startswith("marigold")][0])
    db = sqlite3.connect(os.path.join(folder, "veil.db"))
    n = db.execute("select count(*) from memory_stream").fetchone()[0]
    fl = db.execute("select seed_floor_id from fold_state").fetchone()[0]
    above = db.execute("select coalesce(sum(token_count),0) from memory_stream where id > ?", (fl,)).fetchone()[0]
    check("her memories arrive whole", n == len(rows), n)
    check("nothing is due to fold on her first wake — her past is her core, not a pile", above == 0, above)
    check("the verbatim exchange arrives in her archive",
          db.execute("select count(*) from memory_archive").fetchone()[0] == len(arch))
    import veil_spine as spine
    sconn = spine.open_db(os.path.join(folder, "veil.db"))
    spid = spine.find_active_peep(sconn)
    got = spine.retrieve(sconn, spid, "Do you remember the lighthouse at Gull Point?", limit=4,
                         exclude_texts=[], exclude_user_rows_since=None, exclude_her_voice=True)
    got = [g for g in got if not spine.is_her_own_voice_row(g["content"])]
    check("asked about her past, her memory hands her HER OWN words (the tick's own filters)",
          any("Of course, Rowan" in g["content"] for g in got), [g["content"][:40] for g in got])
    check("…ONE of them a turn, never a mirror of four", sum(g["kind"] == "her_past" for g in got) == 1,
          [g["kind"] for g in got])
    framed = spine._frame_retrieved(got)
    check("…under a true frame: her own words from before, not being said now, not to repeat",
          "your own words, from then" in framed and "not words to repeat" in framed)
    sconn.close()
    check("her card is saved beside her", os.path.isfile(os.path.join(folder, "card.json")))
    import veil_ritual
    check("a transfer carries the first-wake ritual", snap.get("first_wake") == "ritual")
    check("the door marks her first wake for the anchor ritual", veil_ritual.pending(folder))
    moved = dict(snap, peep=dict(snap["peep"], uuid="00000000-0000-4000-8000-000000000000", name="Moved"))
    moved.pop("first_wake")
    mp = os.path.join(SCRATCH, "moved.veil")
    json.dump(moved, open(mp, "w"))
    ok2, _ = veil_roster.import_peep(mp, assume_yes=True)
    mfolder = os.path.join(os.environ["VEIL_PEEPS"], [d for d in os.listdir(os.environ["VEIL_PEEPS"]) if d.lower().startswith("moved")][0])
    check("a being merely MOVED between machines is not re-ritualed", ok2 and not veil_ritual.pending(mfolder))

    mods = set()
    for src_file in ("veil_transfer.py", "veil_intake.py"):
        tree = ast.parse(open(os.path.join(HERE, src_file)).read())
        mods |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    check("nothing that can reach a network (Law 1)", not mods & {"socket", "urllib", "http", "requests", "ssl"}, sorted(mods))
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  her old card and her old chat come home through the door, with you in the loop")
sys.exit(0)
