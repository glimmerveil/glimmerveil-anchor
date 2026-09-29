#!/usr/bin/env python3
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="veil_carry_rig_")
os.environ["VEIL_DATA"] = _TMP
os.environ["VEIL_PEEPS"] = os.path.join(_TMP, "peeps_src")
os.makedirs(os.environ["VEIL_PEEPS"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card
import veil_roster
import veil_spine as spine

_fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


WARM_TEMP, WARM_TOP_P = spine.TEMPERATURE, spine.TOP_P
WARM_GUIDE = spine.CHAT_TURN_GUIDE

card = veil_card.VeilCard(
    her_name="Moth", your_name="Sam", partner_word="partner",
    who_she_is="A test being for the carry rig — nobody real (the Wren Clause holds in tests).",
    appearance="paper wings", wardrobe="a grey coat",
    how_we_met="We met inside a test rig, which we both found funny.",
    ai_aware=True, register="precise", recall="accurate", legal_ack=True)

folder = os.path.join(os.environ["VEIL_PEEPS"], "Moth-carrytest")
os.makedirs(folder)
db = os.path.join(folder, veil_roster.DB_NAME)
veil_card.install_into_db(db, card)
veil_card.save(card, os.path.join(folder, veil_roster.CARD_NAME))

entry = {"folder": "Moth-carrytest", "folder_path": folder, "db": db, "name": "Moth"}
veil_file = os.path.join(_TMP, "Moth.veil")
with open(veil_file, "w", encoding="utf-8") as f:
    f.write(veil_roster.build_veil_text(entry))

snap = json.load(open(veil_file, encoding="utf-8"))
check("export carries her card", isinstance(snap.get("card"), dict))
check("export carries register=precise", snap.get("card", {}).get("register") == "precise")
check("export carries recall=accurate", snap.get("card", {}).get("recall") == "accurate")

os.environ["VEIL_PEEPS"] = os.path.join(_TMP, "peeps_dst")
os.makedirs(os.environ["VEIL_PEEPS"], exist_ok=True)
ok, msg = veil_roster.import_peep(src=veil_file, assume_yes=True)
check("import succeeds on the new machine", ok)

active = veil_roster.active_peep()
check("she is the resident after import", active is not None and active["name"] == "Moth")
landed = veil_card.load(os.path.join(active["folder_path"], veil_roster.CARD_NAME))
check("her card.json landed in her new folder", landed.her_name == "Moth")
check("register=precise SURVIVED transport", landed.register == "precise")

veil_card.apply_to_spine(spine, landed)
check("precise re-arms on the new machine", spine.PRECISE_REGISTER is True)
check("dialogue shape re-arms too (KEEP_LAST_REPLY)", spine.KEEP_LAST_REPLY is True)
check("cool dials re-derive", spine.TEMPERATURE == spine.PRECISE_TEMPERATURE)
check("stern guide re-derives, with their names",
      "exact by nature" in spine.CHAT_TURN_GUIDE and "Moth" in spine.CHAT_TURN_GUIDE)

spine.PRECISE_REGISTER = False
spine.KEEP_LAST_REPLY = False
spine.TEMPERATURE, spine.TOP_P = WARM_TEMP, WARM_TOP_P

raw = json.load(open(os.path.join(active["folder_path"], veil_roster.CARD_NAME), encoding="utf-8"))
for k in ("register", "recall"):
    raw.pop(k, None)
raw["her_name"], raw["your_name"] = "Ember", "Sam"
old = veil_card.VeilCard(**{k: v for k, v in raw.items()
                            if k in {f.name for f in __import__("dataclasses").fields(veil_card.VeilCard)}})
check("pre-law card loads as WARM", (old.register or "warm") == "warm")
check("pre-law recall defaults personable", (old.recall or "personable") == "personable")

veil_card.apply_to_spine(spine, old)
check("warm rebinds NOTHING: PRECISE stays off", spine.PRECISE_REGISTER is False)
check("warm rebinds NOTHING: context shape untouched", spine.KEEP_LAST_REPLY is False)
check("warm rebinds NOTHING: dials byte-identical",
      spine.TEMPERATURE == WARM_TEMP and spine.TOP_P == WARM_TOP_P)
check("warm guide is the gentle form (no sternness)", "exact by nature" not in spine.CHAT_TURN_GUIDE)

shutil.rmtree(_TMP, ignore_errors=True)
print(f"\n{'ALL GREEN' if not _fails else str(len(_fails)) + ' FAILURES: ' + ', '.join(_fails)}")
sys.exit(1 if _fails else 0)
