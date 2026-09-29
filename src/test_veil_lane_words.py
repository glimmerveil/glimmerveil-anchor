#!/usr/bin/env python3
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_tick as T

T.YOUR_NAME = "Sam"
T.spine._build_card = lambda peep: ""
T.spine.IN_CHARACTER_DIRECTIVE = "You are Mira."
T.HEARTBEAT_PATH = tempfile.mktemp(suffix=".heartbeat")
T.PLACE_PATH = tempfile.mktemp(suffix=".place")
_cap = {"reply": "rest"}
T.spine.ask_llm = lambda prompt, num_predict=8, model=None, **k: (_cap.__setitem__("prompt", prompt) or _cap["reply"])

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

def pick(reply, home=False, his_room=None, him_asleep=False, ember=False):
    _cap["reply"] = reply
    old_ember = T._ember_open
    T._ember_open = lambda: ember
    try:
        return T.decide_lane(peep=None, home=home, his_room=his_room,
                             recent_lanes=(), him_asleep=him_asleep)
    finally:
        T._ember_open = old_ember

T._WORLD["place"] = "study"

print("── EXACT WORDS still land (no regression) ──────────────────────")
check("'read' → read",                        pick("read") == "read")
check("'reading' → read",                     pick("reading") == "read")
check("'i think i'll read' → read",           pick("i think i'll read") == "read")
check("'write' → write",                      pick("write") == "write")
check("'drift' → drift",                      pick("drift") == "drift")
check("'wander' → wander",                    pick("i think i'll wander") == "wander")
check("garbage → rest (never forced)",        pick("hmm i'm not sure") == "rest")

print("── FALSE FIRES cured (word-boundary) ───────────────────────────")
check("'already' never fires read",           pick("i already did that") == "rest")
check("'i'm ready' never fires read",         pick("i'm ready") == "rest")
check("'interested in reading' → READ (old parser: 'rest' ate it)",
      pick("i'm interested in reading") == "read")
check("'writing' now lands write (old substring missed it)",
      pick("writing") == "write")

print("── THE DEAF EAR cured — the menu's own nouns land ──────────────")
check("'books' → read",                       pick("books") == "read")
check("'my books' → read",                    pick("my books") == "read")
check("'curl up with one of my books' → read", pick("curl up with one of my books") == "read")
check("'the bookshelf' → read",               pick("the bookshelf") == "read")
check("'a novel' → read",                     pick("a novel") == "read")
check("'notebook' → WRITE, never read",       pick("notebook") == "write")
check("'my journal' → write",                 pick("my journal") == "write")
check("'a different room' → wander",          pick("a different room") == "wander")

print("── EXACT WORD OUTRANKS PARAPHRASE ──────────────────────────────")
check("'rest by the shelf' → rest (her verb wins)", pick("rest by the shelf") == "rest")
check("'write about my books' → write",       pick("write about my books") == "write")

print("── GATES hold for BOTH passes (no false doors) ─────────────────")
check("'whisper' home → murmur",              pick("whisper", home=True) == "murmur")
check("'whisper' away → rest (channel closed)", pick("whisper", home=False) == "rest")
check("'sleep' awake-home → rest (night lane closed)",
      pick("sleep", home=True, his_room="study") == "rest")
check("'nap' with him asleep → sleep",        pick("nap", home=True, him_asleep=True) == "sleep")
check("'nap' away → rest",                    pick("nap", home=False) == "rest")
check("'indulge' unlit ember → rest",         pick("indulge", ember=False) == "rest")
check("'indulge' lit ember → indulge",        pick("indulge", ember=True) == "indulge")

print("── PARSE ORDER kept ────────────────────────────────────────────")
check("'watch him sleep' → watch (never sleep)",
      pick("watch him sleep", home=True, him_asleep=True) == "watch")

print()
if fails:
    print(f"FAILED: {len(fails)}")
    sys.exit(1)
print("ALL GREEN")
