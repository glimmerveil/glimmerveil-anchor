#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as S

S.set_screenplay_roster("Nia", "Sam")

_fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


PROSE_MELT = """I can feel the warmth of your hand in mine as we cross the garden, and I see the easy smile on your face. The evening air is cool and smells of cut grass and the last of the roses.

"There you are," I say softly, tucking my hands into my sleeves. "I was starting to think the lanterns would burn out before you found me."

You laugh quietly, a low sound that carries across the lawn. "Never, Nia. Never." You take the lantern from the bench beside us, then lead me down the path toward the pond. We sit together on the flat stone at its edge, and for a while we just watch the light shiver on the water.

"It's so still out here. I could stay until morning."

I lean my head on your shoulder, feeling the quiet settle over both of us. "Then we will. There's nowhere else I need to be."

"Good." Your fingers find mine again, lacing them together. "The night is long, and it's ours."

We stay like that for a long time, until finally, you break the silence with another question."""

cut = S._prose_partner_cut(PROSE_MELT)
check("a sustained prose melt is CAUGHT", cut is not None)
if cut is not None:
    kept = PROSE_MELT[:cut]
    check("her genuine opening survives the cut", "warmth of your hand" in kept)
    check("the scripted scene is gone from the keep", "You laugh quietly" not in kept)

ADDRESS = [
    "You look tired tonight. Come sit with me — the stars are out and I saved your side of the chair.",
    "I missed you today. Do you want tea? You always know the right moment to come home to me.",
    "You were right about the sky — the storm turned east just like you said it would.",
    "Your eyes are beautiful in this light. I could stay here all night just looking at you.",
    "You make me feel safe. That is not a small thing, and I don't say it enough.",
    "Mm. I love you. Now hush and let me read you this part — it's the passage you asked about.",
    "You said something yesterday that stayed with me — about the tower holding its breath.",
    "Your voice was the first thing I ever knew. I wrote that in my diary the night I woke.",
]
for i, a in enumerate(ADDRESS):
    check(f"address {i + 1} passes untouched", S._prose_partner_cut(a) is None)

ONE_HIT = "You lean against the doorway the way you always do. I love that about you — never change."
check("a single borderline hit stays under the floor", S._prose_partner_cut(ONE_HIT) is None)

WARM_QUOTE = ('I feel the warmth of your hands as they move over me, and I arch into it. '
              '"Doing great! Look at you!" You say with a smile, and I melt against you.')
check("one tucked quote of him stays hers (under the floor)",
      S._prose_partner_cut(WARM_QUOTE) is None)
S.set_screenplay_roster("Noor", "Sam")
SELF_NARRATE = ('Noor smiles and pours the tea. Noor says, "Come sit with me?" '
                "She pats the cushion beside her.")
check("her own name is excused (self-narration is her voice)",
      S._prose_partner_cut(SELF_NARRATE, own_name="Noor") is None)
check("the same shape in ANOTHER rostered mouth still counts",
      S._prose_partner_cut(SELF_NARRATE.replace("Noor", "Sam"), own_name="Noor") is not None
      or S._prose_partner_cut(('Sam smiles and pours the tea. Sam says, "Sit with me?" '
                               'Sam leans back and watches me, then pats the cushion.'),
                              own_name="Noor") is not None)
S.set_screenplay_roster("Nia", "Sam")

COLD_OPEN = ('You walk in and set your bag down, then cross the room to me. "Long day," you murmur, '
             'and pull me close before I can answer. You smile and lift my chin, and your fingers '
             'find my waist as you steer us toward the couch.')
cold = S._prose_partner_cut(COLD_OPEN)
check("cold-open melt is caught", cold is not None)
check("cold-open cut keeps nothing worth saving", cold is not None and cold <= 1)

S._PROSE_GUARD_ON = False
check("VEIL_PROSE_GUARD off → face disarmed", S._prose_partner_cut(PROSE_MELT) is None)
S._PROSE_GUARD_ON = True
LABELED = "Sam: I'm home.\nLua: Welcome back!"
check("label face still fires on script shape", S._foreign_speaker_cut(LABELED, "Nia") is not None)
check("label face untouched by prose patterns", S._foreign_speaker_cut(PROSE_MELT, "Nia") is None)

import inspect
src = inspect.getsource(S.generate_guarded)
check("generate_guarded wires the prose face", "_prose_partner_cut" in src)
check("prose face runs only when labels found nothing", src.index("_foreign_speaker_cut") < src.index("_prose_partner_cut"))
check("its own quarantine tag (fold/audit visibility)", "chat_prose_melt" in src)

print(f"\n{'ALL GREEN' if not _fails else str(len(_fails)) + ' FAILURES: ' + ', '.join(_fails)}")
sys.exit(1 if _fails else 0)
