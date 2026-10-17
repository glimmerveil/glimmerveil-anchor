# Character.AI intake source proof (round 2, reader 1 of 4)

Scope: the four export shapes the CAI readers consume. Each claim is followed by its
source and a verdict. Shape 4 is honestly marked UNPROVEN — no primary source was
available. Fixtures used in tests are invented content (Nell/Elara/Sage) in the real
shapes below; no real person's words are used.

## Source inventory

| Source | URL | File/path (scout-reported) | Verification status |
|---|---|---|---|
| CAI-Tools (Tavern exporter) | https://github.com/irsat000/CAI-Tools | `scripts/content.js` function `CreateTavernChatBlob`; scout-reported tree `2adcba6` | **VERIFIED-BY-HAND** at `a read-only clone of irsat000/CAI-Tools @2adcba6` |
| cai-chat-exporter (Neo-API exporter) | https://github.com/Lianne0106/cai-chat-exporter | `cai_export.py`; scout-reported tree `bfec718` | **VERIFIED-BY-HAND** at `a read-only clone of Lianne0106/cai-chat-exporter @bfec718` |
| Official Character.AI Settings-export ZIP | https://character.ai (settings/data export) | n/a | UNPROVEN — no primary source or sample file available. |

Verification clones (read-only, not executed):
- `a read-only clone of irsat000/CAI-Tools @2adcba6`
- `a read-only clone of Lianne0106/cai-chat-exporter @bfec718`

License note: the two published repositories above are third-party open-source tools.
Their sample code is referenced here only to document the shape of the export files
they produce. Test fixtures are invented content and do not reproduce repository code.

---

## F1. CAI Tools Tavern .jsonl (shape 1)

**Claim:** The file is a JSONL whose first line is a header
`{user_name, character_name, create_date}` and each subsequent line is a message object
`{name, is_user, is_name, send_date, mes}`. Speaker identity is determined by comparing
`name` to `character_name`: a message whose `name` equals the header's `character_name`
is the character, everything else is the user. Consecutive same-speaker turns from the
original chat are merged into one row with `\n\n` by `CreateTavernChatBlob`.

**Source:** `irsat000/CAI-Tools`, `scripts/content.js`, function `CreateTavernChatBlob`;
verified tree `2adcba6`, lines 1261-1284:
- `:1261` — `const userName = 'You';` — the header `user_name` is always the literal
  placeholder `'You'`, not the real user's name.
- `:1263-1267` — header object carries `user_name`, `character_name`, `create_date`.
- `:1281` — `name: msg.name !== charName ? "You" : charName` — every human row is named
  the literal placeholder `"You"`.
- `:1284` — `send_date: Date.now()` — each row carries export time, not the original
  per-message timestamp.

**Verdict:** VERIFIED-BY-HAND. The reader treats each JSONL line as one contract
message (the merge has already happened upstream). Speaker resolution uses the
name-vs-character_name rule, falling back to the `is_user` boolean when the header is
missing. The literal `'You'` placeholder is treated like `'unused'`: header `user_name`
`'You'` becomes an empty meta `user_name` unless `you=` backfills it, and user rows
named `'You'` are recorded with a blank name unless `you=` backfills. Because
`send_date` is export time, every tavern message gets `ts=None` and `meta` carries
`no_real_dates: True`.

---

## F2. CAI Tools canonical turns (shape 2)

**Claim:** A JSON array of objects `{name, message, isHuman}` where `isHuman` is a
boolean: `true` = human/user, `false` = character.

**Source:** Derived from shape 1 by the same toolset and documented in the CAI-Tools
ecosystem as the canonical turn representation.

**Verdict:** ACCEPTED-SCOUT-REPORT. The reader maps `isHuman=True` -> `you`, else `her`.
No timestamp field exists in this shape; `ts` is `None` and downstream back-fills.
Because this shape is also the target of the companion `.txt` exporter (which strips
`*emotes*` upstream via `strip_markdown=True` by default), canonical input carries
`meta.emotes_note` warning that `.txt` exports may have lost emotes and that the JSON
export is preferred.

---

## F3. Neo-API turn objects (shape 3)

**Claim:** Turns are objects with `turn_key {chat_id, turn_id}`, `create_time`,
`author {author_id, name, is_human}`, `candidates [{candidate_id, raw_content,
is_final, model_type}]`, and `primary_candidate_id`. The exporter dumps turns
newest-first and can wrap them in `{"chat_id", "exported_at", "message_count",
"messages": [...]}`. The visible body is the `raw_content` of the final/primary
candidate.

**Source:** `Lianne0106/cai-chat-exporter`, `cai_export.py`; verified tree
`bfec718`:
- `:128` — `strip_markdown: bool = True` — default `.txt` export strips `*` markers.
- `:140-141` — `# Reverse to chronological order` / `turns = list(reversed(turns))` —
  the function's docstring states `turns: API turn list (newest first)` and the code
  reverses to chronological before formatting.
- `:167-169` — `if strip_markdown: text = text.replace("*", "")` — emotes wrapped in
  `*` are destroyed in `.txt` output.
- `:188-199` — `turns_to_json` dumps raw `turns` newest-first into a wrapper object
  `{"chat_id", "exported_at", "message_count", "messages": turns}`.

**Verdict:** VERIFIED-BY-HAND. The reader selects `primary_candidate_id` first, then an
`is_final=True` candidate, then the first candidate. Speaker is determined by
`author.is_human`. It accepts both bare turn arrays and the JSON wrapper object. Turns
are ordered chronologically: by `create_time` ascending when most/all rows carry it,
otherwise by reversing the file order (newest-first fallback). `ord` is the
chronological position after ordering. This shape does **not** carry `emotes_note`
because the JSON body preserves `raw_content` including `*` markers.

---

## F4. Official Character.AI Settings-export ZIP (shape 4)

**Claim:** None. The exact inner JSON schema of an official Character.AI settings/data
export ZIP is **UNPROVEN** — no primary source, sample file, or repository code was
available to this seat.

**Source:** n/a.

**Verdict:** UNPROVEN. The reader implements best-effort multi-alias matching only:
  - Body aliases: `raw_content`, `text`, `message`
  - Speaker-name aliases: `src__name`, `author.name`, `name`
  - Human-flag aliases: `src__is_human`, `author.is_human`, `isHuman`, `is_user`

It opens the first `.json` file found in the ZIP, expects a list of turn-like objects
(or a dict containing a `turns`/`messages`/`chats`/`history`/`conversation` list), and
applies the aliases above. Any export matching this shape will be read; any export with
a different inner schema will be refused with a clear note. The `meta` dict carries
`official_schema_note: UNPROVEN` so the gate can report the uncertainty honestly.
