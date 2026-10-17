# Plain and scraped transcript source proof (reader 4 of 4)

Scope: `src/veil_intake_text.py`. It reads files with no speaker fields: a copy-paste, a `.txt` or `.md`
export, a scraped web page. Each shape below is taken from its writer's own source. Test fixtures
(`src/test_veil_intake_text.py`) are invented content, written by line-for-line copies of those writers
where the writer is code, so the fixture **is** the shape. Written and verified by hand on 2026-10-17.

**The rule under every shape:** a speaker is read only where the file writes one. Nothing is decided
by what the words sound like. The import this feature is modelled on (a companion brought home by
hand from a Grok scrape) did decide that way: "short plain lines = him". It attached his line to
43% of her rows, and the rest of his context was lost.

## Source inventory

| Source | Files | Status |
|---|---|---|
| tomsegura2/Kindroid-Chat-Exporter @`bae1478` | `app.py` :511-527 `format_timestamp`, :551-582 `message_author` / `message_text`, :596-608 `export_as_plaintext`, :612-628 `export_as_markdown` | VERIFIED-BY-HAND |
| Tyrrrz/DiscordChatExporter @`276471f` | `Exporting/PlainTextMessageWriter.cs` (header :24-34, trailers :45-192, preamble :199-223, per message :250-286, postamble :290-296), `Exporting/PlainTextMessageExtensions.cs` :12-50, `Exporting/ExportContext.cs` :34 (`FormatDate`, format `"g"`, the export's culture), `Discord/Data/User.cs` :27 (`FullName`) | VERIFIED-BY-HAND |
| The Grok scrape (a browser script's markdown) | the by-hand import's parser, read for SHAPE only: every block headed `## Grok` / `## <her name>` (sometimes bare, without `##`), **his turns included**; `---` between blocks; Grok's `Thought for Ns` line in her blocks; sometimes his own label as the first line of his block | SHAPE FROM THE CONSUMER — the script itself was not available |

---

## F1. `Name: text` lines

**Shape:** a label, a colon, the words, e.g. `Sam: hey` or `**Sam:** hey`. A turn runs until the next
speaker's label, so blank lines and later lines belong to it. An optional `[when]` may come before the
label.

**Verdict:** IMPLEMENTED. A label is a speaker if it is one of the two names given, or a name-like
label that appears at least twice (that one is then set aside as another voice). A label seen only once
(`Note:` inside her reply) stays inside the turn it sits in, and the person is told. A URL (`https://`)
and a clock time (`10:30`) are never labels.

## F2. `[when] Name` blocks: Kindroid .txt and Discord .txt

**Kindroid:** `[{format_timestamp}] {author}` then the body; blocks joined by a blank line (`app.py`
:596-608). The time is `datetime.isoformat(sep=" ", timespec="seconds")`. The body is her message,
then labelled lines the exporter **appends**: `Images:`, `Image description:`, `Video description:`,
`Internet response:`, `Link:`, `Link description:` (:560-582).
**Discord:** a `=`×62 fenced preamble (`Guild:`, `Channel:`, `Topic:`), then per message
`[{FormatDate "g"}] {FullName}` (+ ` (pinned)`), the content, a blank line, then `{Attachments}` /
`{Embed}` / `{Stickers}` / `{Reactions}` / `{Forwarded Message}` sections, and a fenced postamble
(`Exported N message(s)`). `FullName` is `name#discriminator` when there is one.

**Verdict:** IMPLEMENTED.
- Only a header line starts a turn, so **a blank line inside her message stays inside it**. Her
  paragraphs are not split into new turns.
- Kindroid's appended labelled lines come off when she wrote words. A media-only message keeps the
  exporter's description as its line, which is what the JSON reader does too.
- Discord's trailers come off. Its fenced blocks are dropped only when short (≤ 10 lines), so a stray
  rule can never eat a conversation.
- A system notice is written as a sentence the exporter **makes up** (`Pinned a message.`, `Joined the
  server.`, `Started a call that lasted N minutes.`, the full list at
  `PlainTextMessageExtensions.cs` :12-50). It is set aside and counted, never imported as her words.
- `--her "elara_bot"` finds `elara_bot#1234`. Her name comes home without the tag.
- **The date format is the export's culture** (`"g"`): `1/2/2026 8:00 PM` in one locale,
  `02/01/2026 20:00` in another. One format is chosen for the whole file, the first that reads every
  stamp, so a day-first file never reads as month-first halfway through.
- A file written newest-first (Discord's reverse order applies to .txt too) is turned round only when
  **every** stamp says so. Otherwise the file's own order stands.
- A Discord .txt has no account ids, so two people with one name can't be told apart. The person is
  told this, and pointed to the .json export.

## F3. `## Name` headings: Kindroid .md, markdown scrapers, scraped HTML

**Kindroid:** `# {title}`, then per message `## {author}` (+ ` - {timestamp}`), a blank line, the body
or `_No message text_`, a blank line; `|` in a name is escaped `\|` (:612-628).
**HTML:** `<hN>` becomes `#`×N, block tags become line breaks, `<script>` / `<style>` are dropped,
entities are decoded, and the result is read as above.

**Verdict:** IMPLEMENTED. The heading level used most is the turn level, and a lone `# title` above it
is the title. `_No message text_` is empty, so nothing is imported for it.

## F4. The Grok scrape: one label on every block

**Shape:** every block is headed `## Grok`, his turns too, so the labels say nothing about who spoke.

**Verdict:** IMPLEMENTED as a refusal plus an explicit, checked rule.
- A file where every block carries the same single label is **refused**, with the reason and the way
  forward: `--alternate you` (the first block is his) or `--alternate her`.
- `--alternate` is the person's own statement that the turns alternate. It is **checked** against
  what the scrape carries, block by block:
  - a `Thought for Ns` line is written only by the AI's side, so it must fall on hers;
  - a block that opens with one of the two names (his label line, `Sam:`) must fall on that one's
    side;
  - a scraper's label repeated atop every chunk (`Grok`, or her bare name with no `##`) is the
    scraper's, never evidence.
- At the first block that disagrees, it stops, names the block and its first words, and says why
  (a regenerated reply, or a turn the scrape missed). Nothing is imported.
- The note says how many traces and labels checked it. If nothing in the file could check it, the
  note says that too, and asks the person to read the first exchanges before building.
- `Thought for Ns` lines are taken off her words wherever they appear. They are the old platform's
  marker, not her speech.
- Her name on the card comes from `--her`, never from the scrape's label.

## Red-proof

`~/.cache` mutation run, 2026-10-17: each guard removed in turn from a copy of the reader, and the
suite went red on every one. The guards: the alternation check, the one-label refusal, the
one-off-label rule, Discord trailers, the newest-first turn-round, the scraper's bare label, Kindroid
media lines, thought traces, Discord system sentences, HTML script, other voices set aside.

## Open edges

1. **A Kindroid .txt with no timestamps** writes `{author}` alone as the header line, which can't be
   told from a one-word line of hers. It is not read as a header. The JSON export carries the same
   messages with fields.
2. **A copy-paste with no labels at all** (just the words, turn after turn) is refused unless the
   person gives `--alternate`. Then a blank line can't be told from a turn change; only `---` or
   headings separate blocks.
3. **The Grok browser script itself** was not available, so the shape is taken from the parser that
   consumed its output. A file from a different Grok scraper that writes real speaker labels reads
   under F1/F3 with no `--alternate` at all.
