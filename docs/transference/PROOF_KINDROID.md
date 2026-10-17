# Kindroid intake source proof (round 2, reader 2 of 4)

Scope: the two export shapes the Kindroid reader consumes. Each claim is followed by
its source and a verdict. Fixtures used in tests are invented content (Nell/Elara/Sage)
in the real shapes below; no real person's words are used.

## Source inventory

| Source | URL | File/path (scout-reported) | Verification status |
|---|---|---|---|
| Kindroid Chat Exporter (third-party tool) | https://github.com/tomsegura2/Kindroid-Chat-Exporter | `app.py`; local clone `a read-only clone of tomsegura2/Kindroid-Chat-Exporter` @ `bae1478` | VERIFIED-BY-HAND — paging :406-479, group helper :160-190, txt blocks :596-608. |
| Official Kindroid in-app .jsonl account archive | Kindroid help FAQ (JS-gated page) | n/a | UNPROVEN — only ".jsonl, account-wide" is reported; the exact schema was not verified. |

License note: the third-party repository above is referenced only to document the shape
of the export files it produces. Test fixtures are invented content and do not reproduce
repository code.

---

## F1. Kindroid Chat Exporter API shape

**Claim:** The exporter returns a list of message objects with keys `display_name`, `id`,
`sender`, `sender_type`, `timestamp`, `message`, `image_urls`, `image_description`,
`video_description`, `internet_response`, `link_url`, `link_description`. `sender` is
`"ai"` or `"user"` (ambiguous in group chats with multiple characters). `display_name`
is authoritative when present but is often omitted. Numeric `timestamp`: values greater
than `1e10` are milliseconds, otherwise seconds. Messages are ordered ascending by
timestamp. Media/link-only messages may have an empty `message`; in that case the visible
text falls back to `image_description`, `video_description`, or `link_description`.

**Source:** `tomsegura2/Kindroid-Chat-Exporter`, `app.py`; verified by hand at local clone
`a read-only clone of tomsegura2/Kindroid-Chat-Exporter` @ `bae1478`.

**Verdict:** VERIFIED-BY-HAND. The reader maps `sender="ai"` -> `her` and `sender="user"`
-> `you`. `display_name` is used when present; `her=` / `you=` backfill missing display
names. Multiple distinct AI `display_name`s without `her=` are refused with the names found;
if some AI rows lack `display_name` while the named AI rows already span 2+ distinct names,
import is also refused because the unnamed rows could be any of them. If every AI row lacks
`display_name` and `her=` is not supplied, import proceeds but `meta.single_or_group_unknown`
warns: *"cannot tell AI speakers apart — confirm this was one companion"*. With `her=`,
non-matching AI voices become `who="other"` and are named in `meta.set_aside_speakers`
(never her mouth). Media description fallback text is marked in `meta.media_fallback_*`.
Every message is passed through `clean_text()` and empty-after-clean messages are dropped
and counted.

Because the exporter paginates via `start_after_timestamp` (`app.py:406-479`) and appends
pages to the output file, JSON-array/JSONL file order is not chronological by construction.
The reader therefore sorts API-leg messages by parsed `timestamp` ascending, stable on
file order for equal or missing timestamps, and assigns `ord` as chronological position.
`ord` remains stable across re-parses of the same file.

---

## F2. Official in-app .jsonl account archive

**Claim:** None about the inner schema. The only proven fact is that the official archive
is described as ".jsonl, account-wide" on a Kindroid help FAQ page (JS-gated).

**Source:** Kindroid help FAQ; exact URL/schema not retrieved.

**Verdict:** UNPROVEN. The reader implements best-effort multi-alias matching:
  - Text aliases: `message`, `text`, `content`, `body`, `raw_content`
  - Speaker-name aliases: `display_name`, `sender_name`, `author_name`, `name`, `speaker`,
    `character_name`, `user_name`
  - Time aliases: `timestamp`, `created_at`, `date`, `send_date`, `time`, `updated_at`
  - Role / human-flag aliases: `sender`, `sender_type`, `role`, `type`, `author`,
    `is_user`, `is_human`, `isHuman`, `from_human`

The file may be a JSON array or JSONL (one object per line). If no recognized text key or
speaker/role key is found, the reader refuses with a clear note. Multi-voice refusal and
`her=` selection mirror the API leg. The `meta` dict carries
`official_schema_note: UNPROVEN` so the gate can report the uncertainty honestly.

## F3. API-first routing hazard (judge-found, 2026-10-17)

**Claim:** A file carrying `sender` + `message`-family keys but name-valued senders
(e.g. an official archive that happens to use those key names) routes to the API leg,
parses zero messages, and previously returned empty success with `source="kindroid_api"`
and no UNPROVEN note.

**Verdict:** FIXED. `read_kindroid_export` refuses on zero parsed messages with the
source guess named, so the misroute is loud, never silent. Test `misroute` pins it.

## F4. Plain-text / markdown exporter shape (reader 4 scope)

**Claim:** The same exporter also writes `.txt` and `.md` files. The `.txt` format is a
sequence of blank-line-separated blocks. Each block is one of:
- `[{timestamp}] {author}\n{body}` when `timestamp` is present and non-empty
- `{author}\n{body}` when `timestamp` is absent/empty
- `{header}` only when `body` is empty

where `timestamp = format_timestamp(message.get("timestamp"))` (ISO-style local datetime,
millis converted if >10,000,000,000; `app.py:511-527`), `author = message_author(message)`
(display_name → sender → sender_type → "Unknown"; `app.py:551-557`), and `body =
message_text(message)` (message + image/video/link description lines; `app.py:560-608`).
Blocks are joined by `"\n\n"` and the file ends with a trailing newline when non-empty
(`app.py:596-608`).

**Source:** `tomsegura2/Kindroid-Chat-Exporter`, `app.py:596-608`.

**Verdict:** RECORDED FOR READER 4. No `.txt` or `.md` reader is implemented in this
round. The exact block shape and line cite are preserved here so the plain-text reader
(reader 4) can consume Kindroid `.txt` exports without re-cloning the source.
