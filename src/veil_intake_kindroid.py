#!/usr/bin/env python3
"""Kindroid intake reader, round 2 (2026-10-17).

One entry point -> one contract: list of {"who","name","text","ts","ord"} + meta dict.
  who:  "you" | "her" | "other"
  ord:  source message index (stable across re-parses)
  meta: {"user_name","her_name","source","title"} plus cleaning counts + set_aside_speakers

File format:
  - JSON array if the first non-whitespace char is '['.
  - JSONL otherwise (one JSON object per line).

Shape legs:
  1. API / third-party exporter shape: objects with display_name, id, sender,
     sender_type, timestamp, message, image_urls, image_description,
     video_description, internet_response, link_url, link_description.
     sender ai -> her, sender user -> you; display_name authoritative when present.

  2. Official in-app .jsonl account archive: best-effort duck-type. Speaker/text/time
     alias lists; refuse clearly when no keys match. The exact schema is UNPROVEN.

Stdlib only. Imports cleaning and intake_parsers helpers from the same directory when
importable; otherwise falls back to inline copies so the file can be executed standalone.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from veil_intake_clean import clean_text
    from veil_intake import _when, _refuse
except ImportError:
    import datetime
    import html
    import re

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

    def _refuse(why, names=()):
        err = ValueError("refused: " + why)
        err.names = list(names)
        raise err

    def clean_text(text):
        # inline copy of cleaning.py
        counts = {
            "ooc_lines": 0, "html_tags": 0, "html_entities": 0,
            "md_headers": 0, "md_images": 0, "md_links": 0,
            "md_comments": 0, "emptied": 0,
        }
        ooc = [
            re.compile(r'^\s*\(OOC:\s*.*\)\s*$', re.IGNORECASE),
            re.compile(r'^\s*\(\(.*\)\)\s*$'),
            re.compile(r'^\s*\[OOC\].*$', re.IGNORECASE),
            re.compile(r'^\s*OOC:\s*.*$', re.IGNORECASE),
        ]
        lines = text.splitlines()
        kept = []
        for line in lines:
            if any(pat.match(line) for pat in ooc):
                counts["ooc_lines"] += 1
            else:
                kept.append(line)
        cleaned = "\n".join(kept)
        cleaned, n = re.subn(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
        counts["md_comments"] += n
        cleaned, n = re.subn(r'!\[([^\]]+)\]\(([^)]+)\)', r'\1', cleaned)
        counts["md_images"] += n
        cleaned, n = re.subn(r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)', r'\1', cleaned)
        counts["md_links"] += n
        cleaned, n = re.subn(r'^#{1,6}\s+(.*?)(?:\s+#+\s*)?$', lambda m: m.group(1).rstrip(),
                             cleaned, flags=re.MULTILINE)
        counts["md_headers"] += n
        tags = re.findall(r'<[^>]+>', cleaned)
        counts["html_tags"] += len(tags)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        entities = re.findall(r'&(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);', cleaned)
        counts["html_entities"] += len(entities)
        cleaned = html.unescape(cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            counts["emptied"] += 1
        return cleaned, counts


def _name_key(name):
    return str(name or "").strip()


def _when_kindroid(v):
    """Kindroid timestamp: >1e10 = milliseconds else seconds."""
    if isinstance(v, (int, float)):
        return int(v / 1000) if v > 1e10 else int(v)
    s = str(v or "").strip()
    if not s:
        return None
    if s.isdigit():
        return _when_kindroid(int(s))
    return _when(v)


def _load_file(path):
    """Detect JSON array vs JSONL and return list of objects + format note."""
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    if not raw.strip():
        _refuse("the file is empty.")
    first = None
    for ch in raw:
        if not ch.isspace():
            first = ch
            break
    if first == '[':
        data = json.loads(raw)
        if not isinstance(data, list):
            _refuse("expected a JSON array.")
        return data, "json_array"
    # JSONL
    rows = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if not ln.startswith("{"):
            continue
        rows.append(json.loads(ln))
    if not rows:
        _refuse("the file is empty.")
    return rows, "jsonl"


def _extract_api_text(row):
    """Media/link fallback text for API shape; returns (text, fallback_key)."""
    text = str(row.get("message") or "").strip()
    if text:
        return text, None
    for key in ("image_description", "video_description", "link_description"):
        val = str(row.get(key) or "").strip()
        if val:
            return val, key
    return "", None


def _is_ai_sender(value):
    return str(value or "").lower() in {"ai", "model", "assistant", "character", "bot"}


def _is_user_sender(value):
    return str(value or "").lower() in {"user", "human"}


def _read_api_shape(rows, her=None, you=None):
    """Kindroid API exporter shape."""
    her_key = _name_key(her)
    you_key = _name_key(you)
    msgs = []
    fallback_counts = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        sender = row.get("sender") or row.get("sender_type") or ""
        if _is_ai_sender(sender):
            who = "her"
        elif _is_user_sender(sender):
            who = "you"
        else:
            continue  # unknown sender, skip
        name = _name_key(row.get("display_name"))
        if not name:
            name = her_key if who == "her" and her_key else (you_key if who == "you" and you_key else "")
        text, fallback = _extract_api_text(row)
        if fallback:
            fallback_counts[fallback] = fallback_counts.get(fallback, 0) + 1
        if not text:
            continue
        msgs.append({
            "who": who,
            "name": name,
            "text": text,
            "ts": _when_kindroid(row.get("timestamp")),
            "ord": i,
            "fallback": fallback,
        })
    return msgs, fallback_counts


# Ducktype alias lists
_SPEAKER_ALIASES = ["display_name", "sender_name", "author_name", "author", "name",
                    "speaker", "character_name", "user_name"]
_TEXT_ALIASES = ["message", "text", "content", "body", "raw_content"]
_TIME_ALIASES = ["timestamp", "created_at", "date", "send_date", "time", "updated_at"]
_ROLE_ALIASES = ["sender", "sender_type", "role", "type", "author"]


def _find_alias(row, aliases):
    for key in aliases:
        if key in row:
            return key, row[key]
    return None, None


def _ducktype_who(row, name, you=None):
    """Determine who from ducktype row. Role aliases beat speaker name hints."""
    for key in _ROLE_ALIASES:
        if key not in row:
            continue
        val = row[key]
        if isinstance(val, dict):
            # author: {name, is_human?}
            if "is_human" in val:
                return "you" if bool(val["is_human"]) else "her"
            if "isHuman" in val:
                return "you" if bool(val["isHuman"]) else "her"
            val = val.get("role") or val.get("sender") or val.get("type") or ""
        if _is_user_sender(val):
            return "you"
        if _is_ai_sender(val):
            return "her"
    # Boolean flags
    for key in ("is_user", "is_human", "isHuman", "from_human"):
        if key in row:
            return "you" if bool(row[key]) else "her"
    # Name hints
    if you is not None:
        if _name_key(name) == _name_key(you):
            return "you"
    # Default best-effort: named -> her, unnamed -> you (matches CAI official heuristic)
    return "her" if name else "you"


def _read_ducktype_shape(rows, you=None):
    """Best-effort official archive ducktype."""
    if not rows:
        return [], {}
    first = rows[0]
    if not isinstance(first, dict):
        _refuse("expected JSON objects, not %s." % type(first).__name__)

    def _has_any_alias(row, aliases):
        return any(key in row for key in aliases)

    # Require at least one text alias somewhere in the first row; speaker/role is
    # best-effort (a file with text but no role hint still parses, defaulting to her).
    if not _has_any_alias(first, _TEXT_ALIASES):
        _refuse("no recognized text key in this archive (looked for: %s)." % ", ".join(_TEXT_ALIASES))
    if not _has_any_alias(first, _SPEAKER_ALIASES) and not _has_any_alias(first, _ROLE_ALIASES):
        _refuse("no recognized speaker or role key in this archive (looked for speaker: %s; role: %s)."
                % (", ".join(_SPEAKER_ALIASES), ", ".join(_ROLE_ALIASES)))

    msgs = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        text_key, text_val = _find_alias(row, _TEXT_ALIASES)
        if text_key is None:
            continue
        text = str(text_val or "").strip()
        if not text:
            continue
        speaker_key, speaker_val = _find_alias(row, _SPEAKER_ALIASES)
        if speaker_key and isinstance(speaker_val, dict):
            name = _name_key(speaker_val.get("name") or speaker_val.get("display_name"))
        elif speaker_key:
            name = _name_key(speaker_val)
        else:
            name = ""
        time_key, time_val = _find_alias(row, _TIME_ALIASES)
        ts = _when_kindroid(time_val) if time_key else None
        who = _ducktype_who(row, name, you=you)
        msgs.append({
            "who": who,
            "name": name,
            "text": text,
            "ts": ts,
            "ord": i,
        })
    return msgs, {}


def _resolve_speakers(msgs, her=None, you=None, source="", fallback_counts=None, format_note=""):
    """Shared speaker resolution: you/her/other, refusal, meta build."""
    ai_rows = [m for m in msgs if m["who"] == "her"]
    her_names = sorted({_name_key(m["name"]) for m in ai_rows if _name_key(m["name"])})
    all_ai_unnamed = bool(ai_rows) and all(not _name_key(m["name"]) for m in ai_rows)
    if her is not None:
        her_key = _name_key(her)
        if her_key not in her_names:
            _refuse("no voice named '%s' in here (found: %s)." %
                    (her, ", ".join(her_names) or "none"), her_names)
        for m in msgs:
            if m["who"] == "her" and _name_key(m["name"]) != her_key:
                m["who"] = "other"
                m["other_name"] = m.pop("name", "")
        her_names = {her_key}

    if len(her_names) > 1:
        _refuse("more than one voice that isn't yours in here (%s) — re-run with her=<name> "
                "naming which one is her." % ", ".join(her_names), her_names)

    if you is not None:
        you_key = _name_key(you)
        for m in msgs:
            if m["who"] == "you" and _name_key(m["name"]) and _name_key(m["name"]) != you_key:
                m["who"] = "other"
                m["other_name"] = m.pop("name", "")

    user_names = sorted({_name_key(m["name"]) for m in msgs if m["who"] == "you" and _name_key(m["name"])})
    others = sorted({_name_key(m.get("other_name", ""))
                     for m in msgs if m["who"] == "other" and _name_key(m.get("other_name", ""))})

    her_name = next(iter(sorted(her_names)), "")
    user_name = next(iter(user_names), you or "")

    meta = {
        "user_name": user_name,
        "her_name": her_name,
        "source": source,
        "title": "",
        "set_aside_speakers": others,
    }
    if format_note:
        meta["format"] = format_note
    if source == "kindroid_api" and her is None and all_ai_unnamed:
        meta["single_or_group_unknown"] = "cannot tell AI speakers apart — confirm this was one companion"
    if fallback_counts:
        for k, v in fallback_counts.items():
            meta["media_fallback_" + k] = v
    return meta, msgs


def _clean_messages(msgs):
    total = None
    try:
        from veil_intake_clean import _initial_counts
        total = _initial_counts()
    except Exception:
        total = {"ooc_lines": 0, "html_tags": 0, "html_entities": 0,
                 "md_headers": 0, "md_images": 0, "md_links": 0,
                 "md_comments": 0, "emptied": 0}
    out = []
    for m in msgs:
        text, counts = clean_text(m["text"])
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
        if not text:
            continue
        m["text"] = text
        m.pop("fallback", None)
        out.append(m)
    return out, total


def _is_api_shape(rows):
    """Detect the documented API exporter shape by sender + message/media keys."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        has_sender = "sender" in row or "sender_type" in row
        has_text = ("message" in row or
                    "image_description" in row or
                    "video_description" in row or
                    "link_description" in row)
        if has_sender and has_text:
            return True
    return False


def read_kindroid_export(path, her=None, you=None):
    """Read a Kindroid export (JSON array or JSONL).

    her=<name> and you=<name> backfill missing display_names and select identity
    in group chats. Third speakers are marked who='other' and named in meta.
    """
    rows, fmt = _load_file(path)
    if not rows:
        _refuse("the file is empty.")
    if _is_api_shape(rows):
        msgs, fallback_counts = _read_api_shape(rows, her=her, you=you)
        source = "kindroid_api"
        schema_note = ""
    else:
        msgs, fallback_counts = _read_ducktype_shape(rows, you=you)
        source = "kindroid_official"
        schema_note = "UNPROVEN: multi-alias best-effort; no primary source verified."
    if not msgs:
        _refuse("parsed 0 messages from %d rows (source guess: %s) — the shape router "
                "may have misread this file; check it is a Kindroid export, not another "
                "platform's archive." % (len(rows), source))

    # K1: chronological sort. API-leg is paginated by start_after_timestamp and the
    # resulting file order is not guaranteed to be chronological, so sort by parsed ts.
    # Ducktype keeps file order unless every row carries a recognizable time key.
    unsorted_note = False
    if source == "kindroid_api":
        msgs = sorted(msgs, key=lambda m: (m.get("ts") if m.get("ts") is not None else float("inf"), m.get("ord", 0)))
    else:
        if all(m.get("ts") is not None for m in msgs):
            msgs = sorted(msgs, key=lambda m: (m.get("ts"), m.get("ord", 0)))
        else:
            unsorted_note = True
    for new_ord, m in enumerate(msgs):
        m["ord"] = new_ord

    meta, msgs = _resolve_speakers(msgs, her=her, you=you, source=source,
                                   fallback_counts=fallback_counts, format_note=fmt)
    if unsorted_note:
        meta["unsorted_no_timestamps"] = True
    if schema_note:
        meta["official_schema_note"] = schema_note
    msgs, counts = _clean_messages(msgs)
    for k, v in counts.items():
        meta["cleaning_" + k] = v
    return meta, msgs
