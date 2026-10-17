# Discord intake source proof (reader 3 of 4)

Scope: the DiscordChatExporter JSON export consumed by `src/veil_intake_discord.py`. Each claim
is followed by its source and a verdict. Test fixtures are invented content with invented
snowflake ids; no real person's words or real Discord ids are used.

Drafted from a scout's report; **reviewed and verified by hand on 2026-10-17** against a
read-only clone of the exporter. The review overturned four of the draft's rules. They are
listed at the end, because each one would have put the wrong words in her mouth.

## Source inventory

| Source | URL | Files | Verification status |
|---|---|---|---|
| Tyrrrz/DiscordChatExporter | https://github.com/Tyrrrz/DiscordChatExporter | @`276471f`: `DiscordChatExporter.Core/Exporting/JsonMessageWriter.cs`, `Discord/Data/Message.cs`, `Discord/Data/MessageKind.cs`, `Exporting/ChannelExporter.cs`, `Exporting/ExportRequest.cs`, `Exporting/PlainTextMessageWriter.cs`, `Exporting/PlainTextMessageExtensions.cs` | VERIFIED-BY-HAND |

License note: DiscordChatExporter is MIT-licensed. This reader references only the shape of
the JSON files it produces. Fixtures are invented and reproduce no repository code.

---

## F1. Top-level JSON shape

**Claim:** the top level is `{guild, channel, dateRange, exportedAt, messages, messageCount}`.
Each message has `id`, `type`, `timestamp` (ISO-8601), `timestampEdited`,
`callEndedTimestamp`, `isPinned`, `content` and `author`, then attachments, embeds, stickers,
reactions and mentions, and optionally `reference` and `interaction`.

**Source:** `JsonMessageWriter.cs` — `WritePreambleAsync` :374-428 (guild :382, channel :394,
dateRange :419, exportedAt :425, messages :428), `messageCount` :636, `WriteMessageAsync`
:432-470.

**Verdict:** VERIFIED-BY-HAND. The door's sniffer (`veil_transfer.detect_format`) names a file
`discord` from the `guild`/`channel`/`messages` envelope. Without the envelope, it names it
`discord` only if the author carries Discord's own fields (`isBot` / `discriminator`). A CAI
turn also has an `author`, so that alone is never enough.

## F2. Author identity is the id; the nickname is unstable

**Claim:** `author` is `{id, name, discriminator, nickname, color, isBot, roles, avatarUrl}`.
`nickname` is the server display name if there is one, otherwise the user's display name. It
changes per server and over time.

**Source:** `JsonMessageWriter.cs` `WriteUserAsync` :41-59 (`nickname` :53-56 =
`Context.TryGetMember(user.Id)?.DisplayName ?? user.DisplayName`, `isBot` :59).

**Verdict:** VERIFIED-BY-HAND. Every identity decision is keyed by `author.id`. `--her` and
`--you` take the id, or `nickname:Name` / `name:username` / a bare name for a person reading
the file.

## F3. Order: the exporter can write newest-first

**Claim:** an export made with reverse order is written newest-first.

**Source:** `ChannelExporter.cs` :67 (`!request.IsReverseMessageOrder ? GetMessagesAsync :
GetMessagesInReverseAsync`), `ExportRequest.cs` :36.

**Verdict:** VERIFIED-BY-HAND. The reader **sorts by timestamp**, using the file index to break
ties. Test shape 14, and the end-to-end drive, which exports newest-first.

## F4. System notices: the exporter's own rule, and its made-up sentence

**Claim:** a message is a system notice if and only if its kind is RecipientAdd (1) through
ThreadCreated (18), or PollResult (46). For those, the exporter writes into `content` a
sentence **it composes** ("X pinned a message", "X started a call"), and attributes it to
whoever triggered it. `type` is `Kind.ToString()`, so a kind that is not in the exporter's
enum is written as a **bare number**.

**Source:** `Message.cs` :43-46 (`IsSystemNotification`), `MessageKind.cs` :4-18 (the enum:
Default 0 … ThreadCreated 18, Reply 19, ThreadStarterMessage 21, PollResult 46),
`JsonMessageWriter.cs` :443 (`type`) and :456-458 (system rows: `content =
GetFallbackContent()`), `PlainTextMessageExtensions.cs` :12.

**Verdict:** VERIFIED-BY-HAND. System notices are **set aside and counted**, and are never
imported as anyone's words. The door tells the person how many there were. **Every other kind
is speech**, including Reply (19), ThreadStarterMessage (21), and the bare numbers outside
the enum, such as 20 (a reply to a slash command). Test shapes 13 and 15.

## F5. Who is who: her is never inferred

**Claim:** a companion on Discord usually runs as a **bot account**. A channel can also hold
other bots (music, moderation) and other people.

**Verdict:** IMPLEMENTED.
  - `--her` is required. If it is missing, the reader refuses with a hint that lists the bots.
    When the channel has exactly one bot and one human, the hint names that bot.
  - A bot **can** be her when named.
  - `you` is the one human left once her is known. With two or more humans, `--you` is
    required.
  - Every other author is `other`: set aside, named in `set_aside_speakers`, and never put in
    her mouth.

## F6. Text and cleaning

**Claim:** `content` may be empty on a message that is only an attachment, embed or sticker.

**Verdict:** IMPLEMENTED. Empty content falls back to the attachment's file name and URL, the
embed's description or URL, or the sticker's name. Each fallback is counted, and the door says
how many lines were kept as a placeholder. Every line then passes through `veil_intake_clean`:
whole-line OOC asides and page markup are set aside and counted. Her words and her `*emotes*`
are never edited.

## F7. Plain-text and HTML exports are refused

**Source:** `PlainTextMessageWriter.cs` :24-34 (`[date] FullName` header, no message id, no
author id).

**Verdict:** VERIFIED-BY-HAND. The text export has no author ids, so it cannot tell two people
with the same display name apart. The reader asks for the JSON export.

---

## Corrections made in the 10-17 review (red-proofed against the draft reader)

| | the draft did | why it was wrong | now |
|---|---|---|---|
| S1 | "bots are never her"; a lone human inferred as her | Most Discord companions **are** bots. Inferring the lone human as her imports **the person's own words as hers**. | her never inferred; a bot can be her when named |
| S2 | system notices imported | Their text is a sentence the exporter wrote (F4), attributed to her if she pinned something | set aside, counted, reported |
| S3 | Reply (19) counted as system | A reply is speech; her answers would be lost | kept |
| S4 | no sort ("the exporter writes chronological order") | Reverse exports exist (F3) | sorted by timestamp |
| S5 | (review's own first fix) a whitelist of speech kinds | A slash-command answer is kind 20, written as `"20"`, and the whitelist dropped it. **A slash-command companion would have lost every line.** | the exporter's own system rule (F4), nothing wider |

The draft reader fails S1–S4 under the reviewed tests (and crashes on `her=` naming a bot).
The review's first whitelist fails S5 (test shape 15). The reader as shipped passes all of
them.

## Open edges

1. **A slash-command companion's export has no words from the person.** Discord stores the
   command used (`interaction: {id, name, user}`, `JsonMessageWriter.cs` :597-603), not the
   options the person typed. Her answers come across; his prompts are not in the file. The
   gate then reports that one side is missing, and that is the truth about the file.
2. **`reference` / forwarded messages:** only the message's own content is imported, not the
   quoted message.
3. **Reactions, mentions, inline emoji:** not turned into text.
