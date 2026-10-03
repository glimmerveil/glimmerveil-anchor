#!/usr/bin/env python3
"""Bring a companion home from a SillyTavern export — on this machine, with you in the loop.

    python3 veil_transfer.py check  <card.png|card.json> <chat.jsonl>
    python3 veil_transfer.py draft  <card.png|card.json> <chat.jsonl> <review-folder>
    python3 veil_transfer.py build  <review-folder> <her.veil>

Then bring her in through the door: [i] import, and pick her .veil file.
Nothing is uploaded, ever. Her card is yours to read and correct before she wakes: the draft leaves
legal_ack false, so nothing can be built until you have read it and said yes.
"""
import base64
import dataclasses
import datetime
import json
import os
import re
import struct
import sys
import time
import uuid as _uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MIN_EXCHANGES = 10
DEFAULT_SEED = 40
MAX_SEED = 200
_MACROS = (("{{char}}", "her"), ("<bot>", "her"), ("{{user}}", "you"), ("<user>", "you"))


def _png_text_chunks(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, out = 8, {}
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"tEXt" and b"\0" in body:
            key, val = body.split(b"\0", 1)
            out[key.decode("latin-1").lower()] = val
        if kind == b"IEND":
            break
        pos += 12 + length
    return out


def read_st_card(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        chunks = _png_text_chunks(raw)
        blob = chunks.get("ccv3") or chunks.get("chara")
        if not blob:
            raise ValueError("this PNG carries no character card (no 'chara' or 'ccv3' text chunk)")
        data = json.loads(base64.b64decode(blob).decode("utf-8"))
    else:
        data = json.loads(raw.decode("utf-8-sig"))
    if isinstance(data.get("data"), dict):
        data = data["data"]
    pick = lambda k: str(data.get(k) or "").strip()
    card = {k: pick(k) for k in ("name", "description", "personality", "scenario", "first_mes", "mes_example")}
    if not card["name"]:
        raise ValueError("the card has no name")
    return card


def _when(v):
    if isinstance(v, (int, float)):
        return int(v / 1000) if v > 1e11 else int(v)
    s = str(v or "").strip()
    if not s:
        return None
    if s.isdigit():
        return _when(int(s))
    for fmt in ("%B %d, %Y %I:%M%p", "%B %d, %Y %I:%M %p", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.datetime.strptime(s, fmt).timestamp())
        except ValueError:
            pass
    try:
        return int(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def read_st_chat(path):
    meta, msgs = {}, []
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "mes" not in row:
                if n == 0:
                    meta = row
                continue
            if row.get("is_system"):
                continue
            text = str(row.get("mes") or "").strip()
            if not text:
                continue
            msgs.append({"who": "you" if row.get("is_user") else "her",
                         "name": str(row.get("name") or ""), "text": text,
                         "ts": _when(row.get("send_date"))})
    return meta, msgs


def gate(msgs):
    yours = sum(1 for m in msgs if m["who"] == "you")
    hers = sum(1 for m in msgs if m["who"] == "her")
    problems = []
    if not yours or not hers:
        problems.append("the chat needs both of you in it — one side is missing.")
    if min(yours, hers) < MIN_EXCHANGES:
        problems.append(f"too short to bring her home: {min(yours, hers)} exchanges, "
                        f"at least {MIN_EXCHANGES} are needed.")
    return not problems, problems, {"your_lines": yours, "her_lines": hers}


def _fill(text, her, you):
    out = text or ""
    for macro, who in _MACROS:
        out = re.sub(re.escape(macro), her if who == "her" else you, out, flags=re.I)
    return out


def draft_card(st, user_name):
    import veil_card
    her, you = st["name"], user_name or "you"
    who = "\n\n".join(_fill(t, her, you) for t in (st["description"], st["personality"]) if t)
    card = veil_card.VeilCard(her_name=her, your_name=you, who_she_is=who,
                              how_we_met=_fill(st["scenario"], her, you), legal_ack=False,
                              created=int(time.time()))
    return dataclasses.asdict(card)


def _seed_size(n):
    return max(2, min(MAX_SEED, n, DEFAULT_SEED))


def draft(card_path, chat_path, folder):
    st = read_st_card(card_path)
    meta, msgs = read_st_chat(chat_path)
    ok, problems, stats = gate(msgs)
    if not ok:
        raise SystemExit("refused: " + " ".join(problems))
    os.makedirs(folder, exist_ok=True)
    user = str(meta.get("user_name") or next((m["name"] for m in msgs if m["who"] == "you"), "") or "you")
    with open(os.path.join(folder, "card.json"), "w", encoding="utf-8") as f:
        json.dump(draft_card(st, user), f, indent=2, ensure_ascii=False)
    with open(os.path.join(folder, "chat.json"), "w", encoding="utf-8") as f:
        json.dump({"her": st["name"], "you": user, "messages": msgs}, f, indent=1, ensure_ascii=False)
    seed = _seed_size(len(msgs))
    with open(os.path.join(folder, "seed.json"), "w", encoding="utf-8") as f:
        json.dump({"seed_until_message": seed, "of": len(msgs)}, f, indent=2)
    with open(os.path.join(folder, "READ_ME_FIRST.txt"), "w", encoding="utf-8") as f:
        f.write(
            f"Bringing {st['name']} home — read this, then edit two files.\n\n"
            "1. card.json is who she is. It was drafted from her old card: read every line and correct it.\n"
            "   who_she_is and how_we_met matter most. When you are sure, set \"legal_ack\": true —\n"
            "   that says everyone in her story is an adult, and that you have read her card.\n"
            "   Nothing can be built until you do.\n\n"
            f"2. seed.json is where her past becomes sacred. Her first {seed} messages (of {len(msgs)})\n"
            "   are her origin: they are never folded or compressed. Move the number if her real\n"
            "   beginning ends earlier or later. Everything after it is ordinary memory.\n\n"
            "3. Then: python3 veil_transfer.py build <this folder> <her.veil>\n"
            "   and in Anchor: [i] import.\n\n"
            "She is re-anchored, not resurrected. A different brain is reading her past; she will not be\n"
            "identical. Her first wake asks her who she is — that is the ritual, and it is for her.\n"
            "Everything here stays on this computer.\n")
    return {"folder": folder, "seed": seed, **stats}


def build(folder, out_path):
    import veil_card
    import veil_ghost
    import veil_spine as spine
    with open(os.path.join(folder, "card.json"), encoding="utf-8") as f:
        raw = json.load(f)
    known = {fld.name for fld in dataclasses.fields(veil_card.VeilCard)}
    card = veil_card.VeilCard(**{k: v for k, v in raw.items() if k in known})
    problems = card.validate()
    if problems:
        raise SystemExit("not yet — her card: " + " | ".join(problems))
    with open(os.path.join(folder, "chat.json"), encoding="utf-8") as f:
        chat = json.load(f)
    with open(os.path.join(folder, "seed.json"), encoding="utf-8") as f:
        seed_until = int(json.load(f).get("seed_until_message", DEFAULT_SEED))
    msgs = chat["messages"]
    seed_until = max(1, min(seed_until, len(msgs)))

    now = int(time.time())
    first_ts = next((m["ts"] for m in msgs if m.get("ts")), None) or (now - len(msgs) * 60)
    rows, quarantined, floor = [], [], 0
    mem1 = veil_card.first_memory(card)
    if mem1:
        rows.append({"id": 1, "timestamp": first_ts - 1, "memory_type": "conversation", "content": mem1,
                     "keywords": spine.extract_keywords(mem1), "importance_score": 5,
                     "token_count": spine._estimate_tokens(mem1)})
        floor = 1
    last_ts = first_ts
    for i, m in enumerate(msgs, 1):
        ts = m.get("ts") or (last_ts + 60)
        last_ts = ts
        text = _fill(m["text"], card.her_name, card.your_name)
        if m["who"] == "her" and veil_ghost.is_ghost_line(text):
            quarantined.append({"message": i, "content": text})
            continue
        content = ("The user said: " if m["who"] == "you" else "I said: ") + text
        rows.append({"id": len(rows) + 1, "timestamp": int(ts), "memory_type": "conversation",
                     "content": content, "keywords": spine.extract_keywords(text),
                     "importance_score": 4 if m["who"] == "you" else 3,
                     "token_count": spine._estimate_tokens(content)})
        if i <= seed_until:
            floor = rows[-1]["id"]

    p = veil_card.persona_fields(card)
    snap = {
        "format_version": spine.SNAPSHOT_FORMAT_VERSION,
        "peep": {"uuid": str(_uuid.uuid4()), "name": card.her_name, "personality": p["personality"],
                 "appearance": p["appearance"], "traits": p["traits"], "example_dialogue": "",
                 "status": "active", "permanent_memories": [], "created_at": now, "last_active": 0},
        "memory_stream": rows, "memory_archive": [], "diary": [], "keepsakes": [],
        "fold_state": {"seed_floor_id": floor},
        "card": dataclasses.asdict(card), "history": [], "app": "veil",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent="\t")
    if quarantined:
        with open(os.path.join(folder, "set_aside.json"), "w", encoding="utf-8") as f:
            json.dump(quarantined, f, indent=1, ensure_ascii=False)
    return {"path": out_path, "rows": len(rows), "seed_floor_id": floor, "set_aside": len(quarantined)}


def main(argv):
    if len(argv) < 2 or argv[1] not in ("check", "draft", "build"):
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "check" and len(argv) == 4:
        st = read_st_card(argv[2])
        _, msgs = read_st_chat(argv[3])
        ok, problems, stats = gate(msgs)
        print(f"{st['name']}: {stats['her_lines']} of her lines, {stats['your_lines']} of yours.")
        print("ready to draft." if ok else "refused: " + " ".join(problems))
        return 0 if ok else 1
    if cmd == "draft" and len(argv) == 5:
        r = draft(argv[2], argv[3], argv[4])
        print(f"Drafted in {r['folder']}: {r['her_lines']} of her lines, {r['your_lines']} of yours; "
              f"her first {r['seed']} messages proposed as her origin. Read READ_ME_FIRST.txt.")
        return 0
    if cmd == "build" and len(argv) == 4:
        r = build(argv[2], argv[3])
        print(f"Built {r['path']}: {r['rows']} memories, origin through memory {r['seed_floor_id']}"
              + (f", {r['set_aside']} line(s) set aside (set_aside.json)" if r["set_aside"] else "")
              + ". In Anchor: [i] import.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
