#!/usr/bin/env python3
"""Discord intake reader, round 2 (2026-10-17), reader 3 of 4.

One entry point -> one contract: list of {"who","name","text","ts","ord"} + meta dict.
  who:  "you" | "her" | "other"
  ord:  source message index in the exported messages array (file order)
  meta: {"user_name","her_name","source","title","author_map"} plus cleaning counts +
        set_aside_speakers + fallback counts

Source shape (Tyrrrz/DiscordChatExporter @276471f, VERIFIED BY HAND 2026-10-17 — docs/transference/PROOF_DISCORD.md):
  Top level: {guild:{id,name,iconUrl}, channel:{id,type,categoryId,category,name,topic},
              dateRange:{after,before}, exportedAt, messages:[...], messageCount}
  Per message: {id, type, timestamp (ISO-8601), timestampEdited, callEndedTimestamp,
                isPinned, content, author:{id (snowflake STRING), name (username),
                discriminator, nickname, color, isBot, roles, avatarUrl}, attachments,
                embeds, stickers, reactions, mentions, inlineEmojis, optional reference/
                forwardedMessage/interaction}.

Identity rules:
  - Author identity is keyed by author.id (string snowflake), NEVER by nickname alone.
  - her= / you= are normally the author.id string.
  - They ALSO accept "nickname:Name" or "name:username" for humans reading the file;
    nickname is matched first, then name. A warning about nickname instability is
    included in the refusal text when a name/nickname hint does not match.
  - her is NEVER inferred. A companion on Discord is usually a BOT account, so a bot can be her — when named.
    Unnamed: refused, with a hint (the bots listed; the one bot named when there is one bot and one human).
  - you = the one human left once her= is known (or you= when named); 2+ humans and no you= -> refused.
  - Every other author (a music bot, a friend) is who='other', set aside and named in meta (never her mouth).

Text rules:
  - content is primary.
  - Empty content falls back to attachments (fileName + url), embeds (description/url),
    or stickers (name), counted in meta by fallback type. Never import blind.
  - System notices (the exporter's own rule: kinds 1..18 or 46, Message.cs:43-46) carry a sentence the exporter MADE
    UP (GetFallbackContent) attributed to whoever triggered it: never anyone's words — set aside, counted.
    Every other kind is speech, including Reply (19) and a slash-command answer (20, written as the bare number).

Timestamp rules:
  - ISO-8601 via veil_intake._when (imported, not duplicated).

Export-format rules:
  - JSON only. .txt exports lose message ids and are refused with a clear note.
  - HTML adds nothing; still JSON only.

Order rules:
  - ord is the array position in the exported messages array. The exporter can write newest-first
    (ChannelExporter.cs:67, IsReverseMessageOrder), so the reader SORTS by timestamp, ord breaking ties.
    File order IS the order.

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


def _id_key(v):
    """Normalize an author id to a string."""
    if isinstance(v, bool):
        return ""
    return str(v or "").strip()


def _name_key(v):
    return str(v or "").strip()


def _load_json(path):
    """Load a Discord JSON export. Refuse .txt/.html early."""
    lower = path.lower()
    if lower.endswith(".txt"):
        _refuse("Discord .txt exports lose message ids and cannot identify speakers safely — "
                "re-export as JSON from DiscordChatExporter.")
    if lower.endswith(".html"):
        _refuse("HTML exports are not supported — re-export as JSON from DiscordChatExporter.")

    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)

    if isinstance(data, dict) and isinstance(data.get("messages"), list):
        return data
    if isinstance(data, list):
        return {"messages": data}
    _refuse("expected a Discord JSON export with a 'messages' array.")


def _author_label(author):
    """Return (id, nickname, name) for an author dict."""
    if not isinstance(author, dict):
        return "", "", ""
    return (
        _id_key(author.get("id")),
        _name_key(author.get("nickname")),
        _name_key(author.get("name")),
    )


def _resolve_her_you(author_map, her=None, you=None):
    """Resolve her=/you= hints to author ids.

    author_map: id -> {"nickname","name","isBot"}
    Accepts raw id strings or "nickname:Name"/"name:username" forms.
    Returns (her_id, you_id, resolution_notes).
    """
    notes = []

    def _resolve_one(hint, label):
        if hint is None:
            return None
        s = str(hint).strip()
        if not s:
            return None
        # Direct id match
        if s in author_map:
            return s
        # nickname:Name or name:username prefix forms
        prefix = None
        rest = s
        if s.lower().startswith("nickname:"):
            prefix = "nickname"
            rest = s[9:].strip()
        elif s.lower().startswith("name:"):
            prefix = "name"
            rest = s[5:].strip()
        if prefix:
            matches = [aid for aid, info in author_map.items()
                       if prefix == "nickname" and _name_key(info.get("nickname")) == rest]
            if len(matches) > 1:
                _refuse("hint '%s' matches %d authors by nickname — nicknames are not unique. "
                        "Pass the author.id string. Authors: %s" % (s, len(matches), "; ".join(
                            "%s (%s / %s)" % (aid, author_map[aid].get("nickname") or "no nick",
                                              author_map[aid].get("name") or "no name")
                            for aid in sorted(matches))), sorted(matches))
            if len(matches) == 1:
                return matches[0]
            if prefix == "nickname":
                notes.append(
                    "%s hint '%s' matched no nickname; nicknames are unstable and can change "
                    "per server — try the author id or name:username form." % (label, s))
            name_matches = [aid for aid, info in author_map.items()
                            if _name_key(info.get("name")) == rest]
            if len(name_matches) > 1:
                _refuse("hint '%s' matches %d authors by username — pass the author.id string. "
                        "Authors: %s" % (s, len(name_matches), "; ".join(sorted(name_matches))),
                        sorted(name_matches))
            if len(name_matches) == 1:
                return name_matches[0]
            return None
        # Bare name/nickname lookup: nickname first, then name
        nick_matches = [aid for aid, info in author_map.items()
                        if _name_key(info.get("nickname")) == s]
        if len(nick_matches) > 1:
            _refuse("hint '%s' matches %d authors by nickname — nicknames are not unique. "
                    "Pass the author.id string." % (s, len(nick_matches)), sorted(nick_matches))
        if len(nick_matches) == 1:
            return nick_matches[0]
        name_matches = [aid for aid, info in author_map.items()
                        if _name_key(info.get("name")) == s]
        if len(name_matches) > 1:
            _refuse("hint '%s' matches %d authors by username — pass the author.id string."
                    % (s, len(name_matches)), sorted(name_matches))
        if len(name_matches) == 1:
            return name_matches[0]
        return None

    her_id = _resolve_one(her, "her=")
    you_id = _resolve_one(you, "you=")
    return her_id, you_id, notes


def _extract_text(message):
    """Return (text, fallback_type) for a Discord message.

    content first; if empty, fall back to attachments/embeds/stickers.
    """
    text = str(message.get("content") or "").strip()
    if text:
        return text, None

    attachments = message.get("attachments") or []
    if isinstance(attachments, list) and attachments:
        parts = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            fn = _name_key(att.get("fileName"))
            url = _name_key(att.get("url"))
            if fn and url:
                parts.append("%s %s" % (fn, url))
            elif fn:
                parts.append(fn)
            elif url:
                parts.append(url)
        if parts:
            return "\n".join(parts), "attachment"

    embeds = message.get("embeds") or []
    if isinstance(embeds, list) and embeds:
        parts = []
        for emb in embeds:
            if not isinstance(emb, dict):
                continue
            desc = str(emb.get("description") or "").strip()
            url = _name_key(emb.get("url"))
            title = _name_key(emb.get("title"))
            bits = [b for b in (title, desc, url) if b]
            if bits:
                parts.append(" ".join(bits))
        if parts:
            return "\n".join(parts), "embed"

    stickers = message.get("stickers") or []
    if isinstance(stickers, list) and stickers:
        names = []
        for st in stickers:
            if isinstance(st, dict):
                n = _name_key(st.get("name"))
                if n:
                    names.append(n)
        if names:
            return "\n".join(names), "sticker"

    return "", None


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
        out.append(m)
    return out, total


def read_discord_export(path, her=None, you=None):
    """Read a Discord JSON export from DiscordChatExporter.

    her= and you= are author.id strings by default. They also accept:
      - "nickname:Name" (match server nickname first)
      - "name:username"  (match global username)
      - bare "Name"      (nickname first, then name; warned as unstable)
    Because nicknames are server-specific and unstable, prefer author.id.
    """
    data = _load_json(path)
    raw_messages = data.get("messages") or []
    if not raw_messages:
        _refuse("the export contains no messages.")

    # Build author map from all messages (bots tracked, then dropped).
    author_map = {}
    bot_ids = set()
    for m in raw_messages:
        if not isinstance(m, dict):
            continue
        author = m.get("author") or {}
        if not isinstance(author, dict):
            continue
        aid, nickname, name = _author_label(author)
        if not aid:
            continue
        is_bot = bool(author.get("isBot"))
        if aid not in author_map:
            author_map[aid] = {"nickname": nickname, "name": name, "isBot": is_bot}
        else:
            # Keep any non-empty name/nickname we see.
            if nickname and not author_map[aid]["nickname"]:
                author_map[aid]["nickname"] = nickname
            if name and not author_map[aid]["name"]:
                author_map[aid]["name"] = name
        if is_bot:
            bot_ids.add(aid)

    # ⭐ SPEAKERS (2026-10-17 review against DiscordChatExporter's own source @276471f). A Discord companion usually IS a
    # bot account (JsonMessageWriter writes author.isBot from user.IsBot). The first cut dropped every bot and, with one
    # human left, INFERRED THAT HUMAN AS HER — the person's own words imported as hers. Now her may be any author, bot or
    # human, and is NEVER inferred: she is named (--her), or the reader refuses and lists who is in the chat. Other bots
    # (music bots, moderation bots) are set aside and named. You = the one person left, or named with --you.
    her_id, you_id, resolution_notes = _resolve_her_you(author_map, her=her, you=you)

    def _roster():
        return "; ".join("%s (%s / %s%s)" % (aid, info.get("nickname") or "no nick", info.get("name") or "no name",
                                               ", bot" if info.get("isBot") else "")
                         for aid, info in sorted(author_map.items()))

    if her is not None and her_id is None:
        _refuse("her= hint '%s' did not match anyone in this export. Pass the author.id string (preferred), or "
                "nickname:Name / name:username. Authors: %s" % (her, _roster()))
    if you is not None and you_id is None:
        _refuse("you= hint '%s' did not match anyone in this export. Pass the author.id string (preferred), or "
                "nickname:Name / name:username. Authors: %s" % (you, _roster()))
    bots = sorted(a for a, i in author_map.items() if i.get("isBot"))
    humans = sorted(a for a, i in author_map.items() if not i.get("isBot"))
    if her_id is None:
        hint = ""
        if len(bots) == 1 and len(humans) == 1:
            hint = (" It looks like she is the bot %s (%s) — if so, re-run with --her %s."
                    % (bots[0], author_map[bots[0]].get("nickname") or author_map[bots[0]].get("name"), bots[0]))
        _refuse("I never guess which voice is hers — name her with --her <author.id>.%s Authors: %s"
                % (hint, _roster()), sorted(author_map))
    if you_id is None:
        people = [a for a in humans if a != her_id]
        if len(people) == 1:
            you_id = people[0]
        elif len(people) > 1:
            _refuse("more than one person in here besides her — name yourself with --you <author.id>. Authors: %s"
                    % _roster(), people)
        # no person besides her: left unset — gate_intake refuses 'one side is missing' in its own words
    if you_id == her_id:
        _refuse("her and you name the same author (%s)." % her_id)

    # Message kinds that are SPEECH (Discord/Data/MessageKind.cs). Everything else is a system notification whose
    # content the exporter fills with a made-up fallback sentence (JsonMessageWriter: GetFallbackContent()) — a join, a
    # pin, a call — attributed to whoever triggered it. Those are never anyone's words: set aside and counted.
    # SYSTEM = the exporter's own rule, nothing wider (Message.cs:43-46 IsSystemNotification: RecipientAdd..ThreadCreated
    # = kinds 1..18, or PollResult = 46). "type" is Kind.ToString() (JsonMessageWriter.cs:443), so a kind outside its enum
    # arrives as a bare number — a bot companion answering a slash command is "20". Every other kind is SPEECH.
    SYSTEM_KINDS = {"RecipientAdd", "RecipientRemove", "Call", "ChannelNameChange", "ChannelIconChange",
                    "ChannelPinnedMessage", "GuildMemberJoin", "ThreadCreated", "PollResult"}

    def _is_system(kind):
        return kind in SYSTEM_KINDS or (kind.isdigit() and (1 <= int(kind) <= 18 or int(kind) == 46))

    msgs = []
    fallback_counts = {}
    bot_dropped = 0
    system_count = 0
    for i, m in enumerate(raw_messages):
        if not isinstance(m, dict):
            continue
        author = m.get("author") or {}
        aid, nickname, name = _author_label(author)
        msg_type = str(m.get("type")) if m.get("type") is not None else ""
        if _is_system(msg_type):
            system_count += 1
            continue
        text, fallback = _extract_text(m)
        if fallback:
            fallback_counts[fallback] = fallback_counts.get(fallback, 0) + 1
        if not text:
            continue
        if aid == her_id:
            who = "her"
        elif aid == you_id:
            who = "you"
        else:
            who = "other"
            if author.get("isBot") or aid in bot_ids:
                bot_dropped += 1
        display_name = nickname if nickname else name
        entry = {"who": who, "name": display_name, "text": text, "ts": _when(m.get("timestamp")), "ord": i}
        if who == "other":
            entry["other_name"] = display_name
            entry["other_id"] = aid
        msgs.append(entry)

    # CHRONOLOGICAL, whatever the export's order: DiscordChatExporter can write newest-first
    # (ChannelExporter.cs: IsReverseMessageOrder -> GetMessagesInReverseAsync). ord stays the source index.
    msgs.sort(key=lambda e: (e["ts"] if e["ts"] is not None else float("inf"), e["ord"]))

    msgs, counts = _clean_messages(msgs)

    # Meta assembly.
    her_info = author_map.get(her_id) if her_id else None
    you_info = author_map.get(you_id) if you_id else None
    her_name = ""
    if her_info:
        her_name = her_info.get("nickname") or her_info.get("name") or ""
    user_name = ""
    if you_info:
        user_name = you_info.get("nickname") or you_info.get("name") or ""

    title = ""
    guild = data.get("guild") or {}
    channel = data.get("channel") or {}
    guild_name = _name_key(guild.get("name"))
    channel_name = _name_key(channel.get("name"))
    if guild_name and channel_name:
        title = "%s / #%s" % (guild_name, channel_name)
    elif channel_name:
        title = "#%s" % channel_name
    elif guild_name:
        title = guild_name

    others = sorted({m.get("other_name", "") for m in msgs if m["who"] == "other"} - {""})
    author_map_out = {
        aid: {"nickname": info.get("nickname", ""), "name": info.get("name", ""),
              "isBot": info.get("isBot", False)}
        for aid, info in sorted(author_map.items())
    }

    meta = {
        "user_name": user_name,
        "her_name": her_name,
        "source": "discord",
        "title": title,
        "author_map": author_map_out,
        "bot_dropped": bot_dropped,
        "system_messages": system_count,
        "set_aside_speakers": others,
    }
    for note in resolution_notes:
        meta.setdefault("resolution_notes", []).append(note)
    for k, v in fallback_counts.items():
        meta["fallback_%s" % k] = v
    for k, v in counts.items():
        meta["cleaning_%s" % k] = v

    return meta, msgs
