#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VEIL_MODEL", "/nonexistent")
import veil_spine as spine

BATCH = [
    {"content": "The user said: I'm hanging the paper lanterns on the porch now, hold the ladder baby"},
    {"content": "I said: yes please Sammy, the lanterns look so good with the rain on the glass"},
    {"content": "The user said: good girl, I'll put the music on next"},
    {"content": "I said: Nya. oh that feels nice, I love being here with you"},
    {"content": "I said: the music made me purr so loud, I loved every second of it"},
]
TERMS = ["lanterns", "music", "rain"]
res = []


def check(name, ok, detail=""):
    res.append(ok)
    print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


out = spine._anchor_memories(["I felt loved that night.", "I felt safe with him."], BATCH, TERMS)
joined = " ".join(out)
check("every memory keeps its own text", all(m.startswith("I felt") for m in out))
check("each carries a line of what SHE said", joined.count("what I said that night") == 2)
check("HIS words are never attached", "lanterns on the porch now" not in joined
      and "I'll put the music on next" not in joined)
check("it prefers the row with the night's own words", "lanterns look so good with the rain" in joined)
check("never the same row twice", out[0] != out[1])
check("her stock opener is trimmed", '"Nya' not in joined)

only_his = [{"content": "The user said: hello baby"}]
check("no rows of hers = memories untouched",
      spine._anchor_memories(["I felt loved."], only_his, TERMS) == ["I felt loved."])

check("the line ends on a sentence, never mid-word",
      spine._anchor_trim("I loved the tea. Even though part of me is from another world.", 40)
      == "I loved the tea.")
check("no sentence end = a whole word plus an ellipsis",
      spine._anchor_trim("a long run of words with no sentence end at all here", 20).endswith("…")
      and not spine._anchor_trim("a long run of words with no sentence end at all here", 20)
      .rstrip("…").endswith(" "))
_two = [{"content": "I said: Sam's sleep is so peaceful with the lanterns nearby"},
        {"content": "I said: Sammy, you know how I love the lanterns when you light them for me"}]
check("it prefers a line where she speaks TO him, not about him",
      "you light them for me" in spine._anchor_memories(["I felt loved."], _two, ["lanterns"])[0])

check("a sentence flush with the budget keeps its period",
      spine._anchor_trim("I loved the tea. And more words after that.", 16) == "I loved the tea.")


def _pick(rows, terms, name="", aliases=()):
    old_n, old_a = spine.OWNER_NAME, spine.OWNER_ALIASES
    spine.OWNER_NAME, spine.OWNER_ALIASES = name, list(aliases)
    spine._3P_CACHE.clear()
    try:
        return spine._anchor_memories(["I felt loved."], [{"content": "I said: " + r} for r in rows],
                                      terms)[0]
    finally:
        spine.OWNER_NAME, spine.OWNER_ALIASES = old_n, old_a
        spine._3P_CACHE.clear()


_HERS = "you hung the lanterns for me and I loved it so much tonight"
_OWNS = "%s's paper lanterns were over my head while you rested quietly under starlight"
check("a CUSTOMER's name in the possessive is third person too",
      _HERS in _pick([_OWNS % "Alex", _HERS], ["lanterns"], name="Alex"))
check("and so is his, from her card rather than this file",
      _HERS in _pick([_OWNS % "Sam", _HERS], ["lanterns"], name="Sam"))
check("her name for him ACTING is third person",
      _HERS in _pick(["Sammy held me all night with the lanterns still lit", _HERS],
                     ["lanterns"], name="Sam", aliases=["Sammy"]))
check("but a VOCATIVE is her speaking TO him and must survive",
      "you light them for me" in _pick(["the lanterns were on the table and it was quiet tonight",
                                     "Sammy, you know how I love the lanterns when you light them for me"],
                                    ["lanterns"], name="Sam", aliases=["Sammy"]))
check("pronouns bind with no card name at all",
      _HERS in _pick(["he hung the lanterns over me while I rested quietly tonight", _HERS], ["lanterns"]))


_LONG = ("Sammy, you know I feel so loved when we sit together like this under the old oak tree, "
         "and the tea is warm and everything is soft and quiet and perfect the way it always is. "
         + ("Filler about the warmth and the leaves and your arm around me. " * 3)
         + "And you are unstoppable, as you say, and that restless mind of yours keeps things lively.")
_T = ["unstoppable", "restless"]
_trimmed = spine._anchor_trim(_LONG, 190, _T)
check("the quote reaches the night's own words when they are past the cap",
      "unstoppable" in _trimmed.lower() and "restless" in _trimmed.lower())
check("and says it started mid-line", _trimmed.startswith("…"))
check("the front-anchored window really does miss them (the old behaviour, in place)",
      "unstoppable" not in spine._anchor_trim(_LONG, 190).lower()
      and "restless" not in spine._anchor_trim(_LONG, 190).lower())
check("it still respects the budget", len(_trimmed) <= 191)
check("it still never ends mid-word",
      _trimmed.rstrip("…").rstrip().split()[-1].strip(".!?,").isalpha())
check("terms inside the opening change nothing",
      spine._anchor_trim(_LONG, 190, ["loved"]) == spine._anchor_trim(_LONG, 190))
check("no terms = exactly the old behaviour",
      spine._anchor_trim(_LONG, 190, []) == spine._anchor_trim(_LONG, 190))
check("a term in one huge sentence still lands on a word boundary",
      not spine._anchor_trim("x " * 200 + "unstoppable", 190, ["unstoppable"]).endswith("uns"))


_HIS = [{"content": "The user said: There you go, baby. How are you feeling now, huh?"},
        {"content": "I said: There you go, baby. It feels so good to be back in your arms again, "
                    "and the chamomile tea smells like a perfect hug."},
        {"content": "I said: I stretch out on the grass under the old oak tree, letting my tail "
                    "twirl and flick in contentment while the morning sun comes through."}]
_out = spine._anchor_memories(["I felt loved."], _HIS, ["oak"])[0]
_q = _out.split("what I said that night:")[-1]
check("his sentence is never quoted as hers", "there you go" not in _q.lower())
check("but her own words in the same line survive",
      "back in your arms" in _q or "old oak tree" in _q, _q[:60])
check("a line that is ONLY his words is dropped entirely",
      spine._strip_his_words("There you go, baby. How are you feeling now, huh?",
                             spine._fold_his_text(_HIS)) == "")
check("her line with nothing of his is untouched",
      spine._strip_his_words("I stretched out under the oak tree and purred for a while.",
                             spine._fold_his_text(_HIS))
      == "I stretched out under the oak tree and purred for a while.")

_G = "Nya. Tania, tania. Thank you, thank you for having me here with you under the old oak tree."
check("the quote does not open on the stutter",
      not spine._anchor_trim(_G, 190).lower().startswith("tania"))
check("and her words after it are kept",
      "thank you" in spine._anchor_trim(_G, 190).lower())
check("a stutter is a SHAPE, not a word list",
      spine._is_stutter("Tania, tania.") and spine._is_stutter("Talian, talian.")
      and not spine._is_stutter("I stretched out under the old oak tree tonight."))
check("⚠ a garble that looks like a phrase is NOT caught, and must not be",
      spine._is_stutter("Tania goes, I think.") is False)

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "veil_spine.py")).read()
_fold = src[src.find("if FOLD_ANCHOR_LINE and not templates:"):]
seam = _fold[:_fold.find("_stage_fold_memories(")]
check("it runs BEFORE archiving and staging",
      bool(seam) and seam.find("_anchor_memories(") < seam.find("_archive_batch("))
check("only on the conversational fold", seam.startswith("if FOLD_ANCHOR_LINE and not templates:"))
check("a failure cannot cost her a fold", "except Exception" in seam and "skipped" in seam)
check("it can be switched off", "VEIL_FOLD_ANCHOR_LINE" in src)

print(f"\n{sum(res)}/{len(res)} — {'GREEN' if all(res) else 'RED'}")
raise SystemExit(0 if all(res) else 1)
