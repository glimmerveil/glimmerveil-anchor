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
- **A ChatML instruct model in GGUF format.** The prompt template and stop tokens are ChatML
  (Qwen-family). The Forge ships on `Qwen2.5-7B-Instruct-abliterated-v2` Q8_0 and that is the
  tested brain. A Llama-3-template model is **not** wired yet.
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
