#!/usr/bin/env python3
"""Rung 1 — the door says plainly when a brain is a poor home for her.

Deck rung 3, 2026-10-03: DeepSeek-R1-Distill (a reasoning model) recited her own place block and said "My name is
[Your Name]"; Llama 3.2-1B wrote his part of every scene — and was NOT flagged after all: it is byte-identical to Pixie Prime's
brain (~/pixie.gguf), and she holds herself on it. Size is not the limit; the prompt shape is. Only the reasoning
model gets a note. Nothing is refused.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_template as T

DIR = os.path.join(HERE, ".fit_notes_fixtures")
fails = []


def gguf(name, arch, layers, width, tpl):
    def s(x):
        b = x.encode("utf-8")
        return struct.pack("<Q", len(b)) + b
    kv = [(s("general.architecture") + struct.pack("<I", 8) + s(arch)),
          (s("tokenizer.chat_template") + struct.pack("<I", 8) + s(tpl)),
          (s(arch + ".block_count") + struct.pack("<II", 4, layers)),
          (s(arch + ".embedding_length") + struct.pack("<II", 4, width))]
    os.makedirs(DIR, exist_ok=True)
    p = os.path.join(DIR, name)
    with open(p, "wb") as f:
        f.write(b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv)) + b"".join(kv) + b"\0" * 64)
    return p


def notes_for(path):
    T._CACHE.clear()
    fam = T.family_for(path)[0]
    return T.fit_notes(fam, T.gguf_meta(path))


def check(label, ok, got):
    print("  %s  %-48s %s" % ("ok  " if ok else "FAIL", label, [n[:40] for n in got]))
    if not ok:
        fails.append(label)


LLAMA = "<|start_header_id|>user<|end_header_id|>"
CHATML = "<|im_start|>user"
DEEPSEEK = "<｜User｜>{{x}}<｜Assistant｜>"
try:
    print("\nRUNG 1 — THE DOOR NAMES A POOR HOME, ONCE, AND REFUSES NOTHING")
    print("=" * 74)
    n = notes_for(gguf("llama-1b.gguf", "llama", 16, 2048, LLAMA))
    check("Llama 3.2-1B shape (16 x 2048) -> nothing (Pixie Prime runs this brain)", n == [], n)
    n = notes_for(gguf("llama-8b.gguf", "llama", 32, 4096, LLAMA))
    check("Llama 3.1-8B shape (32 x 4096) -> nothing", n == [], n)
    n = notes_for(gguf("gemma-4b.gguf", "gemma3", 34, 2560, "<start_of_turn>user"))
    check("Gemma 3-4B shape (34 x 2560) -> nothing", n == [], n)
    n = notes_for(gguf("deepseek-7b.gguf", "qwen2", 28, 3584, DEEPSEEK))
    check("DeepSeek-R1-Distill -> reasoning", len(n) == 1 and "reasoning" in n[0], n)
    n = notes_for(gguf("qwen3-8b.gguf", "qwen3", 36, 4096, CHATML + " enable_thinking"))
    check("Qwen3 with thinking OFF -> nothing", n == [], n)
    n = notes_for(gguf("noshape.gguf", "llama", 0, 0, LLAMA))
    check("no shape in the file -> nothing guessed", n == [], n)
finally:
    import shutil
    shutil.rmtree(DIR, ignore_errors=True)

if fails:
    print("\n  %d case(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  a reasoning brain is named; the rest are left alone")
sys.exit(0)
