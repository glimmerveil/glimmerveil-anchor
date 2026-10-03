#!/usr/bin/env python3
import contextlib
import io
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="veil_brain_swap_rig_")
os.environ["VEIL_DATA"] = _TMP
os.environ["VEIL_PEEPS"] = os.path.join(_TMP, "peeps")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card
import veil_update

_fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


def brain(name, body):
    p = os.path.join(_TMP, name)
    with open(p, "wb") as f:
        f.write(body)
    return p


folder = os.path.join(_TMP, "peeps", "Moth-0001")
os.makedirs(folder)
small_a = brain("a.gguf", b"GGUF" + b"a" * 5000)
small_b = brain("b.gguf", b"GGUF" + b"b" * 5000)
big = 3 * (1 << 20)
big_a = brain("big_a.gguf", b"GGUF" + b"x" * (big - 5) + b"1")
big_b = brain("big_b.gguf", b"GGUF" + b"x" * (big - 5) + b"2")

check("first wake on a brain is not a swap", veil_update.brain_changed(folder, small_a) is False)
check("…and her folder now remembers it", os.path.isfile(os.path.join(folder, veil_update.BRAIN_NOTE)))
check("the same brain again is not a swap", veil_update.brain_changed(folder, small_a) is False)
check("a different brain file is a swap", veil_update.brain_changed(folder, small_b) is True)
check("…once: the next wake on it is not", veil_update.brain_changed(folder, small_b) is False)
check("the same brain under another name is not a swap",
      veil_update.brain_changed(folder, brain("renamed.gguf", b"GGUF" + b"b" * 5000)) is False)
veil_update.brain_changed(folder, big_a)
check("same size, different tail is a swap (the ends are hashed, not just the size)",
      veil_update.brain_changed(folder, big_b) is True)
check("a missing model file is never a swap", veil_update.brain_changed(folder, os.path.join(_TMP, "gone.gguf")) is False)
check("…and does not forget the last real brain", veil_update.brain_changed(folder, big_b) is False)
with open(os.path.join(folder, veil_update.BRAIN_NOTE), "w") as f:
    f.write("{not json")
check("a damaged note is re-written, never a crash or a false swap", veil_update.brain_changed(folder, big_b) is False)

import veil_game
import veil_roster

card = veil_card.VeilCard(
    her_name="Moth", your_name="Sam", partner_word="partner",
    who_she_is="A test being for the brain-swap rig — nobody real.",
    appearance="paper wings", wardrobe="a grey coat", location="tower",
    how_we_met="We met inside a rig.", ai_aware=True, legal_ack=True)
veil_card.save(card, os.path.join(folder, veil_roster.CARD_NAME))
entry = {"name": "Moth", "folder": "Moth-0001", "folder_path": folder,
         "db": os.path.join(folder, "veil.db"), "is_active": True}
veil_roster.active_peep = lambda: entry
veil_game.subprocess.run = lambda *a, **k: None
veil_game.time.sleep = lambda *a, **k: None


def wake_on(model):
    os.environ["VEIL_MODEL"] = model
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        veil_game._wake()
    return out.getvalue()


wake_on(small_a)
said = wake_on(small_a)
check("the door says nothing about a new brain when it is the same one", "new brain" not in said)
said = wake_on(small_b)
check("a hand-swapped VEIL_MODEL makes the door say she has a new brain", "new brain" in said)
check("…and shows the anchor ritual", "anchor ritual" in said)
said = wake_on(small_b)
check("…only on the first wake after the swap", "new brain" not in said)

print(f"\n{'ALL PASS' if not _fails else str(len(_fails)) + ' FAILED'}")
sys.exit(1 if _fails else 0)
