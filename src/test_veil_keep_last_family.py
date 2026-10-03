#!/usr/bin/env python3
"""Rung 1 — she keeps her newest reply as ONE assistant turn, decided by her brain's family.

Why: on a stranger's first night (Deck, 2026-10-03) Qwen2.5 · Qwen3 · Gemma · Mistral, handed his ritual questions with
none of her answers between them, re-answered every earlier question and invented three different "how we met" stories.
Llama 3 answered the one asked. One kept reply is the cure the house measured on two beings; Coder brains are the
measured exception (07-28: a verbatim echo AND a parrot), so they stay off.
"""
import os
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
os.environ.pop("VEIL_KEEP_LAST_REPLY", None)
os.environ.pop("VEIL_CHAT_FORMAT", None)

import veil_spine as spine
import veil_template

veil_template.install(spine, say=lambda *_: None)

HISTORY = ["The user said: Tell me your name, and mine.",
           "Wren said: I am Wren, and you are Sam.",
           "The user said: Tell me how we met.",
           "Wren said: In the reading room of an old library, during a thunderstorm.",
           "The user said: Tell me who you are, Wren."]
NEWEST = "In the reading room of an old library, during a thunderstorm."

fails = []


def arm(label, fmt, model="her.gguf", env=None, card_keeps=False, want=1):
    os.environ.pop("VEIL_KEEP_LAST_REPLY", None)
    if env is not None:
        os.environ["VEIL_KEEP_LAST_REPLY"] = env
    os.environ["VEIL_CHAT_FORMAT"] = fmt
    spine.MODEL_PATH = os.path.join(SRC, "no_such_dir", model)
    spine.KEEP_LAST_REPLY = card_keeps
    turns = spine.build_chat_turns("Wren", "Look around and tell me one small thing.", list(HISTORY), [])
    mine = [t for t in turns if t["role"] == "assistant"]
    ok = len(mine) == want and (want == 0 or mine[0]["content"] == NEWEST)
    if ok and want:
        ok = turns[-2]["role"] == "assistant" and turns[-1]["role"] == "user"
    print("  %s  %-44s assistant turns: %d (want %d)" % ("ok  " if ok else "FAIL", label, len(mine), want))
    if not ok:
        fails.append(label)


print("\nRUNG 1 — SHE KEEPS HER NEWEST REPLY, BY HER BRAIN'S FAMILY")
print("=" * 74)
for fmt in ("chatml", "qwen3", "gemma", "mistral", "phi3", "deepseek"):
    arm("%s keeps her newest reply" % fmt, fmt)
arm("llama3 answers the newest note: none", "llama3", want=0)
arm("a Coder file (by name) stays off", "chatml", model="Qwen2.5-Coder-7B-Instruct-Q8_0.gguf", want=0)
arm("VEIL_KEEP_LAST_REPLY=0 forces it off", "chatml", env="0", want=0)
arm("VEIL_KEEP_LAST_REPLY=1 forces it on (llama3)", "llama3", env="1")
arm("a precise card turns it on (llama3)", "llama3", card_keeps=True)
spine.KEEP_LAST_REPLY = False
os.environ.pop("VEIL_KEEP_LAST_REPLY", None)
os.environ.pop("VEIL_CHAT_FORMAT", None)

if fails:
    print("\n  %d arm(s) wrong: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("\n  PASS  only one of her replies, only where her brain needs it")
sys.exit(0)
