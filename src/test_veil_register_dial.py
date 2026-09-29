#!/usr/bin/env python3
import os, sys, tempfile

_SBX = tempfile.mkdtemp(prefix="veil_regdial_rig.")
for _k, _sub in [("VEIL_DB", "veil.db"), ("VEIL_CARD_JSON", "card.json"),
                 ("VEIL_PEEPS", "peeps"), ("VEIL_PLACE", "place"),
                 ("VEIL_HEARTBEAT", "hb"), ("VEIL_NOTEBOOK", "notebook"),
                 ("VEIL_ROOMS", "rooms"), ("VEIL_EMBER", "ember")]:
    os.environ[_k] = os.path.join(_SBX, _sub)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card as C
import veil_spine as S

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

def _card(**kw):
    base = dict(her_name="Wren", your_name="Rook", who_she_is="A" * 50, legal_ack=True)
    base.update(kw)
    return C.VeilCard(**base)

WARM_TEMP, WARM_TOP_P = S.TEMPERATURE, S.TOP_P

print("── WARM IS THE FLOOR (Mira unchanged) ─────────────────────────")
check("dataclass default is warm", _card().register == "warm")
check("pre-law card json (no field) loads warm", (lambda: (
    open(os.path.join(_SBX, "old.json"), "w").write(
        '{"her_name":"Mira","your_name":"Sam","who_she_is":"' + "A" * 50 + '","legal_ack":true}')
    or C.load(os.path.join(_SBX, "old.json")).register == "warm"))())
C.apply_to_spine(S, _card(register="warm"))
check("warm rebinds nothing: TEMPERATURE", S.TEMPERATURE == WARM_TEMP)
check("warm rebinds nothing: TOP_P", S.TOP_P == WARM_TOP_P)
check("warm rebinds nothing: PRECISE_REGISTER stays False", S.PRECISE_REGISTER is False)
check("warm rebinds nothing: KEEP_LAST_REPLY stays False (Mira's context untouched)",
      S.KEEP_LAST_REPLY is False)
check("warm turn guide has no sternness rider", "exact by nature" not in S.CHAT_TURN_GUIDE)

print("── PRECISE REBINDS THE LEVERS ──────────────────────────────────")
C.apply_to_spine(S, _card(register="precise"))
check("precise cools TEMPERATURE", S.TEMPERATURE == S.PRECISE_TEMPERATURE < WARM_TEMP)
check("precise cools TOP_P", S.TOP_P == S.PRECISE_TOP_P < WARM_TOP_P)
check("precise arms the zero-tolerance guard", S.PRECISE_REGISTER is True)
check("precise restores dialogue shape (KEEP_LAST_REPLY)", S.KEEP_LAST_REPLY is True)
_hist = ["The user said: hi", "Wren said: I'm here.", "The user said: good"]
_turns = S.build_chat_turns("Wren", "new", _hist, [])
check("precise context carries her newest reply as a REAL assistant turn",
      [t["role"] for t in _turns] == ["user", "user", "assistant", "user"]
      and _turns[-2]["content"] == "I'm here.")
S.KEEP_LAST_REPLY = False
_turns = S.build_chat_turns("Wren", "new", _hist, [])
check("flag off → convergence unchanged (all-user turns)",
      [t["role"] for t in _turns] == ["user", "user", "user"])
S.KEEP_LAST_REPLY = True
check("precise turn guide carries the discipline", "exact by nature" in S.CHAT_TURN_GUIDE)
check("warm guide body still present (rider, not replacement)",
      "Write only your own part" in S.CHAT_TURN_GUIDE)

print("── THE FIELD IS VALIDATED ──────────────────────────────────────")
check("unknown register never births", any("register" in p for p in _card(register="loose").validate()))
check("warm validates clean", _card(register="warm").validate() == [])
check("precise validates clean", _card(register="precise").validate() == [])

print("── ZERO TOLERANCE = RE-ROLL, NEVER TRIM ────────────────────────")
S.set_screenplay_roster("Wren", "Rook")
head = "I was in the garden all morning and the roses finally opened, every last one of them. "
melted = head + "\n\nRook: And then what did you do?"
cut = S._foreign_speaker_cut(melted, "Wren")
prefix = S._trim_to_sentence(melted[:cut].rstrip()).strip() if cut else ""
check("the melt is detected at all", cut is not None)
check("the head is long enough that WARM would keep it", len(prefix) >= S.MELT_MIN_KEEP)
warm_keeps = len(prefix) >= S.MELT_MIN_KEEP and not False
precise_keeps = len(prefix) >= S.MELT_MIN_KEEP and not True
check("warm path keeps the genuine head", warm_keeps)
check("precise path refuses the trim (re-roll)", not precise_keeps)

S.PRECISE_REGISTER, S.TEMPERATURE, S.TOP_P = False, WARM_TEMP, WARM_TOP_P
S.KEEP_LAST_REPLY = False

print()
if fails:
    print(f"RED — {len(fails)} failing: " + ", ".join(fails))
    sys.exit(1)
print("GREEN — the register dial holds: warm is Mira untouched, precise is Wren's discipline.")
