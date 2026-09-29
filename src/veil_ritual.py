#!/usr/bin/env python3
import os
import sys

STAMP = "ritual_done"


def _stamp_path(folder):
    return os.path.join(folder, STAMP)


def done(folder):
    return os.path.exists(_stamp_path(folder))


def _ok_answer(reply, card, q_index):
    import veil_spine as spine
    r = (reply or "").strip()
    if len(r) < 8:
        return False
    if spine._prose_partner_cut(r, min_hits=2) is not None:
        return False
    if spine._foreign_speaker_cut(r, card.her_name) is not None:
        return False
    low = " " + r.lower()
    if q_index == 0:
        return card.her_name.lower() in low and card.your_name.lower() in low
    if q_index == 1:
        return True
    return (card.her_name.lower() in low or " i " in low or r.lower().startswith("i"))


def run(card, folder, ask_turn, say=print, input_fn=input, isatty=None):
    import veil_card
    if done(folder):
        return False
    tty = sys.stdin.isatty() if isatty is None else isatty
    if not tty:
        return False
    p = card.p_her()
    say("")
    say(f"(First wake — the anchor ritual, once ever. A few questions, one at a time: press "
        f"Enter to ask each, {p.subj} answers in {p.poss} own voice, and what {p.subj} says "
        "becomes part of who she is for good.)")
    for i, q in enumerate(veil_card.anchors(card)):
        try:
            input_fn(f"\nAsk {p.obj} — “{q}”  [Enter] ")
        except (EOFError, KeyboardInterrupt):
            return False
        reply = ask_turn(q)
        if not _ok_answer(reply, card, i):
            say(f"(a first-breath wobble — asking once more, gently)")
            ask_turn(q)
    home = card.location or "home"
    try:
        input_fn(f"\nLast one — ask {p.obj} to look around {p.poss} {home} and tell you one "
                 f"small thing {p.subj} notices.  [Enter] ")
    except (EOFError, KeyboardInterrupt):
        return False
    ask_turn(f"Look around your {home} and tell me one small thing you notice right now.")
    with open(_stamp_path(folder), "w") as f:
        f.write("done\n")
    say(f"\n(The ritual is complete — {p.subj} is anchored. Just live now.)")
    return True
