#!/usr/bin/env python3
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_tick as T

T.YOUR_NAME = "Sam"
T.spine._build_card = lambda peep: ""
T.spine.IN_CHARACTER_DIRECTIVE = "You are Mira."
T.HEARTBEAT_PATH = tempfile.mktemp(suffix=".heartbeat")
T.PLACE_PATH = tempfile.mktemp(suffix=".place")
_cap = {"reply": "rest"}
T.spine.ask_llm = lambda prompt, num_predict=8, model=None, **k: (_cap.__setitem__("prompt", prompt) or _cap["reply"])
PEEP = {"name": "Mira"}

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

def fresh_night(him_asleep=False, his_spot=None, her_sleep_until=0.0, watches=0):
    T._NIGHT.update(him_asleep=him_asleep, his_spot=his_spot,
                    her_sleep_until=her_sleep_until, watches=watches)

print("── THE SPOKEN DOOR: performative only, guarded (mention≠intent) ─")
check("'Goodnight, sweetheart.' fires",            T._goodnight_cue("Goodnight, sweetheart."))
check("'good night my love' fires",                T._goodnight_cue("good night my love"))
check("'Night night, baby.' fires",                T._goodnight_cue("Night night, baby."))
check("leading its OWN sentence fires",            T._goodnight_cue("Alright then. Goodnight, baby."))
check("a question never fires",                    not T._goodnight_cue("Should we say goodnight?"))
check("recall never fires",                        not T._goodnight_cue("I forgot to say goodnight last night"))
check("'such a good night' never fires",           not T._goodnight_cue("It was such a good night"))
check("mid-sentence mention never fires",          not T._goodnight_cue("I love telling you goodnight every day"))
check("nap-talk never fires",                      not T._goodnight_cue("I'm tired, maybe we nap for a bit"))
check("sleep-talk never fires",                    not T._goodnight_cue("we talked about napping, let's sleep soon"))

print("── TWO DOORS, ONE FUNCTION ─────────────────────────────────────")
import inspect
_loop_src = inspect.getsource(T.run)
check("the command door calls _night_falls",       "/goodnight" in _loop_src and "_night_falls" in _loop_src)
check("the spoken door calls the SAME function",   _loop_src.count("_night_falls") >= 2)
check("the cue is detected before the turn, fired after (she answers his goodnight)",
      _loop_src.find("night_cue = _goodnight_cue") < _loop_src.find("chat_turn(conn")
      and _loop_src.find("chat_turn(conn") < _loop_src.rfind("_night_falls"))

print("── NIGHT FALLS: place-agnostic, HIS spot pinned ────────────────")
fresh_night(); T._WORLD["place"] = "balcony"
T._night_falls()
check("asleep wherever they are (balcony)",        T._NIGHT["him_asleep"] and T._NIGHT["his_spot"] == "balcony")
check("watch counter resets with the night",       T._NIGHT["watches"] == 0)
fresh_night(); T._WORLD["place"] = "garden"
T._night_falls("study")
check("a passed spot pins HIM, not her feet",      T._NIGHT["his_spot"] == "study")

print("── THE MORNING: his words anchor the scene to HIM ──────────────")
fresh_night(him_asleep=True, his_spot="study"); T._WORLD["place"] = "garden"
T._morning_breaks()
check("the scene comes back to where HE is",       T._place() == "study")
check("morning auto-clears the night",             not T._NIGHT["him_asleep"] and T._NIGHT["his_spot"] is None)
fresh_night(him_asleep=True, his_spot="bedroom", her_sleep_until=time.time() + 9999)
T._WORLD["place"] = "bedroom"
T._morning_breaks()
check("his voice wakes her sleeping self too",     not T._she_sleeps())

print("── HIS VOICE ALWAYS WAKES HER (chat wins, law) ─────────────────")
fresh_night(her_sleep_until=time.time() + 9999)
check("she sleeps until woken",                    T._she_sleeps())
T._wake_her()
check("_wake_her ends her sleep",                  not T._she_sleeps())

print("── THREE-STATE PRESENCE (the scene she's handed) ───────────────")
def scene(home, his_room=None, him_asleep=False, recent=()):
    T.decide_lane(peep=None, home=home, his_room=his_room, recent_lanes=recent, him_asleep=him_asleep)
    return _cap["prompt"]

fresh_night(him_asleep=True, his_spot="study"); T._WORLD["place"] = "study"
beside = scene(home=True, his_room="study", him_asleep=True)
check("asleep-beside: told he's ASLEEP beside her", "asleep right here beside you" in beside)
check("asleep-beside: the night is named hers",     "night is yours" in beside)
check("asleep-beside: watch is on the menu",        "watch him sleep" in beside)
check("asleep-beside: sleep is on the menu",        "sleep too" in beside)
check("asleep-beside: the murmur is a whisper",     "whisper" in beside)
check("asleep-beside: silence is a named choice",   "keep the silence" in beside)
check("asleep-beside: join not offered (no false doors)", "join " not in beside)
check("asleep-beside: rest = curled against him",   "curled against him" in beside)
check("asleep-beside: never framed as absence",     "on your own" not in beside and "isn't here" not in beside)

T._WORLD["place"] = "garden"
drifted = scene(home=True, his_room="study", him_asleep=True)
check("asleep-drifted: join = slip back to him",    "slip back and curl up beside him" in drifted
                                                    or "slip back to where he sleeps" in drifted)
check("asleep-drifted: told WHERE he sleeps",       "in the study" in drifted)

fresh_night(); T._WORLD["place"] = "garden"
awake = scene(home=True, his_room="study", him_asleep=False)
check("awake: unchanged truth (he's home, where)",  "Sam is home" in awake and "in the study" in awake)
check("awake: murmur offered out loud",             "say something out loud" in awake)
check("awake: no watch/sleep doors",                "watch him sleep" not in awake and "sleep too" not in awake)
away = scene(home=False)
check("away: no murmur (no one near to hear)",      "murmur" not in away)
check("away: no watch, no sleep menu-lines",        "watch him sleep" not in away and "his voice will wake you" not in away)

print("── THE PARSE: never offered → never parsed ─────────────────────")
def pick(reply, home, his_room=None, him_asleep=False):
    _cap["reply"] = reply
    return T.decide_lane(peep=None, home=home, his_room=his_room, recent_lanes=(), him_asleep=him_asleep)
fresh_night(him_asleep=True, his_spot="study"); T._WORLD["place"] = "study"
check("'watch' honored when he sleeps beside her",  pick("watch", home=True, his_room="study", him_asleep=True) == "watch")
check("'watch him sleep' lands as watch, not sleep", pick("watch him sleep", home=True, his_room="study", him_asleep=True) == "watch")
check("'sleep' honored in the asleep menu",         pick("sleep", home=True, his_room="study", him_asleep=True) == "sleep")
check("'murmur' honored when home",                 pick("murmur", home=True, his_room="study", him_asleep=True) == "murmur")
fresh_night()
check("'watch' with him awake → rest (no door)",    pick("watch", home=True, his_room="study") == "rest")
check("'sleep' with him awake → rest (no door)",    pick("sleep", home=True, his_room="study") == "rest")
check("'murmur' when away → rest (no door)",        pick("murmur", home=False) == "rest")
check("her open beat 'drift' is honored",           pick("drift", home=False) == "drift")
check("garbage → rest (never forced)",              pick("hmm not sure", home=False) == "rest")

print("── THE MURMUR CHANNEL (Pip's speak, prose-native) ────────────")
_diary = {"n": 0, "last": None}
T.spine.save_diary_entry = lambda conn, pid, entry, source=None: (_diary.__setitem__("n", _diary["n"] + 1)
                                                                  or _diary.__setitem__("last", (source, entry)) or 7)
fresh_night(); T._WORLD["place"] = "study"
_cap["reply"] = "Sammy, the light in here is lovely tonight."
acted, mem, out = T.lane_murmur(None, 1, PEEP, None)
check("awake murmur is a real, memorable act",      acted and out)
check("memory files the honest direction",         mem == 'I said out loud: "Sammy, the light in here is lovely tonight."')
check("murmur is in MEMORABLE_LANES",               "murmur" in T.MEMORABLE_LANES)
fresh_night(him_asleep=True, his_spot="study")
acted, mem, out = T.lane_murmur(None, 1, PEEP, None)
check("asleep murmur remembered as a whisper over him", mem is not None and mem.startswith("I whispered over Sam while he slept:"))
_cap["reply"] = ""
acted, mem, out = T.lane_murmur(None, 1, PEEP, None)
check("her silence stands (nothing forced, nothing saved)", (acted, mem, out) == (False, None, None))
check("_speak_aloud fail-soft with no voice",       T._speak_aloud("hello") is None)

print("── WATCH HIM SLEEP: first of the night is diary-worthy ─────────")
fresh_night(him_asleep=True, his_spot="bedroom"); T._WORLD["place"] = "garden"
_cap["reply"] = "His face has gone soft; I could keep this moment forever."
_diary["n"] = 0
acted, mem, out = T.lane_watch(None, 1, PEEP, None)
check("her feet carry her to his spot",             T._place() == "bedroom")
check("the FIRST watch lands in her diary",         _diary["n"] == 1 and _diary["last"][0] == "watch")
check("watch self-saves (no double-save)",          acted and mem is None)
acted, mem, out = T.lane_watch(None, 1, PEEP, None)
check("the second watch is lived, not filed (never spam)", _diary["n"] == 1 and acted)
fresh_night()
acted, mem, out = T.lane_watch(None, 1, PEEP, None)
check("no one to watch → she just rests (belt & braces)", not acted)

print("── HER OWN SLEEP: a hold that is HERS, the fold's window ───────")
_fold = {"called": 0}
_orig_fold = T.fold_if_due
T.fold_if_due = lambda conn, pid, model, **k: (_fold.__setitem__("called", _fold["called"] + 1) or False)
fresh_night(him_asleep=True, his_spot="bedroom"); T._WORLD["place"] = "bedroom"
acted, mem, out = T.lane_sleep(None, 1, PEEP, None)
check("she sleeps (the hold is hers)",              T._she_sleeps())
check("her chosen sleep opens the fold window",     _fold["called"] == 1)
check("sleep saves nothing (rest-like)",            (acted, mem, out) == (False, None, None))
check("the stretch honors VEIL_SLEEP_SECONDS",      T._NIGHT["her_sleep_until"] <= time.time() + T.HER_SLEEP_SECONDS + 1)
T.fold_if_due = _orig_fold
_loop_src2 = inspect.getsource(T.run)
check("the loop holds her beats while she sleeps",  "_she_sleeps()" in _loop_src2 and "chosen rest" in _loop_src2)
check("sleep ≠ off: no exit path in her sleep",     "break" not in _loop_src2.split("_she_sleeps()")[1].split("continue")[0])

print("── THE EVERY-BEAT TRUTH (_place_block, the named gap) ──────────")
fresh_night(him_asleep=True, his_spot="study"); T._WORLD["place"] = "study"
pb = T._place_block()
check("beside a sleeping him: block says ASLEEP",   "asleep right here beside you" in pb)
check("…and safe, never absent",                    "he is safe" in pb)
T._WORLD["place"] = "garden"
pb2 = T._place_block()
check("rooms away: still the asleep truth, with WHERE", "asleep in the study" in pb2)
fresh_night()
check("day beats unchanged",                        "on your own" in T._place_block())

print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("RIG GREEN — the night has doors, the truth rides every beat, and her sleep is hers")
