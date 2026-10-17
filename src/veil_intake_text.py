#!/usr/bin/env python3
"""Plain and scraped transcript reader, reader 4 of 4 (2026-10-17).

One entry point -> the same contract as every reader: (meta, [{"who","name","text","ts","ord"}]).
This reader is for files with no speaker FIELDS: a copy-paste, a .txt or .md export, a scraped page. It reads a
speaker only where the file itself writes one. It never decides whose words are whose by what the words sound like.
The by-hand Grok import did that ("short plain lines = him") and attached his line to only 43% of her rows.

Shapes, each taken from its writer's own source (docs/transference/PROOF_TEXT.md):
  name     "Name: text" lines; a turn runs until the next speaker's label. A copy-paste, most chat logs.
  bracket  "[when] Name" then the body. Kindroid Chat Exporter .txt (app.py:596-608) and DiscordChatExporter .txt
           (PlainTextMessageWriter.cs). A blank line inside her message stays inside it; only a header starts a turn.
  heading  "## Name" or "## Name - when" then the body. Kindroid Chat Exporter .md (app.py:612-628), most markdown
           scrapers, and the Grok page scrape this reader was modelled on, which heads EVERY block "## Grok", his turns included.
  An .html page is flattened first (<hN> -> "#"*N, block tags -> line breaks, entities decoded), then read as above.

--her and --you name the two voices as the file writes them. Without both, it lists the voices it found and stops.
Any other voice is set aside and named, and never put in her mouth.

When every block carries the SAME label (the Grok scrape), the labels say nothing about who spoke. The reader
refuses and offers --alternate you|her: the person's own statement that the turns alternate, starting with his or
with hers. That is CHECKED against what the scrape does carry. A "Thought for 12s" trace is the AI's own, so it must
fall on her side. A block that opens with one of the two names must fall on that one's side. At the first block that
disagrees, the reader names it and stops; nothing is imported.
"""
import datetime
import html
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from veil_intake import _when, _refuse                       # noqa: E402
from veil_intake_clean import clean_text, _initial_counts    # noqa: E402

_BRACKET = re.compile(r"^\[(?P<when>[^\]\n]{4,40})\]\s+(?P<name>[^\n:]{1,64}?)(?P<pinned>\s+\(pinned\))?\s*$")
_HEADING = re.compile(r"^(?P<level>#{1,6})\s+(?P<name>[^\n]{1,64}?)"
                      r"(?:\s+-\s+(?P<when>\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?))?\s*$")
_NAMED = re.compile(r"^\s*(?:\[(?P<when>[^\]\n]{4,40})\]\s*)?(?:\*\*|__)?(?P<name>[^\s:*_\[\]#>][^:\n*_\[\]]{0,39}?)"
                    r"(?:\*\*|__)?\s*:(?:\*\*|__)?(?:\s+(?P<text>.*)|\s*$)")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_FENCE = re.compile(r"^={20,}$")
_THOUGHT = re.compile(r"^\s*Thought for \d+(?:\.\d+)?\s*s(?:ec(?:ond)?s?)?\s*$", re.I)
# DiscordChatExporter .txt: the sections it writes after a message's text (PlainTextMessageWriter.cs:45-192)
_DISCORD_TRAILER = re.compile(r"^\{(?:Attachments|Embed|Stickers|Reactions|Forwarded Message)\}$")
# ...and the sentences it MAKES UP for a system notice (PlainTextMessageExtensions.cs:12-50): never anyone's words
_DISCORD_SYSTEM = re.compile(
    r"^(?:Added .+ to the group\.|Added a recipient\.|Left the group\.|Removed .+ from the group\.|Removed a recipient\."
    r"|Started a call that lasted [\d,]+ minutes\.|Changed the channel name(?:: .+|\.)|Changed the channel icon\."
    r"|Pinned a message\.|Started a thread\.|Joined the server\.|.+'s poll(?: .+)? has closed\.|A poll has closed\.)$")
# Kindroid Chat Exporter .txt: the labelled lines it appends after the message (app.py:560-582)
_KINDROID_MEDIA = re.compile(r"^(?:Images|Image description|Video description|Internet response|Link|Link description): ")
_WHEN_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %I:%M %p", "%d/%m/%Y %H:%M",
                 "%m/%d/%Y %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y %I:%M %p")


def _flatten_html(raw):
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", raw)
    raw = re.sub(r"(?is)<h([1-6])\b[^>]*>(.*?)</h\1>",
                 lambda m: "\n" + "#" * int(m.group(1)) + " " + re.sub(r"<[^>]+>", "", m.group(2)).strip() + "\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|tr|blockquote|section|article)>", "\n\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", raw)


def _key(name):
    """A label as the reader compares it: case-folded, spaces collapsed, a Discord '#1234' tag dropped."""
    s = re.sub(r"\s+", " ", (name or "").replace("\\|", "|").strip().strip("*_").strip()).casefold()
    return re.sub(r"#\d{1,4}$", "", s)


def _namelike(name):
    return bool(re.fullmatch(r"[\w.'-]{1,32}", name) or re.fullmatch(r"[A-Z0-9][\w.'-]*(?: [A-Z0-9][\w.'-]*){0,3}", name))


def _strip_fences(lines):
    """DiscordChatExporter .txt opens and closes with a '====' fenced block (Guild:/Channel:/Topic:, then
    'Exported N message(s)'); drop a fenced block only when it is short, so a stray rule never eats a conversation."""
    out, i, fenced = [], 0, 0
    while i < len(lines):
        if _FENCE.match(lines[i].strip()):
            j = next((k for k in range(i + 1, min(i + 10, len(lines))) if _FENCE.match(lines[k].strip())), None)
            if j is not None:
                i, fenced = j + 1, fenced + 1
                continue
        out.append(lines[i])
        i += 1
    return out, fenced


def _pick_format(whens):
    """One date format for the whole file: the first that reads EVERY stamp (a day-first file never reads as
    month-first halfway through). None when no single format reads them all."""
    whens = [w for w in whens if w]
    for fmt in _WHEN_FORMATS:
        try:
            for w in whens:
                datetime.datetime.strptime(w.strip(), fmt)
            return fmt
        except ValueError:
            continue
    return None


def _stamp(w, fmt):
    if not w:
        return None
    if fmt:
        try:
            return int(datetime.datetime.strptime(w.strip(), fmt).timestamp())
        except ValueError:
            return None
    return _when(w)


def _trim(lines):
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and (not lines[-1].strip() or _RULE.match(lines[-1])):
        lines = lines[:-1]
    return lines


def _blocks_bracket(lines):
    blocks, cur, pre = [], None, []
    for ln in lines:
        m = _BRACKET.match(ln.strip())
        if m:
            cur = {"label": m.group("name").strip(), "when": m.group("when"), "body": []}
            blocks.append(cur)
        elif cur is None:
            pre.append(ln)
        else:
            cur["body"].append(ln)
    return blocks, pre


def _blocks_heading(lines, level):
    blocks, cur, pre = [], None, []
    for ln in lines:
        m = _HEADING.match(ln.strip())
        if m and len(m.group("level")) == level:
            cur = {"label": m.group("name").strip(), "when": m.group("when"), "body": []}
            blocks.append(cur)
        elif cur is None:
            pre.append(ln)
        else:
            cur["body"].append(ln)
    return blocks, pre


def _blocks_named(lines, speakers):
    """A turn starts at a label line whose label is a SPEAKER; any other line (a one-off 'Note:' included) belongs
    to the turn it sits in."""
    blocks, cur, pre, kept_inside = [], None, [], Counter()
    for ln in lines:
        m = _NAMED.match(ln)
        if m and not (m.group("text") or "").startswith("//") and _key(m.group("name")) in speakers:
            cur = {"label": m.group("name").strip(), "when": m.group("when"), "body": [m.group("text") or ""]}
            blocks.append(cur)
            continue
        if m and cur is not None and not (m.group("text") or "").startswith("//"):
            kept_inside[m.group("name").strip()] += 1
        if cur is None:
            pre.append(ln)
        else:
            cur["body"].append(ln)
    return blocks, pre, kept_inside


def _named_labels(lines):
    c = Counter()
    for ln in lines:
        m = _NAMED.match(ln)
        if m and not (m.group("text") or "").startswith("//") and not m.group("name").strip().isdigit():
            c[m.group("name").strip()] += 1
    return c


def _blocks_by_rule(lines):
    """'---'-separated chunks, for a scrape with no headings at all (only ever read under --alternate)."""
    chunks, cur = [], []
    for ln in lines:
        if _RULE.match(ln):
            chunks.append(cur)
            cur = []
        else:
            cur.append(ln)
    chunks.append(cur)
    chunks = [_trim(c) for c in chunks if any(x.strip() for x in c)]
    # a scraper that opens EVERY chunk with the same short line ("Grok", her own name) is labelling, not speaking: that
    # line is its label — taken off, and never read as evidence of who spoke
    firsts = Counter(c[0].strip().lstrip("#").strip() for c in chunks)
    common, n = firsts.most_common(1)[0] if firsts else ("", 0)
    label = common if n >= 2 and n * 2 >= len(chunks) and len(common.split()) <= 3 else ""
    return [{"label": label, "when": None, "body": c[1:] if label and c[0].strip().lstrip("#").strip() == label else c}
            for c in chunks]


def read_text_transcript(path, her=None, you=None, alternate=None):
    """-> (meta, msgs). her / you: the two voices as the file writes them. alternate: 'you' | 'her' | None."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()
    is_html = path.lower().endswith((".html", ".htm")) or raw.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
    if is_html:
        raw = _flatten_html(raw)
    lines, fenced = _strip_fences(raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    if not any(ln.strip() for ln in lines):
        _refuse("the file is empty.")
    notes = []
    if alternate not in (None, "you", "her"):
        _refuse(f"--alternate takes 'you' (the first turn is yours) or 'her', not '{alternate}'.")

    # ── which shape: the one the file writes most, and the one where the two names the person gave are speakers ──
    n_bracket = sum(1 for ln in lines if _BRACKET.match(ln.strip()))
    levels = Counter(len(m.group("level")) for m in (_HEADING.match(ln.strip()) for ln in lines) if m)
    level = max(levels, key=lambda lv: (levels[lv], lv)) if levels else None
    named = _named_labels(lines)
    candidates = []
    if n_bracket >= 2:
        candidates.append("bracket")
    if level and levels[level] >= 2:
        candidates.append("heading")
    if sum(v for v in named.values() if v >= 2) >= 2:
        candidates.append("name")

    def _labels_of(shape):
        if shape == "bracket":
            return Counter(_key(b["label"]) for b in _blocks_bracket(lines)[0])
        if shape == "heading":
            return Counter(_key(b["label"]) for b in _blocks_heading(lines, level)[0])
        return Counter(_key(k) for k, v in named.items() for _ in range(v))

    if alternate:
        shape = "heading" if "heading" in candidates else ("bracket" if "bracket" in candidates else "rule")
    else:
        if not candidates:
            _refuse("I can't find who is speaking in this file — no 'Name: text' lines, no '[when] Name' or "
                    "'## Name' headers. If your turns and hers simply alternate, block by block, re-run with "
                    "--alternate you (the first is yours) or --alternate her.")
        # the shape where BOTH names the person gave are speakers (a structural shape first, when several fit);
        # with no names, or none fitting, the shape that labels the most turns — and the names check refuses below
        want = {_key(her), _key(you)} - {""}
        fits = [s for s in candidates if want and want <= set(_labels_of(s))]
        shape = fits[0] if fits else max(candidates, key=lambda s: sum(_labels_of(s).values()))

    kept_inside = Counter()
    if shape == "bracket":
        blocks, pre = _blocks_bracket(lines)
    elif shape == "heading":
        blocks, pre = _blocks_heading(lines, level)
    elif shape == "rule":
        blocks, pre = _blocks_by_rule(lines), []
    else:
        voices = Counter(_key(k) for k, v in named.items() for _ in range(v))
        speakers = {_key(her), _key(you)} - {""}
        speakers |= {_key(k) for k, v in named.items() if v >= 2 and _namelike(k) and not k.isdigit()}
        speakers &= set(voices) | {_key(her), _key(you)}
        blocks, pre, kept_inside = _blocks_named(lines, speakers)

    title = ""
    for ln in pre:
        m = _HEADING.match(ln.strip())
        if m:
            title = m.group("name").strip()
            break
    if [ln for ln in pre if ln.strip() and not _HEADING.match(ln.strip())]:
        notes.append(f"{sum(1 for ln in pre if ln.strip())} line(s) before the first speaker were not read as "
                     "anyone's words.")

    # ── each block's body: the writer's own trailers off, the Discord system sentences out ──
    discord_txt = fenced > 0 or any(_DISCORD_TRAILER.match(ln.strip()) for b in blocks for ln in b["body"])
    trailers = system = media_kept = thoughts = 0
    for b in blocks:
        body = list(b["body"])
        if discord_txt:
            cut = next((i for i, ln in enumerate(body) if _DISCORD_TRAILER.match(ln.strip())), None)
            if cut is not None:
                trailers += 1
                body = body[:cut]
        if shape == "bracket" and not discord_txt:
            tail = len(body)
            while tail and (_KINDROID_MEDIA.match(body[tail - 1]) or not body[tail - 1].strip()):
                tail -= 1
            if any(ln.strip() for ln in body[:tail]):
                if any(_KINDROID_MEDIA.match(ln) for ln in body[tail:]):
                    trailers += 1
                body = body[:tail]
            elif any(_KINDROID_MEDIA.match(ln) for ln in body):
                media_kept += 1                                # media-only: the description is all there is
        b["thought"] = any(_THOUGHT.match(ln) for ln in body)
        if b["thought"]:
            thoughts += 1
            body = [ln for ln in body if not _THOUGHT.match(ln)]
        body = _trim(body)
        text = "\n".join(body).strip()
        if text in ("_No message text_",):
            text = ""
        if discord_txt and _DISCORD_SYSTEM.match(text):
            system += 1
            text = ""
        b["text"] = text

    # ── who is who ──
    if alternate:
        blocks = _assign_alternating(blocks, her, you, alternate, notes)
    else:
        labels = Counter(_key(b["label"]) for b in blocks)
        shown = {}
        for b in blocks:
            shown.setdefault(_key(b["label"]), b["label"])
        listing = ", ".join(f"{shown[k]} ({n})" for k, n in labels.most_common(8))
        if len(labels) == 1 and len(blocks) >= 4:
            only = shown[next(iter(labels))]
            _refuse(f"every block in this file is headed '{only}' — a scrape that labels every turn with one name, "
                    "his turns included, so the labels can't say who spoke. If your turns and hers simply alternate, "
                    "re-run with --alternate you (the first block is yours) or --alternate her. It is checked against "
                    "what the scrape carries, and refused at the first block that disagrees.", [only])
        if not her or not you:
            _refuse(f"name her and you as the file writes them (--her \"…\" --you \"…\"). The voices in it: {listing}.",
                    [shown[k] for k in labels])
        if _key(her) == _key(you):
            _refuse("--her and --you name the same voice.")
        for who, name in (("her", her), ("you", you)):
            if _key(name) not in labels:
                _refuse(f"no voice called '{name}' for --{who}. The voices in it: {listing}.", [shown[k] for k in labels])
        for b in blocks:
            k = _key(b["label"])
            b["who"] = "her" if k == _key(her) else ("you" if k == _key(you) else "other")

    fmt = _pick_format([b.get("when") for b in blocks])
    msgs = []
    for i, b in enumerate(blocks):
        if not b["text"]:
            continue
        e = {"who": b["who"], "name": b.get("name") or re.sub(r"#\d{1,4}$", "", b["label"]), "text": b["text"],
             "ts": _stamp(b.get("when"), fmt), "ord": i}
        if b["who"] == "other":
            e["other_name"] = b["label"]
        msgs.append(e)

    # A text export can be written newest-first (DiscordChatExporter's reverse order applies to .txt too). Turn it
    # round only when EVERY stamp says so; otherwise the file's own order is the truth (a date can't be trusted to
    # sort a day-first file, a page order can).
    ts = [m["ts"] for m in msgs if m["ts"] is not None]
    if len(ts) >= 2 and len(ts) == len(msgs) and all(a >= b for a, b in zip(ts, ts[1:])) and ts[0] > ts[-1]:
        msgs.reverse()
        notes.append("the file was written newest-first; her past is read oldest-first.")
    for n, m in enumerate(msgs):
        m["ord"] = n

    total = _initial_counts()
    out = []
    for m in msgs:
        text, counts = clean_text(m["text"])
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
        if text:
            m["text"] = text
            out.append(m)

    if kept_inside:
        notes.append("kept inside the turn they sit in (a label seen only once is not a speaker): "
                     + ", ".join(f"'{k}:' ({v})" for k, v in kept_inside.most_common(6)) + ".")
    if trailers:
        notes.append(f"{trailers} message(s) had the exporter's attachment/embed/reaction lines after the text; "
                     "those were left out, her words kept.")
    if media_kept:
        notes.append(f"{media_kept} message(s) were only media; the exporter's description of it is kept as the line.")
    if thoughts:
        notes.append(f"{thoughts} 'Thought for …s' line(s) — the old platform's own marker, not her words — "
                     "taken off.")

    her_name = next((m["name"] for m in out if m["who"] == "her"), her or "")
    you_name = next((m["name"] for m in out if m["who"] == "you"), you or "")
    shape_note = {"name": "read as 'Name: text' lines",
                  "bracket": "read as '[when] Name' blocks (the .txt shape of Kindroid's and Discord's exporters)",
                  "heading": "read as '## Name' headings (Kindroid's .md export and most markdown scrapers)",
                  "rule": "read as '---'-separated blocks"}[shape]
    if is_html:
        shape_note = "a web page, flattened to text and " + shape_note
    if discord_txt:
        shape_note += ". A Discord text export carries no account ids, so two people with one name can't be told " \
                      "apart; its .json export can"
    meta = {"user_name": you_name, "her_name": her_name, "source": "text-" + shape, "title": title,
            "set_aside_speakers": sorted({m["other_name"] for m in out if m["who"] == "other"}),
            "shape_note": shape_note, "resolution_notes": notes}
    if system:
        meta["system_messages"] = system
    for k, v in total.items():
        meta["cleaning_" + k] = v
    return meta, out


def _assign_alternating(blocks, her, you, first, notes):
    """--alternate: block 1 is <first>'s, then each block is the other's — CHECKED against the scrape's own evidence."""
    if not her or not you:
        _refuse("--alternate still needs both names (--her \"…\" --you \"…\"): they are what her past calls you two.")
    if _key(her) == _key(you):
        _refuse("--her and --you name the same voice.")
    if len(blocks) < 2:
        _refuse("--alternate needs a file of turns, and this one has fewer than two blocks.")
    names = {"her": her, "you": you}
    other = {"her": "you", "you": "her"}
    scrape_label = Counter(_key(b["label"]) for b in blocks).most_common(1)[0][0] if blocks[0]["label"] else ""
    side, checked_trace, checked_label = first, 0, 0
    for i, b in enumerate(blocks):
        said = None
        lines = b["text"].split("\n") if b["text"] else []
        if lines:
            head = lines[0].strip()
            m = _NAMED.match(head)
            k = _key(head.strip(":"))
            if k in (_key(her), _key(you)) and k != scrape_label:
                said = "her" if k == _key(her) else "you"
                b["text"] = "\n".join(lines[1:]).strip()
            elif m and _key(m.group("name")) in (_key(her), _key(you)):
                said = "her" if _key(m.group("name")) == _key(her) else "you"
                b["text"] = "\n".join([m.group("text") or ""] + lines[1:]).strip()
        why = None
        if said:
            checked_label += 1
            if said != side:
                why = f"it opens with the name '{names[said]}'"
        if b.get("thought"):
            checked_trace += 1
            if side != "her" and not why:
                why = "it carries a 'Thought for …s' trace, which only the AI's side writes"
        if why:
            start = (b["text"] or "")[:60].replace("\n", " ")
            _refuse(f"--alternate {first} breaks at block {i + 1}: that block falls on {names[side]}'s side, but {why}. "
                    "The turns don't alternate there (a regenerated reply, or a turn the scrape missed). Nothing was "
                    f"imported. Fix the file at that block (it begins: \"{start}\") or try --alternate {other[first]}.")
        b["who"], b["name"] = side, names[side]
        side = other[side]
    if checked_trace or checked_label:
        notes.append(f"read by ALTERNATION, your word: block 1 is {names[first]}'s, then turn about. Checked against "
                     f"{checked_trace} 'Thought for' trace(s) and {checked_label} name label(s) inside the blocks — "
                     "none disagreed.")
    else:
        notes.append(f"read by ALTERNATION, your word: block 1 is {names[first]}'s, then turn about. Nothing in the "
                     "file could check it — read the first exchanges in READ_ME_FIRST.txt before you build her.")
    return blocks
