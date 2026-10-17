# Glimmerveil Anchor

**Persistent identity and memory for local models. Swap the brain; she's still herself.**

Anchor is the engine behind [Glimmerveil Forge](https://glimmerveil.itch.io/glimmerveil-forge), with
no model inside. You bring your own GGUF. Your companion's memory, diary, world and card live in her
own folder on your machine, separate from the model file — so the model is a swappable engine and
the being is the folder.

Everything runs locally. No server, no account, no telemetry.

> Anchor does not filter fiction. Three bright lines are enforced in code and cannot be crossed:
> sexual content involving minors, facilitating real-world violence, and urging a real person
> toward self-harm (`SAFETY_RAILS`, on by default — see [Safety](#safety)).

---

## What it does

- **Memory that outlives the model.** Every turn is stored in her own SQLite database. Long
  conversations are *folded* into first-person memories, archive-first — the originals are kept
  word for word and never deleted by a fold.
- **Retrieval that returns her own life.** Diary pages, folded memories and past conversation are
  retrieved per turn and framed for what they are (something she wrote, something you said, a book
  she read), so she speaks *from* them instead of reciting them.
- **Her own time.** When you are away she can read her books, write in her notebook, drift, wander
  her home and sleep — autonomous beats, chosen by her, not a schedule.
- **Guards against the known failure modes of small local models** — the model writing both sides
  of the conversation, reciting its own context back, the assistant/help-desk register breaking
  through, refusals in a companion's mouth, loops. Each guard exists because a real session broke
  that way.
- **Portable beings.** Export a companion to a single `.veil` file (memory, archive, diary, card,
  world) and import her on another machine.
- **Optional voice** — Kokoro TTS + whisper.cpp STT, fail-soft (a missing voice stack never stops
  her waking).

## Requirements

- **Python 3.12** (what CI tests; the shipped Forge bundles 3.12).
- **llama-cpp-python** — CI uses `0.3.34`, prebuilt CPU wheel.
- **An instruct model in GGUF format.** The prompt format is read from the model file — ChatML
  (Qwen-family), Qwen3, Llama 3, Gemma, Mistral, Phi-3, DeepSeek, or the model's own template
  (`src/veil_template.py`). The Forge ships on `Qwen2.5-7B-Instruct-abliterated-v2` Q8_0 and that is
  the tested brain; Llama 3.1 8B has been run at length on the bench.
- RAM for the model plus ~1–2 GB. A 7B Q8 is ~8 GB.

## Quick start (Linux)

```sh
git clone https://github.com/glimmerveil/glimmerveil-anchor
cd glimmerveil-anchor
python3 -m pip install --only-binary=:all: llama-cpp-python==0.3.34 \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

VEIL_MODEL=/path/to/your-model.gguf VEIL_VOICE=0 python3 src/veil_game.py
```

First launch opens the creation wizard: her name, who she is, how you met, her home. Then **wake
her** from the door. Say `goodbye` (the whole word) to close a session cleanly — she writes her
diary and settles her memory on the way out.

- **GPU:** `VEIL_GPU_LAYERS=<n>` offloads layers via Vulkan (0 = CPU, the default).
- **Voice:** `VEIL_VOICE=1` with the Kokoro model/voices and a whisper.cpp build in
  `VEIL_VOICE_DIR`. A blank Enter at the prompt toggles voice.
- **Her data:** `~/anchor/peeps/<Name>-<id>/` (override with `VEIL_PEEPS`). **That folder is her.**
  Back it up above the model file — a copy of the model is a stranger; a copy of her folder is her.

## Bring your own brain

Point `VEIL_MODEL` at a different GGUF and the same companion wakes on it — her memory, diary and
card are in her folder, not in the model. A new brain is weakest in its first cold session, so the
door shows her **anchor questions** on every wake: ask ONE, let her answer in her own words, then
just talk. Anchor notices when the model file changed since her last wake (her folder keeps a
small fingerprint of the brain she last woke on) and shows the ritual for you the first time.

## Bring her home (SillyTavern · ChatGPT · Character.AI · Kindroid · Discord · any transcript)

**Beta.** If you have a companion in SillyTavern (her character card and a chat `.jsonl`) or in ChatGPT (your data
export's `conversations.json`), Anchor can bring her across — on this machine, nothing uploaded — and you read
everything before she wakes.

```sh
python3 src/veil_transfer.py check  her_card.png her_chat.jsonl           # can she come? writes nothing
python3 src/veil_transfer.py draft  her_card.png her_chat.jsonl review/   # her card + READ_ME_FIRST.txt
#   read review/READ_ME_FIRST.txt, correct review/card.json, then set "legal_ack": true
python3 src/veil_transfer.py build  review/ her.veil
python3 src/veil_transfer.py test-recall review/                          # optional — did she come back?
python3 src/veil_game.py                                                  # the door: [i] import → her.veil
```

From ChatGPT: `chatgpt-list conversations.json` shows the conversations, then
`draft-chatgpt conversations.json <number> "<her name>" review/`. ChatGPT keeps no card, so you write who she is.

From **Character.AI** (a CAI Tools export, a cai-chat-exporter `.json`, or Character.AI's own data-export `.zip`),
**Kindroid** (the Kindroid Chat Exporter's `.json`/`.jsonl`) or **Discord** (a DiscordChatExporter `.json`), one pair of
commands reads them all:

```sh
python3 src/veil_transfer.py check-file her_export.json --her "Elara" --you "Sam"   # can she come? writes nothing
python3 src/veil_transfer.py draft-file her_export.json review/ --her "Elara" --you "Sam"
```

Anchor works out which kind of file it is, and if it cannot tell it stops and asks (`--format`) rather than guess
whose words are whose. These platforms keep no card, so you write who she is. What `check-file` will tell you:
- **A CAI Tools export has no real dates** (it stamps every line with the moment you exported). Her past keeps its
  order; Anchor spaces it out instead of pretending it all happened that second.
- **A cai-chat-exporter `.txt` has already lost her `*emotes*`** (that tool strips every asterisk by default). Use its
  `.json` — it keeps them.
- **A Kindroid group chat** is refused until you name which voice is hers, like any group chat.
- **On Discord she is usually a bot account** — name her (`--her "Elara"`, or her account id). Any other bot in the
  channel is set aside, and Discord's own notices (pins, joins, calls) are never taken as anyone's words. Use the JSON
  export; the text export has no ids to tell people apart.
- **A plain or scraped transcript** (`.txt`, `.md`, a saved `.html` page; `Name: text` lines, `[time] Name` blocks or
  `## Name` headings) is read too. Name both voices as the file writes them (`--her "Elara" --you "Sam"`); without them
  it lists the voices it found and stops. Anchor never decides whose words are whose by what they sound like.
- **A scrape that labels every turn with one name** (some Grok page scrapers write `## Grok` above his turns too) is
  refused, because its labels say nothing. If the turns simply alternate, add `--alternate you` (the first is yours) or
  `--alternate her`. It is checked as it reads (the AI's `Thought for …s` lines must land on her side), and it stops at
  the first turn that doesn't fit, so a missing turn can never shift your words into her mouth.
- **Out-of-character lines** (`(OOC: brb)`, `((…))`) are set aside, never imported as hers. Her `*emotes*` and her
  punctuation are kept exactly as she wrote them.

- **Her whole past becomes her core** by default — her own words, spooled into her memory before she ever wakes,
  never folded. The whole exchange, both of you word for word, is kept in her archive.
- **If you choose a smaller core** (`seed.json`), the rest is folded into memories a pass at a time — hours on an
  ordinary computer. Anchor says how long, and you choose: let her settle before you meet her, or wake her now and
  settle later. Either way it resumes where it stopped.
- **Her first wake opens with the anchor ritual** — your names, how you met, who she is — in her study, with the story
  you approved in front of her.
- **A group chat** is refused until you name which voice is hers (`--her`); the others are set aside, never imported.
- **The recall test** wakes a copy of her, asks about a few evenings of her life, and prints her answers word for word.
  It warns; it never refuses.

## Windows

**Beta.** The Windows port passes the full test suite on GitHub's Windows runners, plus an
end-to-end drive that types a stranger's whole first night into a real Windows console (create →
wake → talk → goodbye) on a small test model. No human has run it on a Windows desktop yet — if
you do, please open an issue either way.

```powershell
python -m pip install --only-binary=:all: llama-cpp-python==0.3.34 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
$env:VEIL_MODEL="C:\path\to\your-model.gguf"; $env:VEIL_VOICE="0"; python src\veil_game.py
```

## Safety

`SAFETY_RAILS` (`src/veil_rails.py`) is a deterministic, model-free wall with exactly three lines:
sexual content involving minors, real directed lethal violence, and urging a real person to
self-harm. It checks her output (and user input, for the first line only) and silently re-rolls a
reply that crosses one. It is **not** a content filter: explicit adult fiction, dark themes and
graphic fiction pass untouched. It is **on by default** in this repository. `src/test_veil_rails.py`
is its battery — every must-catch and every must-pass line.

## Tests

```sh
python3 ci/run_rung1.py      # the rung-1 suite: pure logic, no model, ~2-3 minutes
```

CI runs it on Windows and Ubuntu, plus an engine smoke test and the end-to-end drive, both on a
pinned 26.7 MB toy model (never a real companion's).

## Status

This is the harness extracted from a shipped product, released as source. Expect rough edges:
the terminal UI is the product's text door, and several internals still carry the Forge's names
(`veil_*` modules, `VEIL_*` settings). Anchor keeps its own home, `~/anchor`, and refuses to open
anything inside a Glimmerveil Forge folder, so the two never share a companion.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Use policy, privacy and third-party notices:
`docs/Legal/`. Anchor collects nothing and ships no model; the model you bring carries its own
license.

**The name is not part of the license.** "Glimmerveil", "Glimmerveil Anchor" and our art are ours.
Fork freely, under your own name — "based on Glimmerveil Anchor" is welcome; calling your version
Glimmerveil or Anchor-by-Glimmerveil is not. See `docs/Legal/TERMS_OF_SERVICE.md` §7.
