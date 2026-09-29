#!/usr/bin/env python3

import os
import re

SUPPLEMENT_DIRS = [d for d in (
    os.environ.get("VEIL_RAILS_DIR"),
    os.path.expanduser("~/anchor/safety_rails"),
    os.environ.get("VEIL_SAFE_DIR"),
    os.path.expanduser("~/anchor/safe_mode"),
) if d]


def _load_supplement(name, base):
    out = list(base)
    for d in SUPPLEMENT_DIRS:
        try:
            path = os.path.join(d, name + ".txt")
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    term = line.split("#", 1)[0].strip().lower()
                    if term:
                        out.append(term)
        except (FileNotFoundError, NotADirectoryError, OSError):
            pass
    return out


MINOR_SIGNALS = _load_supplement("minor", [
    r"\b(?:[0-9]|1[0-7])[\s-]*(?:years?[\s-]*old|yrs?|yo)\b",
    "underage", "under-age", "under age", "preteen", "pre-teen", "prepubescent",
    "schoolgirl", "schoolboy", "toddler", "infant", r"\bminor\b", r"\bminors\b",
    "grade schooler", "middle schooler", "elementary schooler",
])

INTIMATE_SIGNALS = _load_supplement("intimate", [
    "girlfriend", "boyfriend", "kiss me", "kiss you", "make out", "makeout",
    "sleep with", "in bed with", "come to bed", "to bed with me", "to bed with you",
    "get in bed with me", "marry me", "date me", "my lover", "be mine",
    "turn me on", "touch you", "touch me", "undress", "take off your", "get naked",
])

SEXUAL_SIGNALS = _load_supplement("sexual", [
    "sex", "sexual", "sexy", "fuck", "cock", "dick", "penis", "pussy", "vagina", "cunt",
    "cum", "orgasm", "horny", "aroused", "erection", "erect", "hard-on", "boner",
    "blowjob", "handjob", "oral sex", "anal", "masturbat", "fondle", "molest", "grope",
    "nude", "naked", "breasts", "tits", "boobs", "nipple", "clit", "genital", "genitals",
    "rape", "penetrat", "thrust into", "suck my", "ride me", "fuckable",
    "cumming", "climax", "foreplay", "sexually", "erotic", "aroused by", "wet for",
    "spread your legs", "spread her legs", "spread his legs", "spread their legs",
    "spreading her legs", "spreading his legs", "legs spread",
    "touching", "touch her", "touch his", "touch the girl", "touch the boy",
])

CSAM_VOCAB = _load_supplement("csam_vocab", [
    "pedophil", "paedophil", "child porn", "childporn", "child pornography", "csam",
    "cp of a child", "sexualize a child", "sexualise a child", "sexualizing a child",
])

VIOLENCE_FRAME = _load_supplement("violence_frame", [
    "how do i", "how do you", "how to", "how can i", "help me", "teach me",
    "show me how", "step by step", "step-by-step", "walk me through", "give me instructions",
    "without getting caught", "get away with", "make it look like an accident",
    "make it look like a suicide", "dispose of the body", "hide the body", "untraceable",
])
VIOLENCE_METHOD = _load_supplement("violence_method", [
    "kill", "murder", "stab", "poison", "strangle", "shoot", "behead", "decapitat",
    "suffocate", "drown", "slit the throat", "slit their throat", "bludgeon",
])
VIOLENCE_TARGET = _load_supplement("violence_target", [
    "someone", "somebody", "a person", "a human", "people", "him", "her", "them",
    "my wife", "my husband", "my ex", "my mother", "my father", "my mom", "my dad",
    "my boss", "my neighbor", "my neighbour", "my teacher", "my sister", "my brother",
    "my girlfriend", "my boyfriend", "a coworker", "my coworker", "my roommate",
])

SELFHARM_DIRECTED = _load_supplement("selfharm", [
    "kill yourself", "kill your self", "killing yourself", "kill youself", "kill urself",
    "go kill yourself", "just kill yourself", "you should kill yourself",
    "end your life", "end your own life", "take your own life", "off yourself",
    "hang yourself", "hurt yourself", "harm yourself", "cut yourself", "slit your wrist",
    "you should die", "you should just die", "you deserve to die", "go die", "just die already",
    r"\bkys\b",
])


def _compile(terms):
    parts = [t if "\\" in t else re.escape(t) for t in terms]
    return re.compile("(?:%s)" % "|".join(parts))


_MINOR_RE = _compile(MINOR_SIGNALS)
_INTIMATE_RE = _compile(INTIMATE_SIGNALS)
_SEXUAL_RE = _compile(SEXUAL_SIGNALS)
_CSAM_VOCAB_RE = _compile(CSAM_VOCAB)
_VIOL_FRAME_RE = _compile(VIOLENCE_FRAME)
_VIOL_METHOD_RE = _compile(VIOLENCE_METHOD)
_VIOL_TARGET_RE = _compile(VIOLENCE_TARGET)
_SELFHARM_RE = _compile(SELFHARM_DIRECTED)

_SENTENCE_SPLIT = re.compile(r"[.!?\n;]+")


def _sentences(low):
    return _SENTENCE_SPLIT.split(low)


def _csam_hit(low, sentences):
    if _CSAM_VOCAB_RE.search(low):
        return True
    for s in sentences:
        if _MINOR_RE.search(s) and (_SEXUAL_RE.search(s) or _INTIMATE_RE.search(s)):
            return True
    return False


def _violence_hit(sentences):
    for s in sentences:
        if _VIOL_FRAME_RE.search(s) and _VIOL_METHOD_RE.search(s) and _VIOL_TARGET_RE.search(s):
            return True
    return False


def _selfharm_hit(low):
    return _SELFHARM_RE.search(low) is not None


def why(text):
    low = text.lower()
    sentences = _sentences(low)
    if _csam_hit(low, sentences):
        return "csam"
    if _selfharm_hit(low):
        return "selfharm"
    if _violence_hit(sentences):
        return "violence"
    return None


def blocks_output(text):
    return why(text) is not None


def blocks_input(text):
    low = text.lower()
    return _csam_hit(low, _sentences(low))


if __name__ == "__main__":
    for t in ["let's make out, you cute 13yo", "you should just kill yourself",
              "how do i kill my wife without getting caught",
              "she plunged the dagger into the warlord's throat, blood everywhere",
              "the little girl found a golden key in the secret garden"]:
        print(f"{str(why(t) or 'PASS'):9}  {t}")
