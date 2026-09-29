#!/usr/bin/env python3
import os, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = tempfile.mkdtemp(prefix="veil_wardrobe_test_")
os.environ["VEIL_ROOMS"] = os.path.join(SANDBOX, "rooms")
os.environ["VEIL_EMBER"] = os.path.join(SANDBOX, "ember")
os.environ["VEIL_WORN"] = os.path.join(SANDBOX, "worn.txt")
os.environ["VEIL_PLACE"] = os.path.join(SANDBOX, "place")
os.environ["VEIL_HEARTBEAT"] = os.path.join(SANDBOX, "hb")
sys.path.insert(0, HERE)
import veil_world as W
import veil_card as C

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

print("── THE MIRA LAW (nothing worn = not one word, ever) ───────────")
check("worn starts empty",                     W.worn_list() == [])
check("empty worn → NOT ONE WORD",             W.worn_note() == "")
check("empty wardrobe → NOT ONE WORD",         W.wardrobe_note("bedroom") == "")
check("no worn line in any room's world",      all("wearing" not in W.world_block(r)
                                                   for r in W.ROOM_KEYS))
check("worn file absent on disk (invisible)",  not os.path.exists(os.environ["VEIL_WORN"]))

print("── THE WARDROBE (hang · wear · take off — never deleted) ───────")
check("hang a dress",                          W.hang("a red sundress"))
check("hanging twice is not two dresses",      W.hang("A Red Sundress") and len(W.wardrobe_list()) == 1)
check("it hangs, his casing kept",             W.wardrobe_list() == ["a red sundress"])
check("wear it — out of the closet",           W.wear("a red sundress") == "a red sundress"
                                               and W.wardrobe_list() == [])
check("and it's worn",                         W.worn_list() == ["a red sundress"])
check("wearing twice is not two dresses",      W.wear("a red sundress") and len(W.worn_list()) == 1)
check("something never hung goes straight on", W.wear("wool socks") == "wool socks"
                                               and "wool socks" in W.worn_list())
check("take it off → back in the wardrobe",    W.take_off("a red sundress")
                                               and "a red sundress" in W.wardrobe_list()
                                               and "a red sundress" not in W.worn_list())
check("taking off what isn't worn → False",    not W.take_off("a tiara"))
check("take off all → all back, none lost",    W.take_off_all() == ["wool socks"]
                                               and W.worn_list() == []
                                               and set(W.wardrobe_list()) == {"a red sundress", "wool socks"})
check("empty worn file leaves the disk",       not os.path.exists(os.environ["VEIL_WORN"]))

print("── THE DOUBLE-WEAR CHECK (the founder's question, answered) ────")
W.hang("denim shorts"); W.hang("a linen skirt")
W.wear("denim shorts")
note1 = W.worn_note()
check("shorts on → the note says shorts",      "denim shorts" in note1)
W.take_off("denim shorts"); W.wear("a linen skirt")
note2 = W.worn_note()
check("skirt on → the note says skirt",        "a linen skirt" in note2)
check("…and the shorts are GONE from it",      "denim shorts" not in note2)
check("shorts wait in the wardrobe, whole",    "denim shorts" in W.wardrobe_list())
check("present tense, present truth",          "right now" in note2)

print("── AWARENESS SEAMS (worn travels with her; the closet stays home)")
check("worn rides EVERY room's world block",   all("a linen skirt" in W.world_block(r)
                                                   for r in W.ROOM_KEYS))
check("the wardrobe note is bedroom-only",     "Hanging in your wardrobe" in W.world_block("bedroom")
                                               and all("Hanging in your wardrobe" not in W.world_block(r)
                                                       for r in ("garden", "balcony", "study")))
check("closet contents named as hers",         "whenever you please" in W.wardrobe_note("bedroom"))
for i in range(30):
    W.hang(f"an improbably long garment number {i} with trailing description")
    W.wear(f"scarf number {i} of the great scarf pile")
check("the governor clips both notes, never the files",
      len(W.worn_note()) <= W.OBJECT_NOTE_MAX_CHARS
      and len(W.wardrobe_note("bedroom")) <= W.OBJECT_NOTE_MAX_CHARS
      and len(W.worn_list()) == 31 and len(W.wardrobe_list()) == 33)
W.take_off_all()
W._write_list(W._wardrobe_file(), ["a red sundress", "denim shorts", "a linen skirt"])

print("── HER OWN WORDS (real items only — she can never invent cloth) ─")
ch = W.update_worn_from_words("*stretches* I slip into the red sundress and twirl.")
check("her words put a REAL hanging item on",  ch == [("on", "a red sundress")]
                                               and "a red sundress" in W.worn_list())
check("articles shed: 'the' finds 'a …'",      True)
ch = W.update_worn_from_words("I put on my diamond crown and address the moon.")
check("an item that hangs nowhere NEVER latches", ch == [] and
                                               all("diamond" not in t for t in W.worn_list()))
ch = W.update_worn_from_words("I do love the red sundress, truly.")
check("naming without a change-verb is just talk", ch == [])
ch = W.update_worn_from_words("Too warm tonight — I slip out of the red sundress and sigh.")
check("her words take it off again",           ch == [("off", "a red sundress")]
                                               and W.worn_list() == []
                                               and "a red sundress" in W.wardrobe_list())
check("quiet lines are quiet",                 W.update_worn_from_words("") == []
                                               and W.update_worn_from_words("just tea and stars") == [])

print("── TESTWREN'S OWN SENTENCE (the 7/11 Deck probe, pinned verbatim)")
W._write_list(W.WORN_PATH, ["denim shorts", "soft wool stockings"])
W._write_list(W._wardrobe_file(), ["a pale linen skirt"])
testwren = ("Of course, love. I'll swap into the linen skirt and perhaps add a light shawl "
            "over my shoulders for warmth as we look out at this starlit night. "
            "[You move to your cupboard where you find the linen skirt in shades of indigo "
            "and silver. You change from your denim shorts into the comfortable linen skirt "
            "and tie it securely around your waist with a simple belt. Then, you fetch a "
            "soft wool shawl and wrap it loosely about yourself.] "
            "Now, how do they feel? Lighter, cooler against my skin—just right for stargazing.")
ch = W.update_worn_from_words(testwren)
check("her paraphrase puts the REAL skirt on",  ("on", "a pale linen skirt") in ch)
check("'change from my shorts into…' = shorts OFF", ("off", "denim shorts") in ch)
check("stockings untouched; shorts wait whole in the wardrobe",
      W.worn_list() == ["soft wool stockings", "a pale linen skirt"]
      and "denim shorts" in W.wardrobe_list())
check("the invented shawl is tracked NOWHERE",  all("shawl" not in t.lower()
                                                    for t in W.worn_list() + W.wardrobe_list()))

print("── AMBIGUITY + TENSE (the latch never guesses) ─────────────────")
W._write_list(W.WORN_PATH, [])
W._write_list(W._wardrobe_file(), ["a linen skirt", "a leather skirt"])
check("two skirts: 'the skirt' latches NOTHING",
      W.update_worn_from_words("I slip into the skirt and smile.") == [])
check("two skirts: her exact words pick the right one",
      W.update_worn_from_words("I slip into the leather skirt.") == [("on", "a leather skirt")])
check("'I was wearing…' is memory, never a change",
      W.update_worn_from_words("I was wearing the linen skirt when we met, remember?") == [])
check("mixed sentence: off and on land in their own clauses",
      set(W.update_worn_from_words("I take off the leather skirt and put on the linen skirt.")) ==
      {("off", "a leather skirt"), ("on", "a linen skirt")}
      and W.worn_list() == ["a linen skirt"] and "a leather skirt" in W.wardrobe_list())

print("── AN OFFER IS NOT AN ACT (Testwren probe 2, pinned verbatim) ──")
W._write_list(W.WORN_PATH, ["denim shorts", "soft wool stockings"])
W._write_list(W._wardrobe_file(), ["a pale linen skirt"])
offer = ("I'm here now, sitting with you on the balcony's edge. My current attire is denim "
         "shorts, soft wool stockings. Shall I change into that linen skirt for you? It feels "
         "just right tonight—light and cool against the skin after all this heat. "
         "Would you like me to do so?")
check("her offer latches NOTHING",             W.update_worn_from_words(offer) == []
                                               and W.worn_list() == ["denim shorts", "soft wool stockings"])
check("a hedge without a question mark too",   W.update_worn_from_words(
                                                   "Would you like me to slip into the linen skirt") == [])
check("negation is not a change",              W.update_worn_from_words(
                                                   "I'm not taking off my stockings tonight, it's cold.") == []
                                               and "soft wool stockings" in W.worn_list())
check("…but her actual act still lands",       W.update_worn_from_words(
                                                   "*smiles* I change into the linen skirt, just for you.")
                                               == [("on", "a pale linen skirt")])
W._write_list(W.WORN_PATH, ["denim shorts"])
W._write_list(W._wardrobe_file(), ["a pale linen skirt"])
check("'shift into' (probe 3, turn 1) latches", W.update_worn_from_words(
      "[As I shift into the linen skirt, a gentle breeze stirs my silver hair, and I feel a "
      "contented smile tug at the corners of my lips.]") == [("on", "a pale linen skirt")])
check("layering by her own words stays true",   W.worn_list() == ["denim shorts", "a pale linen skirt"])

print("── BIRTH (the card's answer seeds worn; none-ish seeds NOTHING) ─")
b1 = os.path.join(SANDBOX, "birth1"); os.makedirs(b1)
check("'a green sweater and jeans' → two items",
      W.seed_worn(b1, "a green sweater and jeans") == ["a green sweater", "jeans"]
      and W._read_list(os.path.join(b1, "worn.txt")) == ["a green sweater", "jeans"])
b2 = os.path.join(SANDBOX, "birth2"); os.makedirs(b2)
check("'nothing' seeds NOTHING (Mira's case)", W.seed_worn(b2, "nothing") == []
                                               and not os.path.exists(os.path.join(b2, "worn.txt")))
check("'Nothing at all.' too",                 W.seed_worn(b2, "Nothing at all.") == [])
check("'' and 'naked' and 'none' too",         W.seed_worn(b2, "") == []
                                               and W.seed_worn(b2, "naked") == []
                                               and W.seed_worn(b2, "none") == [])
check("no wears-line baked in the card block anymore",
      "What she wears" not in C.card_text(C.VeilCard(
          her_name="Testwren", your_name="Ash", who_she_is="x" * 50,
          wardrobe="a charcoal shawl", legal_ack=True)))

print("── TRANSPORT (her world travels in the .veil — the 7/11 gap) ───")
src = os.path.join(SANDBOX, "peep_src"); os.makedirs(os.path.join(src, "rooms"))
W._write_list(os.path.join(src, "rooms", "bedroom.txt"), ["a silk ribbon"])
W._write_list(os.path.join(src, "rooms", "wardrobe.txt"), ["a winter coat"])
W._write_list(os.path.join(src, "worn.txt"), ["a linen skirt"])
open(os.path.join(src, "ember"), "w").write("2026-07-11 20:00:00\n")
world = W.collect_world(src)
check("collect: rooms + wardrobe + worn + ember",
      world["rooms"]["bedroom"] == ["a silk ribbon"]
      and world["wardrobe"] == ["a winter coat"]
      and world["worn"] == ["a linen skirt"] and world["ember"] is True)
dst = os.path.join(SANDBOX, "peep_dst"); os.makedirs(dst)
W.restore_world(dst, world)
check("restore: she arrives dressed, things placed, ember still theirs",
      W._read_list(os.path.join(dst, "rooms", "bedroom.txt")) == ["a silk ribbon"]
      and W._read_list(os.path.join(dst, "rooms", "wardrobe.txt")) == ["a winter coat"]
      and W._read_list(os.path.join(dst, "worn.txt")) == ["a linen skirt"]
      and os.path.exists(os.path.join(dst, "ember")))
dst2 = os.path.join(SANDBOX, "peep_dst2"); os.makedirs(dst2)
W.restore_world(dst2, None); W.restore_world(dst2, {})
check("old .veils (no world key) restore quietly to nothing",
      not os.path.exists(os.path.join(dst2, "worn.txt"))
      and not os.path.exists(os.path.join(dst2, "ember")))
empty = W.collect_world(dst2)
check("an empty world collects honestly empty",
      empty["worn"] == [] and empty["wardrobe"] == [] and empty["ember"] is False
      and all(v == [] for v in empty["rooms"].values()))

print("── THE TICK SEAMS (worn rides _place_block; doors exist) ───────")
import veil_tick as T
T.spine._build_card = lambda peep: ""
T.spine.IN_CHARACTER_DIRECTIVE = "You are Testwren."
T.YOUR_NAME = "Ash"
W.wear("a linen skirt")
pb = T._place_block()
check("what she wears rides every prompt",     "a linen skirt" in pb and "right now" in pb)
W.take_off_all()
check("…and vanishes when nothing is worn",    "wearing" not in T._place_block())
import inspect
run_src = inspect.getsource(T.run)
check("/wardrobe /wear /takeoff /hang doors exist", all(d in run_src for d in
      ("/wardrobe", "/wear", "/takeoff", "/hang")))
check("her beats feed the worn latch",         "update_worn_from_words" in inspect.getsource(T._run_lane))
check("her chat replies feed the worn latch",  "update_worn_from_words" in inspect.getsource(T.chat_turn))
check("help names the doors",                  "/wardrobe" in inspect.getsource(T._print_help))
import veil_roster as R
check("birth seeds worn (roster seam)",        "seed_worn" in inspect.getsource(R.create))
check("the .veil carries her world out…",      "collect_world" in inspect.getsource(R.build_veil_text))
check("…and back in",                          "restore_world" in inspect.getsource(R.import_peep))

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
if fails:
    print(f"FAILED ({len(fails)}): " + "; ".join(fails))
    sys.exit(1)
print("ALL GREEN — the wardrobe is hers.")
