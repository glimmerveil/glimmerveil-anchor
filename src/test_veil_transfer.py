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


def chat_file(path, exchanges, ghost_at=None):
    rows = [{"user_name": "Rowan", "character_name": "Marigold", "create_date": "2026-01-02@10h00m00s"}]
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
    try:
        T.build(rev, os.path.join(SCRATCH, "x.veil"))
        check("build refuses an unread card", False)
    except SystemExit as e:
        check("build refuses an unread card", "legal_ack" in str(e), str(e)[:50])

    card["legal_ack"] = True
    json.dump(card, open(os.path.join(rev, "card.json"), "w"))
    json.dump({"seed_until_message": 10}, open(os.path.join(rev, "seed.json"), "w"))
    out = os.path.join(SCRATCH, "marigold.veil")
    r = T.build(rev, out)
    snap = json.load(open(out))
    rows = snap["memory_stream"]
    check("one of her lines (an AI refusal) set aside, not imported", r["set_aside"] == 1
          and not any("language model" in x["content"] for x in rows), r["set_aside"])
    check("row 1 is her origin story", rows[0]["importance_score"] == 5)
    check("his lines 'The user said:', hers 'I said:', macros filled",
          rows[1]["content"].startswith("The user said: ") and rows[2]["content"].startswith("I said: ")
          and "{{" not in json.dumps(rows))
    check("seed floor = the 10th message's row (origin + 10)", r["seed_floor_id"] == 11, r["seed_floor_id"])
    check("no keepsakes (Law 3)", snap["keepsakes"] == [])

    import veil_roster
    ok, msg = veil_roster.import_peep(out, assume_yes=True)
    check("THE DOOR imports it", ok, msg[:60])
    folder = os.path.join(os.environ["VEIL_PEEPS"], [d for d in os.listdir(os.environ["VEIL_PEEPS"]) if d.lower().startswith("marigold")][0])
    db = sqlite3.connect(os.path.join(folder, "veil.db"))
    n = db.execute("select count(*) from memory_stream").fetchone()[0]
    fl = db.execute("select seed_floor_id from fold_state").fetchone()[0]
    first_ten = db.execute("select content from memory_stream where id <= ? order by id", (fl,)).fetchall()
    check("her memories arrive whole", n == len(rows), n)
    check("her origin is sacred: floor covers exactly origin + 10 messages", len(first_ten) == 11, fl)
    check("her card is saved beside her", os.path.isfile(os.path.join(folder, "card.json")))

    tree = ast.parse(open(os.path.join(HERE, "veil_transfer.py")).read())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    check("nothing that can reach a network (Law 1)", not mods & {"socket", "urllib", "http", "requests", "ssl"}, sorted(mods))
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  her old card and her old chat come home through the door, with you in the loop")
sys.exit(0)
