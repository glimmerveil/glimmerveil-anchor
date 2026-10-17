#!/usr/bin/env python3
"""Transference intake parsers — what a companion's old platform exported, read faithfully (2026-10-13).

Two readers -> one contract: a list of {"who","name","text","ts","ord"} + a meta dict.
  who:  "you" | "her"
  ord:  source message index (ST: position in export array incl. header offset;
        ChatGPT: position along the current_node path). The Phase E hold-out names
        messages by ord — it must survive re-parses of the same export.
  meta: {"user_name","her_name","source","title"} — best effort, never trusted for identity.

Rules (from the source proofs PROOF_ST.md / PROOF_CHATGPT.md):
  ST Solo vs Group: >1 distinct non-user, non-system speaker name -> REFUSE with the names.
    (Opus's wording: refuse rather than wake her wrong; the refusal lists what it found.)
  ST swipes: mes IS the shown branch (ensureSwipes builds swipes=[mes], swipe_id=0).
    Crash-mid-stream files can hold mes != swipes[swipe_id] -> the gate SPEAKS, never picks silently.
    Single-swipe rows with no swipes[] array (newer compact ST, issue #6091) read as [mes], never failure.
    extra.display_text, when present, is what was SHOWN — prefer it, and SAY which text was used.
  ChatGPT: walk current_node -> root, reverse. Drop system/tool/hidden/non-text parts silently
    (internal nodes, never rendered). Single assistant by construction — no group rule needed.
  BOTH: empty texts dropped, system rows dropped, ts best-effort (None allowed downstream —
    build() already backfills +60s).

Stdlib only. No network. Nothing imported from anchor-public here — the files land beside
veil_transfer.py and reuse its gate()/draft()/build() through chat.json.
"""
import json

MIN_EXCHANGES = 10


def _when(v):
    """Best-effort timestamp -> epoch seconds, or None. Mirrors veil_transfer._when."""
    if isinstance(v, (int, float)):
        return int(v / 1000) if v > 1e11 else int(v)
    s = str(v or "").strip()
    if not s:
        return None
    if s.isdigit():
        return _when(int(s))
    import datetime
    for fmt in ("%B %d, %Y %I:%M%p", "%B %d, %Y %I:%M %p", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.datetime.strptime(s, fmt).timestamp())
        except ValueError:
            pass
    try:
        return int(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _refuse(why, names=()):
    err = ValueError("refused: " + why)
    err.names = list(names)
    raise err


def read_st_export(path, her=None):
    """SillyTavern .jsonl export (Manage chat files -> Export as .jsonl).
    Proof: docs/transference/PROOF_ST.md (ST release @ 06bde93).
    her=<name>: in a multi-voice chat, rows under that speaker name are hers; every
    other non-user speaker's rows are dropped AND NAMED in meta (never merged, never
    silently lost). Without her=, >1 non-user speaker is a refusal."""
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if not lines:
        _refuse("the file is empty.")
    rows = [json.loads(ln) for ln in lines if ln.startswith("{")]
    if not rows:
        _refuse("the file is empty.")
    first = rows[0]
    meta = first if isinstance(first, dict) and "mes" not in first else {}
    # ST writes user_name/character_name 'unused' in EVERY saved header
    # (script.js saveChat) — never take names from it. Names come from rows + card.
    if isinstance(meta, dict) and meta.get("user_name") == "unused":
        meta = {k: v for k, v in meta.items() if k not in ("user_name", "character_name")}
    msgs, speakers, swipe_notes, dropped = [], set(), [], {"narrator": 0, "display_text": 0}
    for i, row in enumerate(rows):
        if "mes" not in row:
            continue
        if row.get("is_system"):
            continue
        extra = row.get("extra") or {}
        if (extra.get("type") or "").lower() == "narrator":
            dropped["narrator"] += 1  # /sys narration: neither of them, never a speaker
            continue
        name = str(row.get("name") or "")
        who = "you" if row.get("is_user") else "her"
        if who == "her" and name:
            speakers.add(name)
        shown = extra.get("display_text")
        text = str(shown if shown else row.get("mes") or "").strip()
        used_display = bool(shown and str(shown).strip())
        if not row.get("is_user"):
            sw = row.get("swipes")
            sid = row.get("swipe_id", 0) if isinstance(row.get("swipe_id"), int) else 0
            expect = list(sw)[sid] if isinstance(sw, list) and 0 <= sid < len(sw) else None
            if expect is None:
                pass  # compact single-swipe row (ST #6091): mes stands alone, fine
            elif str(expect) != str(row.get("mes") or ""):
                swipe_notes.append(
                    "message %d ('%s…'): saved text and its swipe branch disagree — "
                    "kept the saved text, flagging, not choosing." % (i, name[:24]))
        if not text:
            continue
        if used_display:
            dropped["display_text"] += 1
        msgs.append({"who": who, "name": name, "text": text,
                     "ts": _when(row.get("send_date")), "ord": i,
                     "shown_as": "display_text" if used_display else "mes"})
    if her is not None:
        others = sorted(speakers - {her})
        if her not in speakers:
            _refuse("no voice named '%s' in here (found: %s)." % (her, ", ".join(sorted(speakers)) or "none"),
                    sorted(speakers))
        for m in msgs:
            if m["who"] == "her" and m["name"] != her:
                m["who"] = "other"
                m["other_name"] = m.pop("name")
        speakers = {her}
    if len(speakers) > 1:
        _refuse("more than one voice that isn't yours in here (%s) — re-run with her=<name> "
                "naming which one is her." % ", ".join(sorted(speakers)), sorted(speakers))
    user_names = {m["name"] for m in msgs if m["who"] == "you" and m["name"]}
    others = sorted({m.get("other_name", "") for m in msgs if m["who"] == "other"} - {""})
    meta_out = {"user_name": next(iter(sorted(user_names)), ""),
                "her_name": next(iter(sorted(speakers)), ""),
                "source": "sillytavern",
                "swipe_notes": swipe_notes,
                "dropped_narrator": dropped["narrator"],
                "display_text_rows": dropped["display_text"],
                "set_aside_speakers": others}
    return meta_out, msgs


def _chatgpt_walk(mapping, current):
    """current_node -> root via parents, reversed. Cycle-guarded (untrusted file).
    mapping keys are STRINGS in a real export (json object keys) — coerce both sides."""
    mapping = {str(k): v for k, v in (mapping or {}).items()}
    path, seen, nid = [], set(), str(current) if current is not None else ""
    while nid and nid not in seen and nid in mapping:
        seen.add(nid)
        node = mapping.get(nid) or {}
        path.append(nid)
        p = node.get("parent")
        nid = str(p) if p is not None else ""
    return path[::-1]


def read_chatgpt_conversation(path, index=0):
    """One conversation out of a ChatGPT conversations.json export.
    Proof: docs/transference/PROOF_CHATGPT.md. index selects which conversation;
    list_chatgpt_conversations() names them."""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    convos = data if isinstance(data, list) else [data]
    if not (0 <= index < len(convos)):
        _refuse("conversation %d not in this export (%d in it)." % (index, len(convos)))
    convo = convos[index]
    mapping = convo.get("mapping") or {}
    order = _chatgpt_walk(mapping, convo.get("current_node"))
    msgs, skipped = [], 0
    for ord_, nid in enumerate(order):
        m = (mapping.get(nid) or {}).get("message") or {}
        role = ((m.get("author") or {}).get("role")) or ""
        content = m.get("content") or {}
        if role not in ("user", "assistant"):
            skipped += 1
            continue  # system/tool: internal, never rendered
        if m.get("metadata", {}).get("is_visually_hidden_from_conversation"):
            skipped += 1
            continue
        ctype = content.get("content_type") or "text"
        if ctype == "multimodal_text":
            parts = [p.get("text", "") if isinstance(p, dict) else p
                     for p in (content.get("parts") or [])]
            parts = [p for p in parts if isinstance(p, str)]
        elif ctype != "text":
            skipped += 1
            continue  # code/tool/thought parts: activity, never shown
        else:
            parts = content.get("parts") or []
        text = "\n".join(str(p) for p in parts if isinstance(p, str)).strip()
        if not text:
            skipped += 1
            continue
        msgs.append({"who": "you" if role == "user" else "her",
                     "name": "", "text": text,
                     "ts": _when(m.get("create_time")), "ord": ord_})
    meta = {"user_name": "", "her_name": "", "source": "chatgpt",
            "title": str(convo.get("title") or ""), "skipped_internal": skipped}
    return meta, msgs


def list_chatgpt_conversations(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    convos = data if isinstance(data, list) else [data]
    out = []
    for i, c in enumerate(convos):
        mapping = c.get("mapping") or {}
        n = sum(1 for nd in mapping.values()
                if ((nd.get("message") or {}).get("author") or {}).get("role") in ("user", "assistant"))
        out.append({"index": i, "title": str(c.get("title") or ""),
                    "user_assistant_nodes": n})
    return out


def gate_intake(meta, msgs):
    """Shared intake gate -> (ok, problems, stats). Mirrors veil_transfer.gate's shape."""
    yours = sum(1 for m in msgs if m["who"] == "you")
    hers = sum(1 for m in msgs if m["who"] == "her")
    problems = []
    if not yours or not hers:
        problems.append("the chat needs both of you in it — one side is missing.")
    if min(yours, hers) < MIN_EXCHANGES:
        problems.append("too short to bring her home: %d exchanges, at least %d are needed."
                        % (min(yours, hers), MIN_EXCHANGES))
    notes = list(meta.get("swipe_notes") or [])
    if meta.get("dropped_narrator"):
        notes.append("%d narration line(s) set aside (stage directions, neither of you)."
                     % meta["dropped_narrator"])
    if meta.get("display_text_rows"):
        notes.append("%d line(s) taken from shown text, not the saved text (translation display)."
                     % meta["display_text_rows"])
    if meta.get("set_aside_speakers"):
        notes.append("other voice(s) set aside, not imported: %s."
                     % ", ".join(meta["set_aside_speakers"]))
    stats = {"your_lines": yours, "her_lines": hers, "source": meta.get("source", "")}
    if "other" in {m["who"] for m in msgs}:
        stats["other_lines"] = sum(1 for m in msgs if m["who"] == "other")
    return (not problems, problems + notes, stats)


def to_chat_json(meta, msgs):
    """chat.json shape that veil_transfer.build() already reads (messages: who/text/ts).
    ord rides along additively — build() ignores unknown keys, Phase E reads them.
    ONLY you/her are emitted. Rows marked who='other' (named speakers set aside via
    her=) stay named in meta.set_aside_speakers and NEVER reach the file — build()
    voices anything non-you as her, so emitting them would put their words in her mouth."""
    return {"her": meta.get("her_name", ""), "you": meta.get("user_name", ""),
            "messages": [{"who": m["who"], "text": m["text"], "ts": m["ts"], "ord": m["ord"]}
                         for m in msgs if m["who"] in ("you", "her")]}
