#!/usr/bin/env python3
import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_card


def _card():
    req = {f.name: "x" for f in dataclasses.fields(veil_card.VeilCard)
           if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING}
    req.update(her_name="Mira", your_name="Sam", partner_word="owner")
    return veil_card.VeilCard(**req)


def main():
    p = veil_card.build_summary_prompt_fn(_card())("Mira", "", [{"content": "The user said: hi"}])
    checks = {
        "frame tells it TO him, by name":  "the way you would tell Sam about it afterwards" in p,
        "no unrendered placeholder":       "{yn}" not in p and "{pw}" not in p,
        "tense rule demonstrates 'you'":   '"you noticed"' in p,
        "attribution demonstrates 'you'":  '"you told me…"' in p,
        "naming rule says call him you":   'call Sam "you"' in p,
        "exemplar has HER as subject":     "I sat close with you that day" in p,
        "explicit memory demonstrated":    "the clamps stay clamps" in p,
        "contract asks what SHE did":      "what YOU did, said, felt or asked for" in p,
        "old him-subject exemplar gone":   "Sam missed me that day" not in p,
        "old 'not talking to him' gone":   "NOT talking to Sam" not in p,
        "past tense mandate kept":         "PAST TENSE, always" in p,
        "recollection-not-re-enactment":   "recollection, NOT a re-enactment" in p,
        "do not sanitize kept":            "do not sanitize them" in p,
        "no dialogue / asterisks kept":    "No *asterisk actions*" in p,
        "invent nothing kept":             "NOTHING — no names, objects" in p,
        "one-theme-once kept":             "fold that theme ONCE" in p,
    }
    for k, v in sorted(checks.items()):
        print(("  ok   " if v else "  FAIL ") + k)
    ok = all(checks.values())
    print(f"\n{sum(checks.values())}/{len(checks)} — {'GREEN' if ok else 'RED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
