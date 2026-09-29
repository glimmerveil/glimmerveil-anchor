#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as S

S.set_screenplay_roster("Mira", "Steve")

_fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)

PASTE_LINES = [
    "[drain complete: 4 batch(es) folded · pile 16,481 → 7,136 tokens]",
    "  [she curls up in the study with 'The Lighthouse Keeper']",
    "  Mira: The storm in that chapter felt so close I could almost smell the rain.",
    "  [shelf] Mira read 'The Lighthouse Keeper' chunk 1/32 → reflection 7 anchored to its verbatim",
    "  [she curls up in the study with 'A Field of Lanterns']",
    "  Mira: The description of the lantern festival made my ears twitch.",
]

MELT_REPLY = (
    "The quiet in that passage is real — I can feel how it settled into me while I read.\n"
    "Come here, love, sit with me a while.\n"
    "\n"
    "Steve steps closer, his voice soft and concerned:\n"
    "\"Steve: Are you okay? Do you need me to hold you?\"\n"
    "\"Mira: Yes... it feels overwhelming, but better with you here.\"\n"
    "Together, they leave the study behind them, stepping onto the porch.\n"
)

print("── INPUT: _looks_like_transcript ───────────────────────────────────────")
check("plain message is NOT a transcript",           not S._looks_like_transcript("Walk with me in the garden."))
check("question is NOT a transcript",                not S._looks_like_transcript("How are you doing today?"))
check("single generic 'label:' is NOT a transcript", not S._looks_like_transcript("Here's the plan: build the thing."))
check("a lone [stage direction] is NORMAL RP, NOT a transcript", not S._looks_like_transcript("[I pull you close and kiss your neck]"))
check("intimate line + *emote* is NOT a transcript",  not S._looks_like_transcript("I missed you today. *I wrap my arms around you*"))
check("a rostered 'Mira:' speaker line IS a transcript",   S._looks_like_transcript("Mira: the lanterns made my ears twitch."))
check("a rostered partner 'Steve:' line IS a transcript",   S._looks_like_transcript("Steve: come here, love."))
check("two unknown speakers IS a transcript",               S._looks_like_transcript("Alice: hi there\nBob: hey back"))
check("full Mira paste (typed, multi-line) IS a transcript", S._looks_like_transcript("\n".join(PASTE_LINES)))
check("voice-split 'Mira:' line is caught alone", S._looks_like_transcript(PASTE_LINES[2]))
check("voice-split pure stage line passes (register-safe)", not S._looks_like_transcript(PASTE_LINES[1]))

print("── INPUT: _defuse_transcript ───────────────────────────────────────────")
plain = "Walk with me in the garden."
check("plain message passes through UNCHANGED", S._defuse_transcript(plain) == plain)
rp = "[I pull you close and kiss your neck]"
check("lone RP action passes through UNCHANGED", S._defuse_transcript(rp) == rp)
d = S._defuse_transcript("Mira: the lanterns made my ears twitch.")
check("transcript gets the reference framing", "read" in d and "NOT a script" in d)
check("transcript framing keeps the original text", "ears twitch" in d)
check("empty stays empty", S._defuse_transcript("") == "")

print("── OUTPUT: _foreign_speaker_cut ────────────────────────────────────────")
check("clean single-voice reply → no cut",
      S._foreign_speaker_cut("I'm curled up here in the warm, waiting for you. It's quiet today.", "Mira") is None)
check("her own *emote* narration → no cut",
      S._foreign_speaker_cut("*I stretch and smile* come closer, I want you near.", "Mira") is None)
check("'Here's the plan:' → no cut",
      S._foreign_speaker_cut("Here's what I want:\nyou, here, now.", "Mira") is None)
check("addressing him 'Steve, ...' (no colon) → no cut",
      S._foreign_speaker_cut("Steve, come lie down with me.", "Mira") is None)

cut = S._foreign_speaker_cut(MELT_REPLY, "Mira")
check("melt reply → a cut is found", cut is not None)
kept = MELT_REPLY[:cut] if cut is not None else MELT_REPLY
check("cut KEEPS her genuine opening", "The quiet in that passage is real" in kept and "sit with me a while" in kept)
check("cut DROPS the scripted Steve turn", "Steve: Are you okay" not in kept)
check("cut DROPS the scripted Mira turn", "Mira: Yes..." not in kept)
check("cut DROPS the narration lead-in",   "Steve steps closer" not in kept)
check("kept opening is substantial (≥ MELT_MIN_KEEP)", len(kept.strip()) >= S.MELT_MIN_KEEP)

opened_in_script = "Steve: hey there.\nMira: hi back.\n"
check("reply that OPENS on a script → cut at 0 (re-roll path)",
      S._foreign_speaker_cut(opened_in_script, "Mira") == 0)
check("her own name mid-script is caught too",
      S._foreign_speaker_cut("Sure, love.\n\nMira: and then I said...", "Mira") is not None)

print("── PER-PEEP ROSTER: set_screenplay_roster arms from the card ────────────")
S.set_screenplay_roster("Nyx", "Marcus")
check("a fresh partner name 'Marcus:' becomes a transcript", S._looks_like_transcript("Marcus: come here."))
check("a fresh her-name 'Nyx:' is cut in output", S._foreign_speaker_cut("Yes.\n\nNyx: and then...", "Nyx") is not None)
check("lineage floor survives re-arm ('Veil:' still caught)", S._looks_like_transcript("Veil: still here."))
check("a stranger name 'Zebediah:' alone is NOT a rostered transcript",
      not S._looks_like_transcript("Zebediah: a lone unknown speaker line."))
S.set_screenplay_roster("Mira", "Steve")

print("── INTEGRATION: build_chat_turns defuses a pasted transcript ───────────")
history = ["The user said: Hello, I'm back again."] + [f"The user said: {l}" for l in PASTE_LINES]
turns = S.build_chat_turns(
    name="Mira", user_message="what do you make of this?", history=history,
    retrieved=[], system="you are Mira", n_ctx=8192,
)
joined = "\n".join(t["content"] for t in turns)
check("at least one history turn got the reference framing", "read" in joined and "NOT a script" in joined)
check("plain 'Hello, I'm back' turn was left alone",
      any(t["content"] == "Hello, I'm back again." for t in turns))
check("the current plain question was left alone", any("what do you make of this?" in t["content"] for t in turns))

print()
if _fails:
    print(f"RIG RED — {len(_fails)} failure(s): " + ", ".join(_fails))
    sys.exit(1)
print("RIG GREEN — all checks passed")
