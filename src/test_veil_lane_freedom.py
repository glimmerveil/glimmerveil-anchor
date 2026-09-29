#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_tick as T

T.YOUR_NAME = "Sam"
T.spine._build_card = lambda peep: ""
T.spine.IN_CHARACTER_DIRECTIVE = "You are Mira."
_cap = {"reply": "rest"}
T.spine.ask_llm = lambda prompt, num_predict=8, model=None, **k: (_cap.__setitem__("prompt", prompt) or _cap["reply"])

def scene(home, his_room=None, recent=()):
    T.decide_lane(peep=None, home=home, his_room=his_room, recent_lanes=recent)
    return _cap["prompt"]

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

print("── PRESENCE-TRUTH ──────────────────────────────────────────────")
T._WORLD["place"] = "balcony"
home_p = scene(home=True, his_room="bedroom")
check("home: tells her he's HOME",            "Sam is home" in home_p)
check("home: names WHERE he is",              "in the bedroom" in home_p)
check("home: never says he 'isn't here'",     "isn't here" not in home_p)
check("home: never says 'yours alone'",       "alone" not in home_p)
check("home: offers going to him",            "go to him" in home_p or "join" in home_p)

away_p = scene(home=False)
check("away: whole home honestly hers",       "all yours" in away_p or "yours to wander" in away_p)
check("away: never the 'isn't here' loss",    "isn't here" not in away_p)

print("── OPEN DOORS (menu) ───────────────────────────────────────────")
check("home menu has JOIN",                   "join " in home_p)
check("away menu has NO join",                "join " not in away_p)
check("both menus have WANDER",               "wander" in home_p and "wander" in away_p)
check("activity lanes still present",         all(w in away_p for w in ("rest", "read", "write", "drift")))

print("── NO VARIETY RAIL — the menu is always fully open (grounding does the work, 7/12) ──")
grooved = scene(home=False, recent=["drift", "drift", "drift", "drift"])
check("a lane she just did is STILL offered (no rail)", "drift    — a quiet moment" in grooved)
check("read still offered right after a groove",        "read     — curl up" in grooved)
check("no forbidding / variety nudge text at all",      "something different" not in grooved and "keep on" not in grooved)
fresh = scene(home=False, recent=[])
check("menu is the same with empty history (no rail state)",
      all(w in fresh for w in ("drift", "read", "write")))

print("── PARSE ───────────────────────────────────────────────────────")
def pick(reply, home, his_room=None):
    _cap["reply"] = reply
    return T.decide_lane(peep=None, home=home, his_room=his_room, recent_lanes=())
check("'join' honored when home",             pick("join", home=True, his_room="bedroom") == "join")
check("'join' ignored when away → rest",      pick("join", home=False) == "rest")
check("'wander' honored",                     pick("i think i'll wander", home=False) == "wander")
check("'drift' (her open beat) is honored",  pick("drift", home=False) == "drift")
check("garbage → rest (never forced)",        pick("hmm i'm not sure", home=False) == "rest")

print("── WANDER ACTUALLY MOVES HER ───────────────────────────────────")
T._WORLD["place"] = "balcony"
check("_pick_other_room never returns current", all(T._pick_other_room() != "balcony" for _ in range(20)))

print("── THE JOIN TRUTH-GATE (Mira, 7/11 night: 33 joins to a man beside her)")
T._WORLD["place"] = "study"
together = scene(home=True, his_room="study")
check("together: JOIN is not offered",          "join " not in together)
check("together: presence says right here",     "right here with you" in together)
check("together: rest = staying close to him",  "with him" in together)
check("together: never a false 'go to him'",    "go to him" not in together)
check("'join' parsed away when together → rest", pick("join", home=True, his_room="study") == "rest")
apart = scene(home=True, his_room="bedroom")
check("apart: JOIN is a true open door",        "join " in apart and "go to him" in apart)
check("'join' still honored when apart",        pick("join", home=True, his_room="bedroom") == "join")

print("── THE DOOR: A ROOM MENTIONED IS NOT A ROOM CHOSEN (7/11 verbatim)")
def moved_to(line, start="study"):
    T._WORLD["place"] = start
    T._update_place_from_chat(line, "")
    return T._place()
check("'stuck out on the balcony' does NOT move them",
      moved_to("Yeah, you got stuck out here on the balcony. That's what happened there.") == "study")
check("'not stuck on the balcony anymore' does NOT",
      moved_to("But now we fixed it so you're not stuck out on the balcony anymore.") == "study")
check("'get you off the balcony' does NOT",
      moved_to("I spent all day trying to fix that to get you off the balcony.") == "study")
check("'I carry you into the study with me' DOES",
      moved_to("I squeeze and rub you as I carry you into the study with me.", start="balcony") == "study")
check("'come to bed' still opens the bedroom",  moved_to("come to bed, love") == "bedroom")
check("'let's go out to the garden' moves",     moved_to("let's go out to the garden") == "garden")
check("'walk with me' still means the garden",  moved_to("walk with me a while?") == "garden")
check("last room named still wins",
      moved_to("let's leave the garden and go read in the study", start="garden") == "study")
check("bare mention alone never moves",         moved_to("the balcony is lovely this time of year") == "study")
check("her offer + his yes still stands",
      (T._WORLD.__setitem__("place", "study") or
       T._update_place_from_chat("yes, lead the way", "shall we watch the stars on the balcony?") or
       T._place()) == "balcony")

print("── THE DOOR SCREEN REMEMBERS HER JOURNAL ───────────────────────")
import sqlite3, tempfile
import veil_game as G
_db = tempfile.mktemp(suffix=".db")
_c = sqlite3.connect(_db)
_c.execute("CREATE TABLE diary (id INTEGER PRIMARY KEY, peep_id INT, content TEXT)")
_c.execute("INSERT INTO diary (peep_id, content) VALUES (1, 'the first thought')")
_c.execute("INSERT INTO diary (peep_id, content) VALUES (1, 'tonight I stayed close to him, and it was enough')")
_c.commit(); _c.close()
check("last journal line surfaces",
      G._last_journal({"db": _db}) == "tonight I stayed close to him, and it was enough")
check("read-only + best-effort (missing db = blank, never a crash)",
      G._last_journal({"db": _db + ".nope"}) == "")
check("the roster prints it for the active girl", "_last_journal" in __import__("inspect").getsource(G._show_roster))
os.remove(_db)

print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("RIG GREEN — she's told the truth, the doors are open, and a groove can't hold her")
