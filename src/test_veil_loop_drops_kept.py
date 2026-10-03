#!/usr/bin/env python3
"""Rung 1 — when she parrots her kept reply, the re-roll drops it instead of re-rolling against the same template.

Deck rung 3, 2026-10-03, Qwen3 on the full default: ritual answer #1 already told the whole origin; asked "how we met"
next, with that reply kept as her one assistant turn, she produced it VERBATIM three times through every escalated
re-roll — the loop guard killed all three and the stranger got the fallback stub, and the stub cleared her buffer.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_spine as S

KEPT = ("I remember the day we met — it was a thunderstorm, and the library's reading room had been emptied early "
        "because of the weather. I'd stayed behind to finish some research, huddled by the window.")
FRESH = "You came in out of the rain with your coat soaked through, and I offered you the chair by the radiator."
fails = []


class Parrot:
    def __init__(self):
        self.prompts = []

    def create_completion(self, prompt, **k):
        self.prompts.append(prompt)
        text = KEPT if KEPT in prompt else FRESH
        return iter([{"choices": [{"text": w + " ", "finish_reason": None}]} for w in text.split()])


def run(with_loop_prompt):
    llm = Parrot()
    S.get_llm = lambda *a, **k: llm
    conn = S.open_db(":memory:")
    turns = [{"role": "user", "content": "Tell me your name, and mine."},
             {"role": "assistant", "content": KEPT},
             {"role": "user", "content": "Tell me how we met."}]
    prompt = S.render_chat_turns("You are Wren.", turns)
    loop = S.bare_prompt("You are Wren.", turns) if with_loop_prompt else None
    out = S.generate_guarded(conn, 1, prompt, 120, "Wren", recent_replies=[KEPT], loop_prompt=loop)
    killed = conn.execute("SELECT count(*) FROM memory_quarantine WHERE source_table LIKE 'chat_loop%'").fetchone()[0]
    return out.strip(), llm.prompts, killed


def check(label, ok, got=""):
    print("  %s  %-62s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


print("\nRUNG 1 — A PARROTED KEPT REPLY IS RE-ROLLED WITHOUT IT")
print("=" * 74)
out, prompts, killed = run(False)
check("old path: every re-roll sees the same template -> the stub", out == S.ara_ghost.SOFT_FALLBACK.strip(), killed)
out, prompts, killed = run(True)
check("the parrot is still caught (one loop kill)", killed == 1, killed)
check("the re-roll's prompt no longer carries her kept reply", len(prompts) == 2 and KEPT not in prompts[1])
check("she answers fresh instead of the stub", out == FRESH, out[:40])
check("his words are still in the re-roll", "Tell me how we met." in prompts[1])
check("no kept turn -> no second prompt to fall back to",
      S.bare_prompt("S", [{"role": "user", "content": "hi"}]) is None)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  a parrot costs one re-roll, not her reply")
sys.exit(0)
