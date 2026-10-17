#!/usr/bin/env python3
"""Character.AI intake readers, round 2 (2026-10-17).

Three entry points -> one contract: list of {"who","name","text","ts","ord"} + meta dict.
  who:  "you" | "her" | "other"
  ord:  source index (line number in the JSONL, or array index in the JSON)
  meta: {"user_name","her_name","source","title"} plus cleaning counts + set_aside_speakers

Shapes supported:
  1. CAI Tools Tavern .jsonl (irsat000/CAI-Tools, CreateTavernChatBlob):
     header {user_name, character_name, create_date} then rows {name,is_user,is_name,send_date,mes}.
     Speaker rule: name == character_name -> her, otherwise you.

  2. CAI Tools canonical turns: JSON array of {name, message, isHuman}.
     isHuman=True -> you, else her.

  3. Neo-API turn objects (Lianne0106/cai-chat-exporter, cai_export.py):
     JSON array of {turn_key, create_time, author, candidates, primary_candidate_id}.
     Body = raw_content of the primary/final candidate; author.is_human -> you/her.

  4. Official Settings-export ZIP schema: UNPROVEN primary source. Best-effort multi-alias
     matching inside the first .json file found in the zip. Body aliases: raw_content, text,
     message. Speaker aliases: src__name, author.name, name. Human flag aliases:
     src__is_human, author.is_human, isHuman, is_user.

Stdlib only. Imports cleaning and intake_parsers helpers from the same directory when
importable; otherwise falls back to inline copies so the file can be executed standalone.
"""
import json
import os
import sys
import zipfile

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


def _clean_messages(msgs):
    total = None
    # start from a fresh counts dict if we can reach cleaning's helper
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
        out.append(m)
    return out, total


def _resolve_speakers(msgs, her=None, you=None, header_user=None, header_her=None, source=""):
    """Shared CAI speaker resolution: you/her/other, refusal, meta build.

    Input messages must already have who in {'you','her'} based on per-shape rules.
    """
    speakers = sorted({_name_key(m["name"]) for m in msgs if m["who"] == "her" and _name_key(m["name"])})

    if her is not None:
        her_key = _name_key(her)
        if her_key not in speakers:
            _refuse("no voice named '%s' in here (found: %s)." %
                    (her, ", ".join(speakers) or "none"), speakers)
        for m in msgs:
            if m["who"] == "her" and _name_key(m["name"]) != her_key:
                m["who"] = "other"
                m["other_name"] = m.pop("name", "")
        speakers = {her_key}

    if len(speakers) > 1:
        _refuse("more than one voice that isn't yours in here (%s) — re-run with her=<name> "
                "naming which one is her." % ", ".join(speakers), speakers)

    user_names = sorted({_name_key(m["name"]) for m in msgs if m["who"] == "you" and _name_key(m["name"])})
    others = sorted({_name_key(m.get("other_name", ""))
                     for m in msgs if m["who"] == "other" and _name_key(m.get("other_name", ""))})

    her_name = next(iter(sorted(speakers)), header_her or "")
    user_name = next(iter(user_names), header_user or you or "")

    meta = {
        "user_name": user_name,
        "her_name": her_name,
        "source": source,
        "title": "",
        "set_aside_speakers": others,
    }
    return meta, msgs


def _load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def read_cai_tavern(path, her=None, you=None):
    """CAI Tools Tavern .jsonl export (shape 1).

    Header row carries user_name/character_name/create_date; message rows carry
    {name, is_user, is_name, send_date, mes}. The character is the row whose name
    equals header.character_name; everything else is treated as the user.

    Placeholder header user_name 'You' (case-insensitive) is treated like 'unused'
    and becomes an empty meta user_name unless you= backfills it. Rows whose name is
    'You' and is_user=True are treated as the user with a blank name unless you=
    backfills. send_date is export time, not a real per-message timestamp, so every
    tavern message gets ts=None and meta carries no_real_dates.
    """
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if not lines:
        _refuse("the file is empty.")
    rows = [json.loads(ln) for ln in lines if ln.startswith("{")]
    if not rows:
        _refuse("the file is empty.")

    header = rows[0] if isinstance(rows[0], dict) and "mes" not in rows[0] else {}
    char_name = _name_key(header.get("character_name"))
    header_user = _name_key(header.get("user_name"))
    if header_user.lower() == "you":
        header_user = ""
    her_key = _name_key(her)
    you_key = _name_key(you)

    msgs = []
    for i, row in enumerate(rows):
        if "mes" not in row:
            continue
        name = _name_key(row.get("name"))
        is_user_flag = isinstance(row.get("is_user"), bool) and row["is_user"]
        if her_key and name == her_key:
            who = "her"
        elif char_name and name == char_name:
            who = "her"
        elif is_user_flag:
            who = "you"
        elif isinstance(row.get("is_user"), bool):
            who = "her"
        else:
            who = "you"
        # Blank the literal 'You' placeholder on user rows; backfill with you= if given.
        if who == "you" and name.lower() == "you":
            name = you_key
        text = str(row.get("mes") or "").strip()
        if not text:
            continue
        msgs.append({
            "who": who,
            "name": name,
            "text": text,
            "ts": None,
            "ord": i,
        })

    meta, msgs = _resolve_speakers(msgs, her=her, you=you,
                                   header_user=header_user if header_user != "unused" else "",
                                   header_her=char_name, source="cai_tavern")
    meta["title"] = str(header.get("create_date") or "")
    meta["no_real_dates"] = True
    meta["no_real_dates_text"] = "this export carries no real dates (export-time stamps only)"
    msgs, counts = _clean_messages(msgs)
    for k, v in counts.items():
        meta["cleaning_" + k] = v
    return meta, msgs


def _select_candidate(turn):
    """Pick the body candidate from a neo-API turn object."""
    candidates = turn.get("candidates") or []
    if not candidates:
        return ""
    primary_id = turn.get("primary_candidate_id")
    if primary_id is not None:
        for c in candidates:
            if isinstance(c, dict) and c.get("candidate_id") == primary_id:
                return str(c.get("raw_content") or "")
    for c in candidates:
        if isinstance(c, dict) and c.get("is_final"):
            return str(c.get("raw_content") or "")
    first = candidates[0]
    return str(first.get("raw_content") or "") if isinstance(first, dict) else ""


def _read_neo_turns(data):
    msgs = []
    for i, turn in enumerate(data):
        if not isinstance(turn, dict):
            continue
        author = turn.get("author") or {}
        if not isinstance(author, dict):
            author = {}
        name = _name_key(author.get("name"))
        is_human = author.get("is_human")
        who = "you" if is_human is True else "her"
        text = _select_candidate(turn).strip()
        if not text:
            continue
        msgs.append({
            "who": who,
            "name": name,
            "text": text,
            "ts": _when(turn.get("create_time")),
            "ord": i,
        })
    return msgs


def _read_canonical_turns(data):
    msgs = []
    for i, turn in enumerate(data):
        if not isinstance(turn, dict):
            continue
        name = _name_key(turn.get("name"))
        is_human = turn.get("isHuman")
        who = "you" if is_human is True else "her"
        text = str(turn.get("message") or "").strip()
        if not text:
            continue
        msgs.append({
            "who": who,
            "name": name,
            "text": text,
            "ts": None,
            "ord": i,
        })
    return msgs


def read_cai_turns(path, her=None, you=None):
    """CAI Tools canonical turns OR Neo-API turn objects (shapes 2 and 3).

    Accepts a bare JSON array OR a wrapper object {"chat_id", "exported_at",
    "message_count", "messages": [...]}. Neo-API turns are detected by keys
    turn_key/candidates; canonical turns are {name,message,isHuman}.

    Neo turns are returned in chronological order: sorted by create_time ascending
    when most/all rows carry create_time, otherwise reversed from file order (the
    API and exporter dump newest-first). ord is the chronological position.

    Canonical (non-neo) input carries an emotes_note because the companion .txt
    exporter strips *emotes* upstream with strip_markdown=True by default.
    """
    data = _load_json(path)
    is_wrapped = False
    if isinstance(data, dict):
        if isinstance(data.get("messages"), list):
            data = data["messages"]
            is_wrapped = True
        else:
            data = [data]
    if not isinstance(data, list):
        _refuse("expected a JSON array of turns.")
    if not data:
        _refuse("the file is empty.")

    is_neo = any(isinstance(t, dict) and ("turn_key" in t or "candidates" in t or "author" in t)
                 for t in data)
    msgs = _read_neo_turns(data) if is_neo else _read_canonical_turns(data)

    if is_neo:
        # The exporter dumps newest-first. Prefer create_time when available.
        have_ts = [m for m in msgs if m.get("ts") is not None]
        if len(have_ts) > len(msgs) / 2:
            msgs.sort(key=lambda m: (m.get("ts") is None, m.get("ts") or 0))
        else:
            msgs.reverse()
        for i, m in enumerate(msgs):
            m["ord"] = i

    source = "cai_turns"
    meta, msgs = _resolve_speakers(msgs, her=her, you=you, source=source)
    if not is_neo:
        meta["emotes_note"] = (
            "if this came from a .txt export, *emotes* were stripped upstream; "
            "prefer the JSON export"
        )
    msgs, counts = _clean_messages(msgs)
    for k, v in counts.items():
        meta["cleaning_" + k] = v
    return meta, msgs


def _read_official_turn(turn, user_hint=""):
    """Best-effort turn extraction for the unproven official ZIP schema."""
    if not isinstance(turn, dict):
        return None

    # Body aliases
    text = str(turn.get("raw_content") or turn.get("text") or turn.get("message") or "").strip()
    if not text:
        return None

    # Speaker name aliases: src__name, author.name, name
    author = turn.get("author") or {}
    if not isinstance(author, dict):
        author = {}
    name = _name_key(turn.get("src__name"))
    if not name:
        name = _name_key(author.get("name"))
    if not name:
        name = _name_key(turn.get("name"))

    # Human flag aliases: src__is_human, author.is_human, isHuman, is_user
    is_human = None
    if "src__is_human" in turn:
        is_human = bool(turn["src__is_human"])
    elif "is_human" in author:
        is_human = bool(author["is_human"])
    elif "isHuman" in turn:
        is_human = bool(turn["isHuman"])
    elif "is_user" in turn:
        is_human = bool(turn["is_user"])

    if is_human is None:
        # No human flag found: use the user/her name hints if available, else fall
        # back to "named -> her, unnamed -> you". Documented as best-effort.
        if user_hint and name == user_hint:
            is_human = True
        elif name:
            is_human = False
        else:
            is_human = True

    ts = _when(turn.get("create_time") or turn.get("send_date") or
               turn.get("timestamp") or turn.get("date"))
    return {"name": name, "text": text, "is_human": is_human, "ts": ts}


def read_cai_official(path, her=None, you=None):
    """Best-effort reader for an official Character.AI Settings-export ZIP.

    The exact inner schema is UNPROVEN (no primary source was available). This reader
    opens the zip, parses the first .json file it finds, and applies multi-alias
    matching. See PROOF_CAI.md for the honest provenance note.
    """
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as e:
        _refuse("not a valid zip file: %s" % e)

    with zf:            # closed on EVERY path, refusals too: an open zip is LOCKED on Windows (CI, 10-17)
        json_names = [n for n in zf.namelist() if n.lower().endswith(".json")]
        if not json_names:
            _refuse("no .json file found inside the zip.")

        data = None
        for name in json_names:
            try:
                with zf.open(name) as f:
                    data = json.loads(f.read().decode("utf-8-sig"))
                break
            except Exception:
                continue
    if data is None:
        _refuse("could not parse any .json file inside the zip.")

    if isinstance(data, dict):
        for key in ("turns", "messages", "chats", "history", "conversation"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        _refuse("expected a JSON list of turns inside the zip.")

    user_hint = _name_key(you)
    msgs = []
    for i, turn in enumerate(data):
        parsed = _read_official_turn(turn, user_hint=user_hint)
        if parsed is None:
            continue
        msgs.append({
            "who": "you" if parsed["is_human"] else "her",
            "name": parsed["name"],
            "text": parsed["text"],
            "ts": parsed["ts"],
            "ord": i,
        })

    meta, msgs = _resolve_speakers(msgs, her=her, you=you, source="cai_official")
    meta["official_schema_note"] = "UNPROVEN: multi-alias best-effort; no primary source verified."
    msgs, counts = _clean_messages(msgs)
    for k, v in counts.items():
        meta["cleaning_" + k] = v
    return meta, msgs
