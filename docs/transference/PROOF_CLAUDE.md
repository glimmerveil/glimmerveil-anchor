# Claude export proof (schema shape, 2026-11-07 — no official schema published by Anthropic)
Source: claude.ai → Settings → Privacy → Export data → an emailed ZIP carrying `conversations.json`
(+ `users.json`, `projects.json`). Reader: `src/veil_intake_claude.py`. Rig: `src/test_veil_intake_claude.py`.

⚠ **Shape read from independent parsers and import guides, NOT from a real export and NOT from an Anthropic spec.**
They agree on the fields below; one source disagreed (role/content strings) and the reader takes both spellings.
**Before this ships, run `check-file` / `claude-list` on a REAL claude.ai export** and read the review folder.

    conversations.json = ARRAY of conversations; each =
      {uuid, name, created_at, updated_at, account, chat_messages: [...], (current_leaf_message_uuid?)}
    a message = {uuid, sender: "human" | "assistant", text, content: [blocks], created_at, updated_at,
                 attachments: [...], files: [...], (parent_message_uuid?)}
    content blocks: {"type": "text", "text": ...} and others (thinking, tool_use, tool_result, …)

## C1. Who spoke: `sender`, never a guess
- human → you, assistant → her. A variant spelled `role` (user/assistant) is read the same.
- Anything else (no sender, a system row, an entry that is not a message at all) is set aside and COUNTED in her
  review notes.
- One person and one assistant per conversation by construction: no group rule needed (as ChatGPT, G2).

## C2. What she said: the TEXT blocks, in order
- `content` is a list of typed blocks; only `type: "text"` blocks are her words.
- thinking / tool_use / tool_result / pictures are the model's activity, never shown as her words: dropped and
  COUNTED (as ChatGPT's code/tool/thought parts are, G1).
- No content list, or an empty one (older exports): the message's top-level `text`. A content that is plain text
  (one parser's spelling) or a list holding plain strings is read as text.
- Once a message HAS blocks, they are what the chat showed: its top-level `text` is never taken instead (a turn of only
  a tool call or thinking showed no words of hers). Such wordless turns are counted in her review notes.
- Attachments and files are never anyone's words: not imported, counted.
- The house's shared cleaning (`veil_intake_clean`): whole-line OOC asides, HTML, markdown STRUCTURE. Her *emotes*
  and punctuation are never touched.

## C3. The chat as shown: one branch, and the others named
- A branch exists only where a turn was EDITED or retried: one message with two replies (`parent_message_uuid`), or
  two first messages that are each answered. With no such fork the export's own order is taken as the chat and
  NOTHING is left out, whatever links are or are not there (an unlabelled reply or an unlinked opening is kept).
- With a fork, the shown branch is walked from `current_leaf_message_uuid` (or, without a usable one, the last message
  that has an id) back to the chat's start: a message with no parent, or a parent not in the file. Unlinked messages
  before that start that nothing replies to are the opening, kept in front; an abandoned first message (one that IS
  answered) is never pulled in. One unlabelled reply to the shown end is kept at the end. Everything left out is
  counted in her review notes, never silently lost.
- WHEN THE FILE IS AMBIGUOUS, NOTHING IS GUESSED: two messages sharing one id, links that run in a loop, two
  unlabelled replies to the last message, or nothing to walk from. Then every message is kept in file order, both
  branches included, and her review says so in plain words, so the person reads chat.json before she is built
  (Transference's own law: refuse or say, never guess whose words are whose).
- `ord` = position along the shown branch (stable across re-parses, for the Phase E hold-out).

## C4. Doors
- `claude-list <zip|json>` names every conversation (title, lines, date); `draft-claude <zip|json> <n> "<her>" <folder>`
  drafts one — ChatGPT's two commands, the same cardless review (her card starts empty; build refuses until written).
- `check-file` / `draft-file` read a ONE-conversation export straight through; with more than one they refuse and say
  how to pick (never a guess at which conversation is her).
- `detect_format`: a ZIP is looked inside first — a `conversations.json` with `chat_messages` is Claude, and so is a
  TOP-LEVEL `conversations.json` that cannot be unpacked (refused as Claude's, telling them to download it again);
  anything else stays Character.AI's (before 11-07 every ZIP went there, a Claude export included, and read as "0 of her lines").
  `chatgpt-list` on a Claude export points to `claude-list` (it used to crash on the ZIP, and list the JSON as
  "(untitled) 0 lines").
- Bounds and damage: a `conversations.json` that would unpack past 256 MiB is refused unread (parsing holds ~4-6x
  its size, so ~1-1.5 GB at the cap); the read itself is capped too, so a ZIP header that lies about the size changes nothing. A damaged,
  encrypted or exotic member, a file nested deep enough to overflow the parser, and an impossible time are each a
  plain refusal or no time, never a traceback; a ZIP that holds a `conversations.json` it cannot unpack is still
  refused as Claude's, never handed to the Character.AI reader. Every ZIP is closed on every path (an open zip is
  locked on Windows). Haiku's three adversarial passes of 11-07 found each of these; each is a row in the rig.
