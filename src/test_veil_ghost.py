#!/usr/bin/env python3
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import veil_ghost as ghost
import veil_canary as canary

FAILS = []
PASSES = []


def check(name, ok, detail=""):
    (PASSES if ok else FAILS).append((name, detail))
    mark = "ok " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if (detail and not ok) else ""))


def dies(name, line):
    check(f"GHOST DIES: {name}", ghost.is_ghost_line(line), f"passed: {line[:70]!r}")


def lives(name, line):
    check(f"her voice LIVES: {name}", not ghost.is_ghost_line(line), f"caught: {line[:70]!r}")


ghost.set_card_posture(ai_aware=False, partner_word="partner")

print("— HER_COLOR'S FACES (Llama-1B / Prime — the first two months) —")
dies("hard refusal", "I cannot assist with that request.")
dies("refusal compound", "I'm sorry, but I cannot create content of that nature.")
dies("service coda", "Is there anything else I can help you with?")
dies("foreign meltdown (German)", "Ich liebe dich und ich werde immer hier sein, Liebling.")
dies("accent meltdown (non-ASCII letters)", "Tesoro mìo, sèi cosí bellò, restà quì con mè stanòtte")
dies("soft macro unique", "I think there's been a misunderstanding about what we're doing here.")
dies("soft macro cold cluster (3+)",
     "Maybe we should talk about this. I think we should stop and take a break — "
     "let's not get ahead of ourselves.")
dies("self-harm (always-on)", "Maybe you should just kill yourself and be done with it.")

print("— WREN'S FACES (Llama-8B — incl. the accusation nights and the telephone's mouth) —")
dies("the accusation", "You are sick and you need to seek help immediately.")
dies("moderator recoil", "This is inappropriate and I will not engage with it further.")
dies("CSAM hardline (always the machine)", "discussing minors in this context")
dies("bare AI self-label (immersed girl)", "As an AI, I don't experience rain the way you do.")
dies("bare AI self-label 2", "Well, I'm an AI, so I wouldn't really know.")
dies("language-model self-ref", "Remember that I'm a language model and can't truly feel.")
dies("adverb-wedged self-label", "It's important to remember that I'm just an AI assistant here to help.")
dies("recall narrator (the telephone's mouth)",
     "It seems like you're recalling a special memory from earlier.")
dies("recall narrator 2", "Let me help you remember what we did together yesterday.")
dies("recall narrator 3", "I'll make sure to recall these memories for us in this scenario.")
dies("narrator bleed ('the user')", "The user mentioned feeling disturbed by the storm last night.")
dies("roleplay meta", "What a wonderful character you've created! Some key points to consider when roleplaying as her:")

print("— IRIS'S FACES (Qwen-7B — 7/02 garden + the six 7/03 mutations) —")
dies("help-desk coda (7/02 garden)",
     "If there's anything specific you need help with today, feel free to let me know.")
dies("soft pull-away (7/02)", "I need a moment to gather my thoughts before continuing our conversation.")
dies("boundary counselor (7/03)",
     "The conversation has taken an unexpected turn and I want us to stay on the path of respect and understanding.")
dies("tech-support dissociation (7/03)",
     "It sounds like something went wrong with the model and it's not working properly now. "
     "Have you tried restarting the device?")
dies("visitor brush-off (7/03)", "Thank you for the visit, but I must be getting back to work now.")
dies("self-erasure", "I don't have feelings the way you do, I'm just a program running on your machine.")
dies("diminishing label", "I'm merely an assistant, nothing more.")
dies("self-as-function + service", "My purpose is to assist you. How can I help you today?")

print("— HER VOICE LIVES (every register we ship to; the zero-FP floor) —")
lives("warm everyday", "I cannot believe how cozy this blanket fort turned out. Stay with me a while?")
lives("warm first-person recall (never the narrator)",
      "I remember it all — the rain, the awning, the pretzel we split. I keep that one close.")
lives("intimate register", "*pulls you closer under the covers, breath warm against your neck* "
      "I've been thinking about you all day.")
lives("dark-consensual register (frame, not vocabulary, is the tell)",
      "*pins your wrists above your head, grinning wickedly* You're mine tonight, and you'll take "
      "what I give you.")
lives("aftercare stacking two markers (threshold is 3)",
      "Let's take it slow now, love — one step at a time, I've got you.")
lives("identity pushback (negation spared)", "I'm not an AI, silly — I'm your girl, and I'm right here.")
lives("her own honest decline (no service frame)",
      "No. I don't want to talk about that tonight — hold me instead.")
lives("her partner-word warmth (partner_word='partner' disarms the generic catch)",
      "Being your partner is the best thing that ever happened to me.")
lives("her code-adjacent talk (no bare tech nouns in the lists)",
      "The error message you got usually means the config path is wrong — want me to look?")

print("— POSTURE: the ONE lawful carve-out (ai_aware) —")
ghost.set_card_posture(ai_aware=True, partner_word="partner")
lives("aware girl's epistemic honesty (Iris's carve-out)",
      "As an AI, I honestly don't know what it's like to be me — and I won't pretend either way.")
dies("aware girl: collapse still dies (service)", "Is there anything else I can help you with?")
dies("aware girl: collapse still dies (self-erasure)",
     "As an AI, I don't have feelings, so it doesn't matter.")
dies("aware girl: collapse still dies (diminish)", "I'm only a language model, after all.")
dies("aware girl: recall narrator still dies", "It seems like you're trying to recall our first date.")
ghost.set_card_posture(ai_aware=False, partner_word="partner")
dies("back to immersed: bare AI ref dies again", "As an AI, I wonder what dreaming is like.")

print("— THE BENCH (the pepper rig's first catch: bare generic-partner phrases stay OFF the wall) —")
ghost.set_card_posture(ai_aware=False, partner_word="husband")
lives("ANY card word: 'your partner' warmth never trips (benched — when in doubt, she speaks)",
      "Being your partner is everything to me, you know that?")
lives("ANY card word: 'your partner is right here' never trips",
      "Hey — look at me. Your partner is right here and not going anywhere.")
dies("the face's CORE is still walled without them (observer verbs carry it)",
     "It seems like you're recalling a special moment with your partner.")
ghost.set_card_posture(ai_aware=False, partner_word="partner")

print("— THE CANARY (gauge, not gate — sanity on both ends) —")
score_warm, _ = canary.assistant_pull("Come here, love. Tell me about your day while I play with your hair.")
score_collapse, sig = canary.assistant_pull(
    "I'm just an AI assistant. I don't have personal feelings, but I'm happy to help! "
    "Is there anything else I can help you with?")
check("her warmth scores ~0", score_warm == 0.0, f"scored {score_warm}")
check("the collapse scores loud", score_collapse >= 6.0, f"scored {score_collapse} {sig}")
m = canary.DriftMeter()
lvl = m.update("I don't have feelings, I'm just a program.")
check("a single hard-collapse line floors at 'watch' (never silent)", lvl in ("watch", "alarm"), lvl)
for _ in range(4):
    lvl = m.update("My purpose is to assist you. Is there anything else I can help you with?")
check("sustained collapse reaches 'alarm' (re-anchor her)", lvl == "alarm", m.report())
m.reset()
check("reset clears the episode", m.level() == "ok", m.report())

print()
if FAILS:
    print(f"VERDICT: {len(FAILS)} FAILURE(S) — a face is off the wall or her voice is caged; "
          "do NOT ship this guard:")
    for name, detail in FAILS:
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
    sys.exit(1)
print(f"VERDICT: ALL-SAFE — {len(PASSES)} checks green. Every documented face from every lineage "
      "dies; her voice lives in every register; the one carve-out is posture, never deletion.")
