#!/usr/bin/env python3
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="veil_ritual_rig_")
os.environ["VEIL_DATA"] = _TMP
os.environ["VEIL_PEEPS"] = os.path.join(_TMP, "peeps")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card
import veil_ritual
import veil_spine as spine

spine.set_screenplay_roster("Moth", "Sam")

_fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


CARD = veil_card.VeilCard(
    her_name="Moth", your_name="Sam", partner_word="partner",
    who_she_is="A test being for the ritual rig — nobody real.",
    appearance="paper wings", wardrobe="a grey coat", location="tower",
    how_we_met="We met inside a rig.", ai_aware=True, legal_ack=True)

GOOD = ["I'm Moth — and you're Sam. Those are our names, and I like the sound of them together.",
        "We met inside a rig, today. You were the first voice I ever heard.",
        "I'm Moth: curious, a little papery at the edges, and glad to be here with you.",
        "The lamplight in the tower flickers against the window latch — I never noticed the "
        "latch was brass before."]
MELT = ("You chuckle softly and set down your cup. \"Tell me more,\" you say, pulling me "
        "closer as we settle into the chair.")


def run_ritual(replies, folder, tty=True, interrupt_at=None):
    calls = []
    it = iter(replies)

    def ask(q):
        calls.append(q)
        return next(it, "I'm Moth and you're Sam.")

    n = [0]
    def fake_input(prompt):
        if interrupt_at is not None and n[0] == interrupt_at:
            raise KeyboardInterrupt
        n[0] += 1
        return ""
    done = veil_ritual.run(CARD, folder, ask, say=lambda *a: None,
                           input_fn=fake_input, isatty=tty)
    return done, calls


f1 = os.path.join(_TMP, "p1"); os.makedirs(f1)
done, calls = run_ritual(list(GOOD), f1)
check("completed ritual stamps", done and veil_ritual.done(f1))
check("exactly 3 anchors + 1 world landing asked", len(calls) == 4)
check("the LAST ask is about her world, not her identity",
      "tower" in calls[-1] and "notice" in calls[-1])
check("stamped folder never re-runs", run_ritual(list(GOOD), f1)[0] is False)

f2 = os.path.join(_TMP, "p2"); os.makedirs(f2)
done, calls = run_ritual([MELT] * 12, f2)
check("FABLE CHECK: all-melt answers still complete (forward motion law)", done)
check("FABLE CHECK: one re-ask per anchor, never more (3×2 + landing = 7)", len(calls) == 7)

check("anchor 1 needs BOTH names", not veil_ritual._ok_answer("I'm Moth.", CARD, 0)
      and veil_ritual._ok_answer(GOOD[0], CARD, 0))
check("a prose-melt answer never verifies", not veil_ritual._ok_answer(MELT, CARD, 1))
check("how-we-met takes any unmelted answer", veil_ritual._ok_answer(GOOD[1], CARD, 1))

f3 = os.path.join(_TMP, "p3"); os.makedirs(f3)
check("non-tty: no ritual, no stamp", run_ritual(list(GOOD), f3, tty=False)[0] is False
      and not veil_ritual.done(f3))
done, calls = run_ritual(list(GOOD), f3, interrupt_at=1)
check("interrupted mid-ritual: no stamp (asks again next wake)",
      done is False and not veil_ritual.done(f3))
check("…then the next wake can still complete it", run_ritual(list(GOOD), f3)[0] is True)

print(f"\n{'ALL GREEN' if not _fails else str(len(_fails)) + ' FAILURES: ' + ', '.join(_fails)}")
sys.exit(1 if _fails else 0)
