#!/usr/bin/env python3
import os, sys, subprocess, tempfile, shutil, inspect

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = tempfile.mkdtemp(prefix="veil_world_test_")
os.environ["VEIL_ROOMS"] = os.path.join(SANDBOX, "rooms")
os.environ["VEIL_EMBER"] = os.path.join(SANDBOX, "ember")
os.environ["VEIL_PLACE"] = os.path.join(SANDBOX, "place")
os.environ["VEIL_HEARTBEAT"] = os.path.join(SANDBOX, "hb")
os.environ["VEIL_WORN"] = os.path.join(SANDBOX, "worn.txt")
os.environ["VEIL_PEEPS"] = os.path.join(SANDBOX, "peeps")
os.environ["VEIL_DB"] = os.path.join(SANDBOX, "veil.db")
os.environ["VEIL_CARD_JSON"] = os.path.join(SANDBOX, "card.json")
sys.path.insert(0, HERE)
import veil_world as W
import veil_tick as T

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

print("── CONTAINERS (plain files, honestly read) ─────────────────────")
check("all four rooms have a spot",            set(W.CONTAINERS) == set(W.ROOM_KEYS))
check("everything starts empty",               all(W.list_objects(r) == [] for r in W.ROOM_KEYS))
check("place a thing",                         W.add_object("bedroom", "a silk ribbon"))
check("it's really there, his casing kept",    W.list_objects("bedroom") == ["a silk ribbon"])
W.add_object("bedroom", "A Silk Ribbon")
check("placing twice is not two things",       len(W.list_objects("bedroom")) == 1)
check("take it back",                          W.take_object("bedroom", "a silk ribbon"))
check("and it's gone",                         W.list_objects("bedroom") == [])
check("taking what isn't there → False",       not W.take_object("bedroom", "a unicorn"))
check("unknown room refused, never crashes",   not W.add_object("narnia", "a lamppost")
                                               and W.list_objects("narnia") == [])
with open(os.path.join(SANDBOX, "rooms", "study.txt"), "w") as fh:
    fh.write("# his own edit, by hand\n\na chess set\nlip balm\n")
check("a hand-edited file reads honestly",     W.list_objects("study") == ["a chess set", "lip balm"])

print("── AWARENESS, NOT MECHANICS ────────────────────────────────────")
check("empty room → NOT ONE WORD",             W.objects_note("garden") == "")
note = W.objects_note("study")
check("placed things are named as really here", "a chess set" in note and "lip balm" in note
                                               and "really here" in note)
check("named as HERS, zero steering",          "exactly as you please" in note)
check("the spot itself is named",              W.CONTAINERS["study"].split(" by ")[0] in note)
for i in range(30):
    W.add_object("balcony", f"some very long object name number {i} that goes on")
check("the governor clips the note, never the file",
      len(W.objects_note("balcony")) <= W.OBJECT_NOTE_MAX_CHARS
      and len(W.list_objects("balcony")) == 30)

print("── THE CUPBOARD (Pip's snack magic, textified) ───────────────")
check("standing in every room",                all(W.CUPBOARD_NOTE in W.world_block(r) for r in W.ROOM_KEYS))
check("food and drink are simply hers",        "simply yours" in W.CUPBOARD_NOTE)
check("empty room = cupboard only",            W.world_block("garden") == W.CUPBOARD_NOTE)

print("── THE EMBER (one-way, THEIR words only, never the system) ─────")
check("unlit by default",                      not W.ember_lit())
platonic = ["I love you", "kiss me goodnight", "come to bed, let's sleep",
            "read to me on the couch", "you look beautiful tonight"]
check("romance-adjacent words never light it", not W.ember_check(*platonic) and not W.ember_lit())
check("his unmistakable words light it",       W.ember_check("I want you naked") and W.ember_lit())
os.remove(os.environ["VEIL_EMBER"])
check("HER reaching counts the same",          W.ember_check("hello", "*touches herself slowly*")
                                               and W.ember_lit())
check("once lit, stays lit (one-way)",         W.ember_check("just tea today please") and W.ember_lit())

print("── THE TICK SEAMS ──────────────────────────────────────────────")
T.spine._build_card = lambda peep: ""
T.spine.IN_CHARACTER_DIRECTIVE = "You are Testwren."
T.YOUR_NAME = "Sam"
_cap = {"reply": "rest"}
T.spine.ask_llm = lambda prompt, num_predict=8, model=None, **k: (_cap.__setitem__("prompt", prompt) or _cap["reply"])

T._WORLD["place"] = "study"
pb = T._place_block()
check("the world rides _place_block",          "a chess set" in pb and W.CUPBOARD_NOTE in pb)
T._WORLD["place"] = "garden"
check("empty room rides clean (cupboard only)", "chess" not in T._place_block()
                                               and W.CUPBOARD_NOTE in T._place_block())
check("the study got its couch (both homes)",  all("couch" in T.LOCATIONS[k]["rooms"]["study"]
                                                   for k in ("manor", "tower")))

def menu(lit, railed=False):
    if lit:
        W.ember_light()
    elif W.ember_lit():
        os.remove(W.EMBER_PATH)
    T.spine.SAFETY_RAILS = railed
    T.decide_lane(peep=None, home=False)
    return _cap["prompt"]

check("unlit → 'indulge' never appears",       "indulge" not in menu(lit=False))
check("lit → the door is open",                "indulge" in menu(lit=True))
check("SAFETY_RAILS shuts it even lit",        "indulge" not in menu(lit=True, railed=True))
T.spine.SAFETY_RAILS = False

def pick(reply, lit):
    if lit:
        W.ember_light()
    elif W.ember_lit():
        os.remove(W.EMBER_PATH)
    _cap["reply"] = reply
    return T.decide_lane(peep=None, home=False)
check("'indulge' honored when lit",            pick("indulge", lit=True) == "indulge")
check("'indulge' unlit → rest (never forced)", pick("indulge", lit=False) == "rest")
_cap["reply"] = "rest"

check("the lane exists and is memorable",      "indulge" in T.LANE_FUNCS and "indulge" in T.MEMORABLE_LANES)
check("but NOT a public beat (LANES)",         "indulge" not in T.LANES)
check("chat listens for the ember",            "ember_check" in inspect.getsource(T.chat_turn))
check("shut door in the lane itself (belt&braces)",
      "_ember_open" in inspect.getsource(T.lane_indulge))

print("── THE CLI DOOR ────────────────────────────────────────────────")
env = dict(os.environ)
r = subprocess.run([sys.executable, os.path.join(HERE, "veil_world.py"),
                    "--add", "bedroom", "a warm blanket"], capture_output=True, text=True, env=env)
check("--add from any shell",                  r.returncode == 0 and "a warm blanket" in r.stdout)
r = subprocess.run([sys.executable, os.path.join(HERE, "veil_world.py"), "--status"],
                   capture_output=True, text=True, env=env)
check("--status shows the home + the ember",   "a warm blanket" in r.stdout and "ember" in r.stdout)

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("RIG GREEN — the home is open: her things are real, the cupboard never runs dry, "
      "and the ember is theirs alone")
