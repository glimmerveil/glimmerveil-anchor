#!/usr/bin/env python3
"""Transference intake — Claude (claude.ai "Export data"), 2026-11-07.

Claude had been missed: until 2.0.2 a Claude export was misread as a Character.AI ZIP (every .zip went there) and
its conversations.json was refused outright.

THE SHAPE (no official schema is published; read from independent parsers, see PROOF_CLAUDE.md):
  claude.ai -> Settings -> Privacy -> Export data -> a ZIP holding conversations.json (+ users.json, projects.json).
  conversations.json = ARRAY of conversations; each =
      {uuid, name, created_at, updated_at, chat_messages: [...], ...}
  a message = {uuid, sender: "human" | "assistant", text, content: [blocks], created_at, attachments, files, ...}
      content blocks: {"type": "text", "text": ...} and others (thinking, tool_use, tool_result, …).

THE CONTRACT (the same as every reader in this house): (meta, msgs), msgs = [{who, name, text, ts, ord}].
  who:  human -> "you", assistant -> "her". Anything else is set aside and counted.
  text: the TEXT blocks of content, in order; when a message has no content list (or no text blocks in it), its
        top-level "text". Thinking and tool blocks are activity, never shown as her words: dropped and counted, as
        the ChatGPT reader drops its code/tool/thought parts. Attachments and files are never anyone's words.
  ord:  the message's position in the conversation as shown, so the Phase E hold-out survives a re-parse.
  Branches (an edited or retried message): only where one message has two replies (parent_message_uuid). Then the
        shown branch is walked from current_leaf_message_uuid (or the last message with an id) back to the root, as
        ChatGPT's current_node is; the other branch's messages are left out AND counted, never silently. A chat that
        was never edited keeps the file's order whole.
  Cleaning: the house's shared clean_text (OOC asides, HTML, markdown STRUCTURE); her *emotes* are never touched.

A Claude conversation is one person and one assistant by construction: no group rule is needed (as ChatGPT).
Stdlib only. No network. Every ZIP is closed on every path (an open zip is LOCKED on Windows: CI, 10-17).
"""
import json
import math
import os
import zipfile
import zlib

try:
    from veil_intake_clean import clean_text
except ImportError:                                   # (a reader must still load where the shared module is absent)
    def clean_text(text):
        return text, {}

# A conversations.json is read whole (as ChatGPT's is), and parsing holds ~4-6x its size in memory (measured by
# Haiku 11-07: 19 MB -> 117 MB, 44 MB -> 164 MB). This bounds what one export may unpack to, so a zip bomb or a broken
# header cannot run the machine out of memory: at the cap the parse peaks near 1-1.5 GB. A real export of years of
# chats is tens of MB.
MAX_JSON_BYTES = 256 << 20          # 256 MiB uncompressed
# What a damaged, encrypted or exotic ZIP member raises while it is read (Haiku 11-07): each becomes a plain refusal.
_ZIP_READ_ERRORS = (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, OSError, EOFError, KeyError,
                    ValueError)
# A file nested deep enough overflows the JSON parser's stack (Haiku 11-07: "[" * 200000): a refusal, never a crash.
_JSON_ERRORS = (UnicodeDecodeError, ValueError, RecursionError)


def _refuse(why):
    raise ValueError("refused: " + why)


def _when(v):
    """The house's _when, guarded: a non-finite or absurd time is no time (Haiku 11-07: 1e400 raised OverflowError)."""
    import veil_intake
    if isinstance(v, bool) or (isinstance(v, float) and not math.isfinite(v)):
        return None
    try:
        return veil_intake._when(v)
    except (OverflowError, OSError, ValueError):
        return None


def _member(zf):
    """The conversations.json a Claude export ZIP holds: the top-most one. ONE choice, shared by the reader and the
    sniffer (Haiku 11-07: they picked different members and disagreed)."""
    hits = [i for i in zf.infolist()
            if not i.is_dir() and os.path.basename(i.filename).lower() == "conversations.json"]
    return min(hits, key=lambda i: (i.filename.count("/"), i.filename)) if hits else None


def _read_zip(path):
    """-> parsed conversations.json from a Claude export ZIP. Refuses when there is none."""
    try:
        zf = zipfile.ZipFile(path, "r")
    except (zipfile.BadZipFile, OSError) as e:
        _refuse("not a zip file I can open: %s" % e)
    with zf:
        info = _member(zf)
        if info is None:
            _refuse("this zip holds no conversations.json, so it is not a Claude export.")
        if info.file_size > MAX_JSON_BYTES:
            _refuse("its conversations.json would unpack to %d MB, more than I will read (%d MB)."
                    % (info.file_size >> 20, MAX_JSON_BYTES >> 20))
        try:
            with zf.open(info) as f:
                raw = f.read(MAX_JSON_BYTES + 1)
        except _ZIP_READ_ERRORS as e:
            _refuse("its conversations.json could not be unpacked (damaged, encrypted or an unusual kind of zip). If "
                    "this is a Claude export, download it again from claude.ai. (%s)" % str(e)[:100])
    if len(raw) > MAX_JSON_BYTES:
        _refuse("its conversations.json is larger than it says it is; not read.")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except _JSON_ERRORS as e:
        _refuse("its conversations.json is not readable JSON: %s" % str(e)[:120])


def load_export(path):
    """-> the list of conversations in a Claude export (.zip or conversations.json)."""
    if str(path).lower().endswith(".zip"):
        data = _read_zip(path)
    else:
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError,) + _JSON_ERRORS as e:
            _refuse("not a JSON file I can read: %s" % str(e)[:120])
    if isinstance(data, dict):                         # one conversation saved alone, or a wrapper around the list
        data = data.get("conversations") if isinstance(data.get("conversations"), list) else [data]
    if not is_claude_data(data):
        _refuse("this is not a Claude export (no conversation in it carries chat_messages).")
    return data


def is_claude_data(data):
    """True when parsed JSON looks like Claude's conversations.json: conversations carrying chat_messages lists."""
    if not isinstance(data, list) or not data:
        return False
    convos = [c for c in data if isinstance(c, dict)]
    return bool(convos) and all(isinstance(c.get("chat_messages"), list) for c in convos)


def zip_is_claude(path):
    """Peek, never raise: does this ZIP hold a Claude conversations.json? (So a Claude export is never handed to the
    Character.AI reader, which used to take every .zip.)"""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            hit = _member(zf)
            if hit is None:
                return False
            with zf.open(hit) as f:                    # the head only: the key is in the first conversation
                head = f.read(8 << 20).decode("utf-8-sig", errors="ignore")
    except _ZIP_READ_ERRORS:
        # A ZIP whose TOP-LEVEL conversations.json (where claude.ai puts it) cannot be unpacked is still Claude's to
        # refuse, plainly — never handed to the Character.AI reader to misread (Haiku 11-07: a bad CRC was routed
        # there). A deeper one is not claimed (Haiku 11-07 r2): only the name and the place say Claude, not the bytes.
        try:
            with zipfile.ZipFile(path, "r") as zf:
                hit = _member(zf)
                return hit is not None and "/" not in hit.filename.strip("/")
        except _ZIP_READ_ERRORS:
            return False
    return '"chat_messages"' in head


def _role(m):
    r = str(m.get("sender") or m.get("role") or "").strip().lower()
    return "you" if r in ("human", "user") else "her" if r == "assistant" else None


def _text_of(m, counts):
    """The words a message SHOWED: its text blocks in order. Its top-level text only when it has no blocks to say
    otherwise: a turn whose blocks are ALL activity (a tool call, thinking) shows no words of hers, so its top-level
    text is never taken for them (Haiku 11-07). A content that is plain text is read as text (one parser's spelling)."""
    blocks = m.get("content")
    parts, activity = [], 0
    if isinstance(blocks, dict):                        # one block, not in a list (Haiku 11-07 r2: a lone tool block
        blocks = [blocks]                               # let the top-level text through as her words)
    if isinstance(blocks, str):
        parts.append(blocks)
    elif blocks is not None and not isinstance(blocks, list):
        activity += 1                                   # a number, a bool: nothing that shows words — and no fallback
    elif isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, str):
                parts.append(b)
                continue
            if not isinstance(b, dict):
                activity += 1                           # null, a number: not words (Haiku 11-07 r3)
                continue
            kind = str(b.get("type") or "")
            if kind in ("text", "") and isinstance(b.get("text"), str):
                parts.append(b["text"])                 # (a block with no type but a text is text: r3 note 9)
            else:
                activity += 1
    if activity:
        counts["internal_blocks"] = counts.get("internal_blocks", 0) + activity
    text = "\n\n".join(p for p in parts if p.strip())
    # The top-level text only when the message carried NO content at all (missing, or an empty list): once there are
    # blocks, they are what the chat showed, even when they show nothing (Haiku 11-07 r3: an empty text block let the
    # top-level text in).
    if not text.strip() and (blocks is None or blocks == []) and isinstance(m.get("text"), str):
        text = m["text"]
    return text.strip()


def _parent(m):
    return str(m.get("parent_message_uuid") or "")


_UNKNOWN = ("this chat was edited, but the file does not say clearly which branch was shown ({why}): every message "
            "was kept in file order, both branches included. Read chat.json and take out what was not said before you "
            "build her")


def _shown_branch(convo, msgs):
    """-> (the messages on the shown branch, in order, as (position, message)), how many were left out, and a note
    when the branch could not be told (or "").

    A branch exists only where a turn was EDITED or retried: one message with two replies, or two first messages that
    each have replies. Without that, the file's own order is the chat and nothing is left out, whatever links are or
    are not there (Haiku 11-07 r2). With it, the shown branch is walked back from its last message — and whenever the
    file is ambiguous about that walk (a repeated id, a loop, two unlabelled last replies), NOTHING is guessed: every
    message is kept in file order and the review says so, in the person's hands (Haiku 11-07 r3)."""
    indexed = [(i, m) for i, m in enumerate(msgs) if isinstance(m, dict)]
    ids = [str(m.get("uuid")) for _, m in indexed if m.get("uuid") not in (None, "")]
    by_id = {str(m.get("uuid")): (i, m) for i, m in indexed if m.get("uuid") not in (None, "")}
    unlinked = lambda m: not _parent(m) or _parent(m) not in by_id     # no parent, or one not in the file (a root)
    replies = {}
    for _, m in indexed:
        if _parent(m):
            replies[_parent(m)] = replies.get(_parent(m), 0) + 1
    rooted = sum(1 for _, m in indexed if unlinked(m) and str(m.get("uuid") or "") in replies)
    if not any(n > 1 for n in replies.values()) and rooted <= 1:
        return indexed, 0, ""
    if len(ids) != len(set(ids)):
        return indexed, 0, _UNKNOWN.format(why="two messages share one id")
    leaf = str(convo.get("current_leaf_message_uuid") or "")
    if leaf not in by_id:                               # no usable leaf: the LAST message that can be walked from
        leaf = next((str(m.get("uuid")) for _, m in reversed(indexed) if str(m.get("uuid") or "") in by_id), "")
    path, seen, nid = [], set(), leaf
    while nid and nid in by_id:
        if nid in seen:                                 # a loop in the links: the walk cannot be trusted
            return indexed, 0, _UNKNOWN.format(why="its links run in a loop")
        seen.add(nid)
        path.append(by_id[nid])
        nid = _parent(by_id[nid][1])
    path.reverse()
    if not path:
        return indexed, 0, _UNKNOWN.format(why="no message to walk back from")
    on = {i for i, _ in path}
    if unlinked(path[0][1]):
        # The walk reached the chat's start (no parent, or a parent not in the file): unlinked messages BEFORE it that
        # nothing replies to are the chat's opening, kept in front. One that something replies to is the root of
        # another branch (an abandoned first message), never pulled in (Haiku 11-07 r3).
        head = [(i, m) for i, m in indexed if i < path[0][0] and i not in on and unlinked(m)
                and str(m.get("uuid") or "") not in replies]
        path = head + path
        on |= {i for i, _ in head}
    last = str(path[-1][1].get("uuid") or "")
    tail = [(i, m) for i, m in indexed if i > path[-1][0] and i not in on and not m.get("uuid") and _parent(m) == last]
    if len(tail) > 1:                                   # two unlabelled replies to the shown end: which one? unknown
        return indexed, 0, _UNKNOWN.format(why="two replies to its last message carry no id")
    path += tail
    return path, len(indexed) - len(path), ""


def _conversations_summary(convos):
    out = []
    for i, c in enumerate(convos):
        if not isinstance(c, dict):
            continue
        shown, _, _ = _shown_branch(c, c.get("chat_messages") or [])
        n = sum(1 for _, m in shown if _role(m) and _text_of(m, {}))
        out.append({"index": i, "title": str(c.get("name") or ""), "lines": n,
                    "created": str(c.get("created_at") or "")[:10]})
    return out


def list_claude_conversations(path):
    """-> [{index, title, lines, created}] for every conversation in the export."""
    return _conversations_summary(load_export(path))


def _read_one(convo):
    msgs_raw = convo.get("chat_messages") or []
    shown, off_branch, branch_note = _shown_branch(convo, msgs_raw)
    not_messages = sum(1 for m in msgs_raw if not isinstance(m, dict))
    msgs, counts, cleaning, skipped_roles, attached, wordless = [], {}, {}, 0, 0, 0
    for ord_, (_pos, m) in enumerate(shown):
        who = _role(m)
        if who is None:
            skipped_roles += 1
            continue
        if m.get("attachments") or m.get("files") or m.get("files_v2"):
            attached += 1
        text = _text_of(m, counts)
        if not text:
            wordless += 1
            continue
        cleaned, c = clean_text(text)
        for k, v in (c or {}).items():
            cleaning[k] = cleaning.get(k, 0) + v
        if not cleaned.strip():
            continue
        msgs.append({"who": who, "name": "", "text": cleaned.strip(), "ts": _when(m.get("created_at")), "ord": ord_})
    notes = []
    if off_branch:
        notes.append(f"{off_branch} message(s) not on the branch the chat showed last (an edited or retried turn, or "
                     "a broken link in the file) left out")
    if branch_note:
        notes.append(branch_note)
    if not_messages:
        notes.append(f"{not_messages} entry(ies) in the chat that were not messages set aside")
    if wordless:
        notes.append(f"{wordless} message(s) carried no words (only activity, files, or nothing readable) and were "
                     "left out")
    if counts.get("internal_blocks"):
        notes.append(f"{counts['internal_blocks']} piece(s) of the model's own activity (thinking, tools, pictures) "
                     "set aside, never imported as her words")
    if attached:
        notes.append(f"{attached} message(s) carried attachments or files; the files were not imported, only the words")
    if skipped_roles:
        notes.append(f"{skipped_roles} message(s) from neither of you set aside")
    meta = {"user_name": "", "her_name": "", "source": "claude", "title": str(convo.get("name") or ""),
            "resolution_notes": notes}
    meta.update({"cleaning_" + k: v for k, v in cleaning.items()})
    return meta, msgs


def read_claude_conversation(path, index=0):
    """One conversation out of a Claude export, by its number in claude-list."""
    try:
        n = int(str(index).strip())
    except ValueError:
        _refuse("the conversation number must be a number from claude-list, not '%s'." % index)
    convos = load_export(path)
    if not (0 <= n < len(convos)) or not isinstance(convos[n], dict):
        _refuse("conversation %s is not in this export (%d in it: see claude-list)." % (index, len(convos)))
    return _read_one(convos[n])


def read_claude_export(path, her=None, you=None):
    """check-file / draft-file's door: an export holding ONE conversation reads straight through; more than one is
    refused with the way to pick (claude-list, then draft-claude), never a guess at which one is her."""
    convos = [c for c in load_export(path) if isinstance(c, dict)]
    if len(convos) != 1:
        _refuse("this Claude export holds %d conversations. List them with: claude-list %s  — then bring the one "
                "that is her home with: draft-claude %s <number> \"<her name>\" <review-folder>"
                % (len(convos), os.path.basename(path), os.path.basename(path)))
    meta, msgs = _read_one(convos[0])
    if her:
        meta["her_name"] = str(her).strip()
    if you:
        meta["user_name"] = str(you).strip()
    return meta, msgs
