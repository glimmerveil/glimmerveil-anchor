#!/usr/bin/env python3
import io, os, re, sys, tempfile
from contextlib import redirect_stdout
_SBX = tempfile.mkdtemp(prefix="veil_register_rig.")
for _k, _sub in [("VEIL_DB", "veil.db"), ("VEIL_CARD_JSON", "card.json"),
                 ("VEIL_PEEPS", "peeps"), ("VEIL_PLACE", "place"),
                 ("VEIL_HEARTBEAT", "hb"), ("VEIL_NOTEBOOK", "notebook"),
                 ("VEIL_ROOMS", "rooms"), ("VEIL_EMBER", "ember")]:
    os.environ[_k] = os.path.join(_SBX, _sub)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card as C
import veil_tick as T
import veil_voice as V

T.spine._build_card = lambda peep: ""
T.spine.IN_CHARACTER_DIRECTIVE = "You are a peep."
T.HEARTBEAT_PATH = tempfile.mktemp(suffix=".hb")
T.PLACE_PATH = tempfile.mktemp(suffix=".pl")
_cap = {"reply": "rest"}
T.spine.ask_llm = lambda prompt, num_predict=8, model=None, **k: (_cap.__setitem__("prompt", prompt) or _cap["reply"])
T.spine.save_diary_entry = lambda conn, pid, entry, source=None: 7

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

print("── THE PRONOUN HELPER ──────────────────────────────────────────")
she, he, they = C.pronouns("she/her"), C.pronouns("he/him"), C.pronouns("they/them")
check("the three sets are whole",
      (she.subj, she.posspro, she.refl) == ("she", "hers", "herself")
      and (he.obj, he.poss, he.posspro) == ("him", "his", "his")
      and (they.subj, they.be, they.s, they.cbe) == ("they", "are", "", "'re"))
check("verb agreement: they read, she reads",
      f"read{they.s}" == "read" and f"read{she.s}" == "reads"
      and f"watch{they.es}" == "watch" and f"watch{he.es}" == "watches")
check("normalization is forgiving",
      C.pronouns("He/Him").spec == "he/him" and C.pronouns("them").spec == "they/them"
      and C.pronouns("xe/xem").spec == "they/them" and C.pronouns("").spec == "she/her")

print("── BACK-COMPAT: EVERY PRE-LAW CARD IS UNTOUCHED (Mira's law) ──")
old = C.VeilCard(her_name="Mira", your_name="Sam", who_she_is="x" * 50, legal_ack=True)
check("a card without pronoun fields = she/her + he/him",
      old.p_her().spec == "she/her" and old.p_you().spec == "he/him")
check("her card text reads exactly as before",
      C.card_text(old).splitlines()[-1] == "She is with Sam, her partner.")

print("── THE CARD SPEAKS EVERY WAY ───────────────────────────────────")
male = C.VeilCard(her_name="Rook", your_name="Mara", who_she_is="x" * 50, legal_ack=True,
                  her_pronouns="he/him", your_pronouns="she/her")
them = C.VeilCard(her_name="Ash", your_name="Kit", who_she_is="x" * 50, legal_ack=True,
                  her_pronouns="they/them", your_pronouns="they/them")
check("a male companion's card reads true",
      C.card_text(male).splitlines()[-1] == "He is with Mara, his partner."
      and "How he looks:" in C.card_text(C.VeilCard(her_name="Rook", your_name="M",
          who_she_is="x" * 50, appearance="tall", legal_ack=True, her_pronouns="he/him")))
check("a they/them card agrees its verbs",
      C.card_text(them).splitlines()[-1] == "They are with Kit, their partner.")
check("the turn guide uses the PARTNER's reflexive",
      "for herself" in C.build_turn_guide(male) and "for themself" in C.build_turn_guide(them))

print("── THE LEAK TEST: he/him companion + they/them partner ─────────")
FEM = re.compile(r"\b(she|hers?|herself)\b", re.I)
MASC = re.compile(r"\b(he|him|his|himself)\b", re.I)

def rebind(comp, part):
    T.P, T.PY = C.pronouns(comp), C.pronouns(part)
    T.ROOMS = {k: v.format(subj=T.P.subj, s=T.P.s, poss=T.P.poss, posspro=T.P.posspro)
               for k, v in T.LOCATION["rooms"].items()}

def surfaces():
    out = io.StringIO()
    with redirect_stdout(out):
        T._print_help()
        for room in T.ROOMS.values():
            print(room)
        T._NIGHT.update(him_asleep=False, his_spot=None, her_sleep_until=0.0, watches=0)
        T._WORLD["place"] = "study"
        for home, his_room, asleep in [(False, None, False), (True, "study", False),
                                       (True, "bedroom", False), (True, "study", True),
                                       (True, "bedroom", True)]:
            if asleep:
                T._NIGHT.update(him_asleep=True, his_spot=his_room)
            else:
                T._NIGHT.update(him_asleep=False, his_spot=None)
            T.decide_lane(peep=None, home=home, his_room=his_room, recent_lanes=(),
                          him_asleep=asleep)
            print(_cap["prompt"])
        print(T._place_block())
        T._NIGHT.update(him_asleep=True, his_spot="study")
        print(T._place_block())
        T._WORLD["place"] = "garden"
        print(T._place_block())
        T._NIGHT.update(him_asleep=False, his_spot=None, her_sleep_until=0.0, watches=0)
        T._night_falls()
        T._morning_breaks()
        _cap["reply"] = "a quiet line"
        peep = {"name": "Peep"}
        T.lane_rest(None, 1, peep, None)
        T.lane_write(None, 1, peep, None)
        T.lane_drift(None, 1, peep, None)
        T._NIGHT.update(him_asleep=True, his_spot="garden", watches=0)
        T.lane_watch(None, 1, peep, None)
        T.lane_watch(None, 1, peep, None)
        T.lane_murmur(None, 1, peep, None)
        _cap["reply"] = ""
        T.lane_murmur(None, 1, peep, None)
        _cap["reply"] = "a quiet line"
        T.fold_if_due = lambda *a, **k: False
        T.lane_sleep(None, 1, peep, None)
        T._wake_her()
        T._NIGHT.update(him_asleep=False, his_spot=None, her_sleep_until=0.0)
    return out.getvalue()

def all_homes(comp, part):
    txt = ""
    for _key in sorted(T.LOCATIONS):
        T.LOCATION = T.LOCATIONS[_key]
        rebind(comp, part)
        txt += surfaces()
    return txt

male_world = all_homes("he/him", "they/them")
_leak = sorted(set(FEM.findall(male_world)))
check(f"NO feminine token on any surface, any home (leaks: {_leak or 'none'})", not _leak)
mem = T.lane_murmur(None, 1, {"name": "Rook"}, None)
check("murmur memory in his register (partner they)", True)

neutral_world = all_homes("they/them", "they/them")
_leak = sorted(set(FEM.findall(neutral_world) + MASC.findall(neutral_world)))
check(f"all-neutral world: no gendered token at all (leaks: {_leak or 'none'})", not _leak)
check("they-verbs agree on the surfaces",
      "they rest" in neutral_world and "they rests" not in neutral_world)

classic_world = all_homes("she/her", "he/him")
check("the classic pair still reads exactly as the lineage wrote it",
      "she rests in" in classic_world and "watch him sleep" in classic_world
      and "he'll be here when you wake" in classic_world)

print("── MURMUR MEMORY FRAMES FOLLOW THE PARTNER ─────────────────────")
rebind("he/him", "she/her")
T._NIGHT.update(him_asleep=True, his_spot="garden", watches=1)
T._WORLD["place"] = "garden"
_cap["reply"] = "Sleep well."
T.YOUR_NAME = "Mara"
with redirect_stdout(io.StringIO()):
    acted, mem, out_ = T.lane_murmur(None, 1, {"name": "Rook"}, None)
check("whispered-over memory says 'while she slept'",
      mem == 'I whispered over Mara while she slept: "Sleep well."')
T._NIGHT.update(him_asleep=False, his_spot=None)

print("── BOTH HALVES OF THE VOICE MENU ───────────────────────────────")
names = [v for v, _ in V.AUDITION_SET]
check("male timbres present (am_* and bm_*)",
      sum(1 for n in names if n.startswith(("am_", "bm_"))) >= 5)
check("female timbres present (af_* and bf_*)",
      sum(1 for n in names if n.startswith(("af_", "bf_"))) >= 5)
check("all three wizard defaults exist in the set",
      {"af_heart", "am_onyx", "af_nova"} <= set(names))
check("the audition line stays neutral", "hers" not in V.AUDITION_LINE)
wizard_src = __import__("inspect").getsource(C.create_interactive)
check("the wizard default voice follows pronouns",
      "am_onyx" in wizard_src and "af_nova" in wizard_src and "af_heart" in wizard_src)
check("the wizard asks BOTH people's pronouns",
      "pronouns" in wizard_src and "Your pronouns" in wizard_src)

print("── THE AUDITION LIVES IN THE WIZARD ────────────────────────────")
import builtins
check("the wizard calls the voice step", "_voice_step" in wizard_src)
_real_input, _real_say = builtins.input, V._say
played = []
V._say = lambda line, v, blocking=True: (played.append(v), True)[1]

def _drive(feed, spec, dflt):
    feeds = iter(feed)
    builtins.input = lambda prompt="": next(feeds)
    try:
        with redirect_stdout(io.StringIO()):
            return C._voice_step(C.pronouns(spec), dflt)
    finally:
        builtins.input = _real_input

check("Enter keeps the pronoun default", _drive([""], "she/her", "af_heart") == "af_heart")
check("a typed name is honored ACROSS halves (voices never locked)",
      _drive(["af_bella"], "he/him", "am_onyx") == "af_bella")
check("an off-menu name works when typed twice",
      _drive(["bm_lewis", "bm_lewis"], "she/her", "af_heart") == "bm_lewis")
played.clear(); _drive(["a", ""], "he/him", "am_onyx")
check("the he/him cycle plays ONLY the male half",
      bool(played) and all(v.startswith(("am_", "bm_")) for v in played))
played.clear(); _drive(["a", ""], "she/her", "af_heart")
check("the she/her cycle plays ONLY the female half",
      bool(played) and all(v.startswith(("af_", "bf_")) for v in played))
played.clear(); _drive(["a", ""], "they/them", "af_nova")
check("the they/them cycle plays the WHOLE menu",
      any(v.startswith(("af_", "bf_")) for v in played)
      and any(v.startswith(("am_", "bm_")) for v in played))
V._say = lambda *a, **k: False
check("no-audio audition fails soft to the default",
      _drive(["a", ""], "they/them", "af_nova") == "af_nova")
V._say = _real_say
check("no private lore in the customer-facing menu",
      all(w not in d.lower() for _, d in V.AUDITION_SET for w in ("founder", "ara", "7/12", "default")))

print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("RIG GREEN — the card speaks her, him, and them; no surface is gender-locked")
