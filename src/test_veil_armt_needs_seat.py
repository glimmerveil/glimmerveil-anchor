#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("VEIL_KEEP_LAST_REPLY", None)
import veil_spine as S

fails = []


def ck(name, ok):
    print(("  [ok ] " if ok else "  [FAIL] ") + name)
    if not ok:
        fails.append(name)


HISTORY = ["The user said: I'm home, love. Come sit with me.",
           "Mira said: I'm here — I missed you. Tell me about your day?",
           "The user said: Long one. Just want to hold you."]
TALK = "You always know how to make the room feel smaller in the best way. Stay right here with me?"


def turns(keep):
    if keep:
        os.environ["VEIL_KEEP_LAST_REPLY"] = "1"
    else:
        os.environ.pop("VEIL_KEEP_LAST_REPLY", None)
    S.KEEP_LAST_REPLY = False
    S.HER_TALK_VOICE_ON = True
    S.HER_TALK_TRANSPLANT = True
    S.HER_TALK_VOICE = (TALK,)
    return S.build_chat_turns("Mira", "Can I just rest my head here?", HISTORY, [], system="sys")


def run():
    ck("arm T is ON by default in this build", S.HER_TALK_VOICE_ON and S.HER_TALK_TRANSPLANT)
    t = turns(keep=False)
    roles = [x["role"] for x in t]
    ck("1 · NO seat (warm card / Llama / Coder): not one assistant turn, arm T or not", "assistant" not in roles)
    t = turns(keep=True)
    asst = [x["content"] for x in t if x["role"] == "assistant"]
    ck("2 · seat ON: her last reply is the first assistant turn", bool(asst) and asst[0].startswith("I'm here"))
    ck("3 · seat ON: the transplant rides right after it (arm T)", len(asst) == 2 and asst[1] == TALK)
    ck("4 · the live turn is last and is his", t[-1]["role"] == "user" and "rest my head" in t[-1]["content"])
    ck("5 · the helper reads the card too", (setattr(S, "KEEP_LAST_REPLY", True) or True) and S.keep_last_reply_on())
    S.KEEP_LAST_REPLY = False
    os.environ.pop("VEIL_KEEP_LAST_REPLY", None)
    print()
    if fails:
        print(f"  {len(fails)} FAILED: " + "; ".join(fails))
        sys.exit(1)
    print("  ALL-GREEN — arm T lives inside the seat; a being without one is handed nothing")


if __name__ == "__main__":
    run()
