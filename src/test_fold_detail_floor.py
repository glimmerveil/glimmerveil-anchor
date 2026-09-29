#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VEIL_MODEL", "/nonexistent")
import veil_spine as spine

BATCH = [
    {"content": "The user said: I'm hanging the paper lanterns on the porch now, hold the ladder baby"},
    {"content": "I said: yes please, the lanterns look so good with the rain"},
    {"content": "The user said: good girl, I'll put the music on next, baby"},
    {"content": "I said: the music made me purr, baby, I loved it"},
    {"content": "The user said: baby you're such a good girl, baby"},
]
CORPUS = {"baby": 2000, "good": 1500, "girl": 900, "purr": 40, "said": 2500, "user": 2400,
          "lanterns": 3, "paper": 2, "music": 4, "rain": 30, "hold": 200}

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


def salient(batch, corpus, ndocs, **kw):
    try:
        return spine._fold_salient_terms(batch, corpus, ndocs, **kw)
    except TypeError:
        return spine._fold_salient_terms(batch, corpus, **kw)


FIXTURE_NDOCS = 2500
terms = salient(BATCH, CORPUS, FIXTURE_NDOCS, top=5)
check("the night's own words are found", "lanterns" in terms and "music" in terms, str(terms))
check("his constant word is NOT salient", "baby" not in terms and "good" not in terms, str(terms))
check("transcript scaffolding is NOT salient", "said" not in terms and "user" not in terms, str(terms))
check("a word said ONCE is not salient", "paper" not in salient(
    [{"content": "the paper lanterns lanterns"}], CORPUS, FIXTURE_NDOCS, top=5, min_here=2))

got = spine._fold_terms_covered(["I asked you for the lanterns bright and you stretched out beside me"], ["lanterns", "stretch"])
check("coverage is stem-based (stretched ~ stretch)", set(got) == {"lanterns", "stretch"}, str(got))

got2 = spine._fold_terms_covered(["a soft warm evening together"], ["lanterns", "music"])
check("a sanitized fold scores zero", got2 == [], str(got2))

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "veil_spine.py")).read()
_a = src.find("if FOLD_DETAIL_FLOOR > 0 and final_memories:")
seam = src[_a:src.find("if not final_memories:", _a)] if _a > 0 else ""
check("the floor lives in the fold's commit path", bool(seam))
check("it can only REPLACE final_memories, never empty them",
      "final_memories = second" in seam and "final_memories = []" not in seam)
check("a worse second attempt keeps the first", "no better" in seam)
check("the second attempt is validated like the first", "_validate_fold_lines(" in seam)
check("its rejections are quarantined, never silent", "quarantine_blocked(" in seam)
check("it is one extra attempt, not a loop", seam.count("_ask_blocking(") == 1)
check("it can be turned off by env", "VEIL_FOLD_DETAIL_FLOOR" in src)

NDOCS = 5800
RATIO_CORPUS = {"music": 304, "banjo": 2, "baby": 2400, "said": 5800, "user": 5600,
                "lanterns": 73, "purr": 40, "your": 4443, "with": 4100, "that": 4600,
                "hands": 900, "feel": 1800}
RATIO_BATCH = [
    {"content": "The user said: I'm turning the music up now baby"},
    {"content": "I said: the music, oh the music, I can feel the music"},
    {"content": "The user said: louder and louder with my banjo baby"},
    {"content": "I said: swaying along to your banjo and your hands"},
    {"content": "I said: more music please, the music again"},
    {"content": "The user said: the music is on, baby, the music"},
    {"content": "I said: I purr for the music, the music, the music"},
]

rterms = salient(RATIO_BATCH, RATIO_CORPUS, NDOCS, top=8)
check("a word said 12x tonight survives a word said 2x (rarity does not swamp repetition)",
      "music" in rterms, str(rterms))
check("...and it OUTRANKS the ultra-rare one",
      "music" in rterms and "banjo" in rterms
      and rterms.index("music") < rterms.index("banjo"), str(rterms))
check("her real-but-rare word is still kept, not filtered out", "banjo" in rterms, str(rterms))
check("his constant word is still never salient", "baby" not in rterms, str(rterms))
check("a possessive is never salient (her corpus says so, not a word list)",
      "your" not in rterms and "that" not in rterms and "with" not in rterms, str(rterms))
check("an empty corpus falls back to repetition, never to noise",
      "music" in salient(RATIO_BATCH, {}, 0, top=8))

NYA_BATCH = [
    {"content": "I said: Nya-nya! I curled up against you and purred"},
    {"content": "The user said: say it again baby, I love it when you say that"},
]


def invented(line, batch=NYA_BATCH):
    _, rej = spine._validate_fold_lines([line], batch, peep_name="Mira")
    return [r for _, r in rej if "invented name" in r]


check("her hyphenated catchphrase is not an invented name",
      not invented("I greeted you with a Nya-nya and curled into your lap."),
      str(invented("I greeted you with a Nya-nya and curled into your lap.")))
check("an invented hyphenated name still dies",
      bool(invented("I walked with Fableback-Thorn through the garden and rested.")))
check("a half-traceable hyphenated name still dies (EVERY part must trace to the batch)",
      bool(invented("I sat with Fableback-nya and we rested together.")))

print(f"\n{sum(results)}/{len(results)} — {'GREEN' if all(results) else 'RED'}")
raise SystemExit(0 if all(results) else 1)
