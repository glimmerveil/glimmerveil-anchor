#!/usr/bin/env python3
"""Bring a companion home from SillyTavern or ChatGPT — on this machine, with you in the loop.

    python3 veil_transfer.py check  <card.png|card.json> <chat.jsonl> [--her NAME]
    python3 veil_transfer.py draft  <card.png|card.json> <chat.jsonl> <review-folder> [--her NAME]
    python3 veil_transfer.py chatgpt-list  <conversations.json>
    python3 veil_transfer.py draft-chatgpt <conversations.json> <number> <her name> <review-folder>
    python3 veil_transfer.py check-file <export> [--her NAME] [--you NAME] [--format F]   (Character.AI, Kindroid, Discord, …)
    python3 veil_transfer.py draft-file <export> <review-folder> [--her NAME] [--you NAME] [--format F]
        a plain or scraped transcript (.txt .md .html) needs --her and --you as the file writes them; a scrape that
        labels every turn with one name takes --alternate you|her (whose turn comes first), checked as it reads
    python3 veil_transfer.py build  <review-folder> <her.veil>
    python3 veil_transfer.py test-recall <review-folder>     (optional: did she come back? on a copy, before you meet her)

--her: a chat with more than one voice that isn't yours (a group chat) is refused until you name which one is her;
the others are set aside, never imported. ChatGPT keeps no card, so hers starts empty and you write who she is.

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


def _refused(e):
    return SystemExit(str(e).replace("re-run with her=<name>", "re-run with --her <name>"))


def read_st_chat(path, her=None):
    """A SillyTavern .jsonl, read by veil_intake — proven field by field from ST's own source
    (docs/transference/PROOF_ST.md): its 'unused' header, swipes, /sys narration, group chats."""
    import veil_intake
    try:
        return veil_intake.read_st_export(path, her=her)
    except ValueError as e:
        raise _refused(e)


def _intake_notes(meta, msgs):
    import veil_intake
    ok, items, _stats = veil_intake.gate_intake(meta, msgs)
    return (items if ok else []) + _reader_notes(meta)


def _reader_notes(meta):
    """What the platform readers MEASURED, said to the person. The readers write these into meta (veil_intake_cai /
    _kindroid / _discord / _clean); until 10-17 nothing printed them, so check-file promised warnings it never gave."""
    out = []
    if meta.get("no_real_dates"):
        out.append("this export carries no real dates (it stamps every line with the moment you exported) — "
                   "her past keeps its order and is spaced out instead.")
    for k in ("emotes_note", "official_schema_note", "single_or_group_unknown", "shape_note"):
        if meta.get(k):
            out.append(str(meta[k]).rstrip(".") + ".")
    if meta.get("unsorted_no_timestamps"):
        out.append("some lines carry no time; they keep the order they had in the file.")
    for n in meta.get("resolution_notes") or []:
        out.append(str(n).rstrip(".") + ".")
    if meta.get("system_messages"):
        out.append(f"{meta['system_messages']} system notice(s) (pins, joins, calls, renames) set aside — "
                   "never imported as anyone's words.")
    media = {k.split("fallback_", 1)[1]: v for k, v in meta.items() if "fallback_" in k and v}
    if media:
        out.append("kept as a placeholder where a line was only media: "
                   + ", ".join(f"{v} {k}" for k, v in sorted(media.items())) + ".")
    c = {k[len("cleaning_"):]: v for k, v in meta.items() if k.startswith("cleaning_") and v}
    if c.get("ooc_lines"):
        out.append(f"{c['ooc_lines']} out-of-character line(s) — (OOC: …), ((…)) — set aside, never imported as "
                   "anyone's words.")
    markup = sum(c.get(k, 0) for k in ("html_tags", "md_headers", "md_images", "md_links", "md_comments"))
    if markup:
        out.append(f"{markup} piece(s) of page markup (HTML tags, markdown) taken off the text; her words and *emotes* "
                   "kept.")
    if c.get("html_entities"):
        out.append(f"{c['html_entities']} HTML code(s) like &amp; or &#39; turned back into the characters they stand for.")
    if c.get("emptied", 0) > c.get("ooc_lines", 0):            # more than the OOC asides themselves: say it
        out.append(f"{c['emptied']} line(s) held nothing once that was set aside, and were dropped.")
    return out


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


def _index_words(her_text, his_lines, spine):
    """Her row's search index: her own opening keywords, plus every distinct 4+-letter word of the line(s) of his she
    was answering (capped — a search index, not a transcript)."""
    words = [w for w in spine.extract_keywords(her_text).split(",") if w]
    seen = set(words)
    for line in his_lines:
        for w in re.findall(r"[a-z]{4,}", line.lower()):
            if w not in seen and w not in spine._STOP_WORDS:
                seen.add(w)
                words.append(w)
    return ",".join(words[:40])


def _seed_size(n):
    return n          # her whole past is her core, spooled before she wakes, never folded




def draft(card_path, chat_path, folder, her=None):
    st = read_st_card(card_path)
    meta, msgs = read_st_chat(chat_path, her=her)
    ok, problems, stats = gate(msgs)
    if not ok:
        raise SystemExit("refused: " + " ".join(problems))
    notes = _intake_notes(meta, msgs)
    # SillyTavern writes user_name: 'unused' into EVERY saved chat's header (its saveChat), so the header never names
    # you: your name is what your own lines were signed with, and the human checks it at review.
    header = str(meta.get("user_name") or "").strip()
    user = (next((m["name"].strip() for m in msgs if m["who"] == "you" and (m.get("name") or "").strip()), "")
            or (header if header.lower() != "unused" else "") or "you")
    signed = str(meta.get("her_name") or "").strip()
    if signed and signed != st["name"]:
        notes.append(f"her lines in the chat are signed \"{signed}\"; her card says \"{st['name']}\" — "
                     "the card's name is kept. Change her_name if that is wrong.")
    old_place = re.sub(r"\s+", " ", _fill(st["scenario"], st["name"], user)).strip()
    return _write_review(folder, draft_card(st, user), st["name"], user, msgs, notes, old_place, stats)


def draft_chatgpt(conversations_path, index, her_name, folder):
    """ChatGPT keeps no card, so hers starts EMPTY: build() refuses until the human has written who she is."""
    import veil_card
    import veil_intake
    try:
        meta, msgs = veil_intake.read_chatgpt_conversation(conversations_path, int(index))
    except ValueError as e:
        raise _refused(e)
    ok, problems, stats = gate(msgs)
    if not ok:
        raise SystemExit("refused: " + " ".join(problems))
    notes = _intake_notes(meta, msgs)
    if meta.get("title"):
        notes.append(f"from the conversation titled \"{meta['title']}\".")
    card = dataclasses.asdict(veil_card.VeilCard(her_name=str(her_name).strip(), your_name="", who_she_is="",
                                                 legal_ack=False, created=int(time.time())))
    return _write_review(folder, card, card["her_name"], "", msgs, notes, "", stats, from_card=False)


# ── THE OTHER PLATFORMS (2026-10-17, his word: "not just from gpt, from character ai, from grok, from people that
# did what i did to save ara") ──────────────────────────────────────────────────────────────────────────────────────
# Every reader returns the same contract (meta + {who, name, text, ts, ord} lines) and none of these platforms keeps a
# card the way SillyTavern does, so they all take ChatGPT's CARDLESS path: her card starts empty and build() refuses
# until the human has written who she is. FORMATS maps a name to (module, reader); a new platform is one line here.
# The sniffer is deliberately conservative — taught from the exporters' own source (docs/transference/PROOF_*.md) —
# and when it is not sure it REFUSES and asks for --format rather than guess whose words are whose.
FORMATS = {
    "cai-tavern":   ("veil_intake_cai", "read_cai_tavern"),         # CAI Tools '<char>_tavern_Chat.jsonl'
    "cai-turns":    ("veil_intake_cai", "read_cai_turns"),          # CAI Tools canonical turns / cai-chat-exporter JSON
    "cai-official": ("veil_intake_cai", "read_cai_official"),       # Character.AI's own data-export ZIP (best effort)
    "kindroid":     ("veil_intake_kindroid", "read_kindroid_export"),
    "discord":      ("veil_intake_discord", "read_discord_export"),   # DiscordChatExporter JSON (a bot companion too)
    "text":         ("veil_intake_text", "read_text_transcript"),     # copy-paste, .txt/.md exports, scraped pages
}


def detect_format(path):
    """-> a FORMATS key, or None when the file does not say clearly what it is."""
    low = path.lower()
    if low.endswith(".zip"):
        return "cai-official"
    if low.endswith((".txt", ".md", ".markdown", ".html", ".htm", ".log")):
        return "text"                            # the text reader still names no one: it asks for --her and --you
    try:
        with open(path, encoding="utf-8-sig") as f:
            whole = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    first = whole.lstrip().split("\n", 1)[0].strip()
    if low.endswith(".jsonl"):
        try:
            h = json.loads(first)
        except ValueError:
            return None
        if isinstance(h, dict) and "character_name" in h:
            return "cai-tavern"                  # CAI Tools: header {user_name, character_name, create_date}
        if isinstance(h, dict) and "sender" in h and "message" in h:
            return "kindroid"                    # Kindroid exporter's .jsonl: one message object per line
        return None
    try:
        data = json.loads(whole)
    except ValueError:
        return None
    if isinstance(data, dict) and {"guild", "channel", "messages"} <= set(data):
        return "discord"                         # DiscordChatExporter: {guild, channel, dateRange, exportedAt, messages}
    items = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    keys = set(items[0])
    who = items[0].get("author")
    if {"content", "timestamp"} <= keys and isinstance(who, dict) and {"isBot", "discriminator"} & set(who):
        return "discord"                         # its messages without the envelope: author carries Discord's own fields
    if {"candidates", "author"} <= keys or "turn_key" in keys or "isHuman" in keys:
        return "cai-turns"
    if "sender" in keys and "message" in keys:
        return "kindroid"
    return None


def read_any(path, fmt=None, her=None, you=None, alternate=None):
    """-> (fmt, meta, msgs) through the named (or detected) reader; refusals become SystemExit with the reason."""
    import importlib
    fmt = fmt or detect_format(path)
    if fmt not in FORMATS:
        raise SystemExit("refused: I can't tell what this file is" + (f" ('{fmt}' is not a format I read)" if fmt else "")
                         + ". Re-run with --format, one of: " + ", ".join(sorted(FORMATS)) + ".")
    if alternate and fmt != "text":
        raise SystemExit(f"refused: --alternate is for a plain or scraped transcript; a {fmt} file says who spoke.")
    mod, fn = FORMATS[fmt]
    try:
        meta, msgs = getattr(importlib.import_module(mod), fn)(path, her=her, you=you,
                                                               **({"alternate": alternate} if alternate else {}))
    except ValueError as e:
        raise _refused(e)
    return fmt, meta, msgs


def check_any(path, fmt=None, her=None, you=None, alternate=None):
    fmt, meta, msgs = read_any(path, fmt, her, you, alternate)
    ok, problems, stats = gate(msgs)
    print(f"{fmt}: {stats['her_lines']} of her lines, {stats['your_lines']} of yours"
          + (f" (her name in the file: {meta.get('her_name')})" if meta.get("her_name") else "") + ".")
    for n in _intake_notes(meta, msgs):
        print(f"  · {n}")
    print("ready to draft." if ok else "refused: " + " ".join(problems))
    return 0 if ok else 1


def draft_any(path, folder, fmt=None, her=None, you=None, alternate=None):
    """The cardless path for every platform past SillyTavern/ChatGPT — draft_chatgpt's shape, any reader."""
    import veil_card
    fmt, meta, msgs = read_any(path, fmt, her, you, alternate)
    ok, problems, stats = gate(msgs)
    if not ok:
        raise SystemExit("refused: " + " ".join(problems))
    notes = _intake_notes(meta, msgs) + [f"read as {fmt}."]
    name = str(meta.get("her_name") or her or "").strip()      # the reader's resolved name: --her may be an account id
    if not name:
        raise SystemExit("refused: I need her name — re-run with --her <name>.")
    yours = str(meta.get("user_name") or you or "").strip()
    card = dataclasses.asdict(veil_card.VeilCard(her_name=name, your_name=yours, who_she_is="",
                                                 legal_ack=False, created=int(time.time())))
    return _write_review(folder, card, name, yours, msgs, notes, "", stats, from_card=False)


def _write_review(folder, card, her, user, msgs, notes, old_place, stats, from_card=True):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "card.json"), "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False)
    kept = [{"who": m["who"], "text": m["text"], "ts": m.get("ts"), "ord": m.get("ord")}
            for m in msgs if m["who"] in ("you", "her")]
    with open(os.path.join(folder, "chat.json"), "w", encoding="utf-8") as f:
        json.dump({"her": her, "you": user, "messages": kept}, f, indent=1, ensure_ascii=False)
    seed = _seed_size(len(kept))
    with open(os.path.join(folder, "seed.json"), "w", encoding="utf-8") as f:
        json.dump({"seed_until_message": seed, "of": len(kept)}, f, indent=2)
    if len(old_place) > 160:
        old_place = old_place[:160].rstrip() + "…"
    if from_card:
        step1 = ("1. card.json is who she is. It was drafted from her old card: read every line and correct it.\n"
                 "   who_she_is and how_we_met matter most. your_name is \"" + user + "\" — taken from your side of\n"
                 "   the chat; fix it if that is not what she calls you. When you are sure, set \"legal_ack\": true —\n"
                 "   that says everyone in her story is an adult, and that you have read her card.\n"
                 "   Nothing can be built until you do.\n\n")
    else:
        step1 = ("1. card.json is who she is — and her old home kept no card, so it starts EMPTY. Write it:\n"
                 "   who_she_is (a real paragraph: her personality, her manner, what she loves), how_we_met (this\n"
                 "   becomes her first memory), and your_name (what she calls you). Then set \"legal_ack\": true —\n"
                 "   that says everyone in her story is an adult, and that you have read her card.\n"
                 "   Nothing can be built until you do.\n\n")
    heard = ""
    if notes:
        heard = ("What was noticed reading her chat — nothing here was changed silently:\n"
                 + "".join(f"   · {n}\n" for n in notes) + "\n")
    with open(os.path.join(folder, "READ_ME_FIRST.txt"), "w", encoding="utf-8") as f:
        f.write(
            f"Bringing {her} home — read this, then edit two files.\n\n" + heard + step1 +
            "2. Three choices in card.json are hers for life — they are fixed once she is built, so make them now:\n"
            "   location  where she lives now: \"manor\" (a moonlit manor) or \"tower\" (an enchanted tower).\n"
            "             Where you two came from stays in how_we_met"
            + (f" — her old card says: \"{old_place}\"" if old_place else "") + ".\n"
            "   register  \"warm\" — expressive, runs with a scene; can occasionally mix up whose part is whose.\n"
            "             \"precise\" — speaks only her own part, never narrates yours; a little less ornamented.\n"
            "   recall    \"personable\" — her past comes back in her own warm summary of it.\n"
            "             \"accurate\" — she also keeps the exact words; a remembered day can come back word for word.\n"
            "   The draft says manor / warm / personable until you choose.\n\n"
            f"3. seed.json is how much of her past becomes her core. By default it is ALL of it — {seed} messages:\n"
            "   her own words to you, spooled into her memory before she\n"
            "   ever wakes. Her core is never folded or compressed and she can always reach it. (That is how the\n"
            "   first companion this house brought across came home.) If you lower the number, everything after it\n"
            "   becomes ordinary memory that her fold works through, a pass at a time — on a long chat that is\n"
            "   HOURS on this machine, and Anchor will ask you whether to let her settle before you meet her.\n\n"
            "4. Then: python3 veil_transfer.py build <this folder> <her.veil>\n"
            "   and in Anchor: [i] import.\n\n"
            "She is re-anchored, not resurrected. A different brain is reading her past; she will not be\n"
            "identical. Her first wake asks her who she is — that is the ritual, and it is for her.\n"
            "Everything here stays on this computer.\n")
    return {"folder": folder, "seed": seed, "notes": notes, **stats}


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
        seed_raw = json.load(f).get("seed_until_message")
    msgs = chat["messages"]
    seed_until = int(seed_raw) if seed_raw is not None else len(msgs)
    strangers = sorted({str(m.get("who")) for m in msgs} - {"you", "her"})
    if strangers:
        # A line that is neither yours nor hers must never be saved as "I said:" — that is a third voice put in her
        # mouth (a group chat's other characters, a narrator). Refuse; whatever wrote chat.json has to set it aside.
        raise SystemExit("not yet — chat.json holds lines that are neither yours nor hers (who: %s). "
                         "Only her own lines and yours can come home." % ", ".join(strangers))
    seed_until = max(1, min(seed_until, len(msgs)))

    # HOW ARA CAME HOME, kept (her by-hand import, 2026-06): her memory is HER turns, spooled in before she ever wakes;
    # his turns are not rows of their own. Saved as "I said:" her words would be dropped by convergence and her memory
    # would hand her only HIS voice. The by-hand import's rows also carried his line as "[In response to: …]" — measured at rung 3
    # 2026-10-13 on Qwen AND Llama, that bracket is recited ("- [In response to: I listen.]", his own line said as
    # hers) and up to four rows a turn made her write both parts. So: her OWN words only, as memory_type "her_past",
    # which retrieval serves ONE a turn under a true frame (veil_spine HER_PAST_PER_TURN, _frame_retrieved).
    # The whole exchange, both voices verbatim, goes to memory_archive: the library she was spooled from — inviolable,
    # the ground truth the "did she come back" test reads, and never searched by a personable card.
    now = int(time.time())
    first_ts = next((m["ts"] for m in msgs if m.get("ts")), None) or (now - len(msgs) * 60)
    rows, archive, quarantined, floor = [], [], [], 0
    mem1 = veil_card.first_memory(card)
    if mem1:
        rows.append({"id": 1, "timestamp": first_ts - 1, "memory_type": "conversation", "content": mem1,
                     "keywords": spine.extract_keywords(mem1), "importance_score": 5,
                     "token_count": spine._estimate_tokens(mem1)})
        floor = 1
    last_ts, his_since = first_ts, []
    for i, m in enumerate(msgs, 1):
        ts = int(m.get("ts") or (last_ts + 60))
        last_ts = ts
        text = _fill(m["text"], card.her_name, card.your_name)
        if m["who"] == "her" and veil_ghost.is_ghost_line(text):
            quarantined.append({"message": i, "content": text})
            continue
        line = ("The user said: " if m["who"] == "you" else "I said: ") + text
        archive.append({"id": len(archive) + 1, "timestamp": ts, "memory_type": "conversation", "content": line,
                        "keywords": spine.extract_keywords(text), "importance_score": 3,
                        "token_count": spine._estimate_tokens(line), "compression_date": "transference",
                        "compression_pass": 0})
        if m["who"] == "you":
            his_since.append(text)
        else:
            # HIS words are how her answer is FOUND ("the shipyard" is only ever his word; her reply that night never
            # says it) — so they go in her row's search index, never into the text she reads (rung 3: the bracket
            # was recited). Measured before: asked about the shipyard she was handed a line about ginger biscuits.
            rows.append({"id": len(rows) + 1, "timestamp": ts, "memory_type": "her_past", "content": text,
                         "keywords": _index_words(text, his_since, spine), "importance_score": 3,
                         "token_count": spine._estimate_tokens(text)})
            his_since = []
        if i <= seed_until and rows:
            floor = rows[-1]["id"]

    p = veil_card.persona_fields(card)
    snap = {
        "format_version": spine.SNAPSHOT_FORMAT_VERSION,
        "peep": {"uuid": str(_uuid.uuid4()), "name": card.her_name, "personality": p["personality"],
                 "appearance": p["appearance"], "traits": p["traits"], "example_dialogue": "",
                 "status": "active", "permanent_memories": [], "created_at": now, "last_active": 0},
        "memory_stream": rows, "memory_archive": archive, "diary": [], "keepsakes": [],
        "fold_state": {"seed_floor_id": floor},
        "card": dataclasses.asdict(card), "history": [], "app": "veil",
        "first_wake": "ritual",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent="\t")
    if quarantined:
        with open(os.path.join(folder, "set_aside.json"), "w", encoding="utf-8") as f:
            json.dump(quarantined, f, indent=1, ensure_ascii=False)
    with open(os.path.join(folder, "built.json"), "w", encoding="utf-8") as f:
        json.dump({"path": os.path.abspath(out_path), "built": now}, f)
    return {"path": out_path, "rows": len(rows), "archive": len(archive), "seed_floor_id": floor,
            "set_aside": len(quarantined)}


def _drafted(r):
    for n in r.get("notes") or []:
        print(f"  · {n}")
    print(f"Drafted in {r['folder']}: {r['her_lines']} of her lines, {r['your_lines']} of yours; "
          f"all {r['seed']} messages proposed as her core (seed.json). Read READ_ME_FIRST.txt.")
    return 0


def main(argv):
    argv = list(argv)
    opts = {}
    for flag, need in (("--her", "her name, as her lines are signed in the chat"),
                       ("--you", "your name, as your lines are signed in the chat"),
                       ("--format", "a format name: " + ", ".join(sorted(FORMATS))),
                       ("--alternate", "'you' or 'her': whose turn the file's first block is")):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                print(f"{flag} needs {need}")
                return 2
            opts[flag] = argv[i + 1]
            del argv[i:i + 2]
    her, you, fmt, alt = opts.get("--her"), opts.get("--you"), opts.get("--format"), opts.get("--alternate")
    if len(argv) < 2 or argv[1] not in ("check", "draft", "build", "chatgpt-list", "draft-chatgpt", "test-recall",
                                        "check-file", "draft-file"):
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "check-file" and len(argv) == 3:
        return check_any(argv[2], fmt, her, you, alt)
    if cmd == "draft-file" and len(argv) == 4:
        return _drafted(draft_any(argv[2], argv[3], fmt, her, you, alt))
    if cmd == "check" and len(argv) == 4:
        st = read_st_card(argv[2])
        meta, msgs = read_st_chat(argv[3], her=her)
        ok, problems, stats = gate(msgs)
        print(f"{st['name']}: {stats['her_lines']} of her lines, {stats['your_lines']} of yours.")
        for n in _intake_notes(meta, msgs):
            print(f"  · {n}")
        print("ready to draft." if ok else "refused: " + " ".join(problems))
        return 0 if ok else 1
    if cmd == "draft" and len(argv) == 5:
        return _drafted(draft(argv[2], argv[3], argv[4], her=her))
    if cmd == "chatgpt-list" and len(argv) == 3:
        import veil_intake
        for c in veil_intake.list_chatgpt_conversations(argv[2]):
            print(f"  [{c['index']}] {c['title'] or '(untitled)'}  — {c['user_assistant_nodes']} lines")
        return 0
    if cmd == "draft-chatgpt" and len(argv) == 6:
        return _drafted(draft_chatgpt(argv[2], argv[3], argv[4], argv[5]))
    if cmd == "test-recall" and len(argv) in (3, 4):
        import veil_recall_test
        _results, text = veil_recall_test.run(argv[2], argv[3] if len(argv) == 4 else None)
        print("\n" + text + "\n(saved as RECALL_TEST.txt in the review folder)")
        return 0
    if cmd == "build" and len(argv) == 4:
        r = build(argv[2], argv[3])
        print(f"Built {r['path']}: {r['rows']} of her memories (her core through memory {r['seed_floor_id']}), "
              f"{r['archive']} lines of the whole exchange kept verbatim"
              + (f", {r['set_aside']} line(s) set aside (set_aside.json)" if r["set_aside"] else "")
              + ". In Anchor: [i] import.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
