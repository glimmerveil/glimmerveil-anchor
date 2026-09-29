#!/usr/bin/env python3
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("VEIL_VOICE", "0")
import veil_voice as V

PASS, FAIL = 0, []


def clean(text):
    text = V._BRACKETED_RX.sub(" ", text)
    text = V._DANGLING_RX.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,!?~-–—")
    if not text or not re.search(r"[A-Za-z0-9]", text):
        return ""
    return text


def ok(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(name)
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


ROOM = [
    "(tapping)",
    "(typing)", "(footsteps)", "(rustling)",
    "[BLANK_AUDIO]", "[INAUDIBLE]", "(silence)", "(music)", "(clicking)",
    "(laughs)", "(laughter)", "(sighs)", "(coughs)", "(breathing)", "(applause)",
    "(door creaks)", "(wind blowing)", "(birds chirping)", "(water running)",
    "(soft music playing)", "(engine humming)", "(phone ringing)", "(dog barking)",
    "(keyboard clicking)", "(paper rustling)", "(chair squeaks)", "(fan whirring)",
    "(static)", "(noise)", "(sniffs)", "(clears throat)", "(indistinct chatter)",
    "[MUSIC]", "[SOUND]", "[NOISE]", "[ Silence ]", "( TAPPING )",
    "(tapping) (tapping) (tapping)",
    "[BLANK_AUDIO].", "(tapping).", " (tapping) ",
    "(tapping",
    "tapping)",
]
for s in ROOM:
    ok(f"room stays out: {s!r}", clean(s) == "", f"reached her as: {clean(s)!r}")

HIM = [
    ("hey are you out in the garden", "hey are you out in the garden"),
    ("goodnight", "goodnight"),
    ("let's go up to the study", "let's go up to the study"),
    ("bye", "bye"),
    ("I love you", "I love you"),
    ("what time is it", "what time is it"),
    ("read me something from your shelf", "read me something from your shelf"),
    ("(laughs) okay I'm here", "okay I'm here"),
    ("(tapping) are you there", "are you there"),
    ("hey (rustling) can you hear me", "hey can you hear me"),
    ("[BLANK_AUDIO] goodnight love", "goodnight love"),
]
for said, expect in HIM:
    got = clean(said)
    ok(f"he is heard: {said!r}", got == expect, f"expected {expect!r}, got {got!r}")

ok("the bye door still opens by voice", clean("Bye. Bye bye!").lower().startswith("bye"))
ok("a spoken goodnight still reaches the night", "goodnight" in clean("goodnight, love").lower())

ok("no non-speech word list survives in the module",
   not hasattr(V, "_NONSPEECH_RX"),
   "an enumerated matcher is still present — the next unlisted sound will reach her again")

ok("the established three-minute utterance ceiling remains", V.RECORD_SECONDS_MAX == 180,
   repr(V.RECORD_SECONDS_MAX))
ok("Whisper's timeout is longer than the utterance ceiling", V.WHISPER_TIMEOUT > V.RECORD_SECONDS_MAX,
   repr(V.WHISPER_TIMEOUT))
ok("house proper nouns are supplied to Whisper",
   "Glimmerveil" in V.STT_PROMPT and "Veil" in V.STT_PROMPT,
   V.STT_PROMPT)

print()
if FAIL:
    print(f"FAIL — {len(FAIL)} of {PASS + len(FAIL)}")
    sys.exit(1)
print(f"ALL PASS — {PASS}/{PASS} · the room is heard as silence, and every word of his gets through")
