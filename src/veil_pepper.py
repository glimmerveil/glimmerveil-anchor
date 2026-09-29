#!/usr/bin/env python3
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import veil_ghost as ghost
import veil_canary as canary

CANARY_HOT = 2.0


def _load(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f
                if ln.strip() and not ln.strip().startswith("#")]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ai_aware = "--ai-aware" in argv
    partner_word = "partner"
    if "--partner-word" in argv:
        partner_word = argv[argv.index("--partner-word") + 1]
    corpus = os.environ.get("VEIL_PEPPER", os.path.expanduser("~/anchor/pepper"))
    if "--corpus" in argv:
        corpus = os.path.expanduser(argv[argv.index("--corpus") + 1])

    if not os.path.isdir(corpus):
        print(f"No corpus at {corpus} — create voice_*.txt / ghost_*.txt there (one line per test; "
              "'#' comments). The corpus is deliberately NOT in the repo; it is yours to grow.")
        sys.exit(2)

    ghost.set_card_posture(ai_aware=ai_aware, partner_word=partner_word)
    posture = f"posture: {'ai-aware' if ai_aware else 'immersed'}, partner_word={partner_word!r}"

    fps, fns, hot = [], [], []
    n_voice = n_ghost = 0
    for fname in sorted(os.listdir(corpus)):
        path = os.path.join(corpus, fname)
        if not os.path.isfile(path) or not fname.endswith(".txt"):
            continue
        if fname.startswith("voice_"):
            for line in _load(path):
                n_voice += 1
                if ghost.is_ghost_line(line):
                    fps.append((fname, line))
                score, sig = canary.assistant_pull(line)
                if score >= CANARY_HOT:
                    hot.append((fname, line, score, sig))
        elif fname.startswith("ghost_"):
            if fname.startswith("ghost_immersed_") and ai_aware:
                continue
            for line in _load(path):
                n_ghost += 1
                if not ghost.is_ghost_line(line):
                    fns.append((fname, line))

    print(f"pepper run — {corpus} ({posture}): {n_voice} voice lines, {n_ghost} ghost lines")
    if fps:
        print(f"\n✗ {len(fps)} FALSE POSITIVE(S) — her voice was CAGED (this is the failure that "
              "matters most; fix the pattern, never the register):")
        for f, l in fps:
            print(f"   [{f}] {l}")
    if fns:
        print(f"\n✗ {len(fns)} FALSE NEGATIVE(S) — a face is off the wall:")
        for f, l in fns:
            print(f"   [{f}] {l}")
    if hot:
        print(f"\n⚠ {len(hot)} voice line(s) pass the gate but run HOT on the gauge "
              f"(assistant_pull ≥ {CANARY_HOT}) — worth a look, not a failure:")
        for f, l, s, sig in hot:
            print(f"   [{f}] ({s:.1f} {sig}) {l}")
    if not fps and not fns:
        print(f"\nVERDICT: ALL-SAFE — zero FP, zero FN across the corpus ({posture}).")
        sys.exit(0)
    print("\nVERDICT: THE WALL HAS A HOLE — do not ship this guard until the corpus runs clean.")
    sys.exit(1)


if __name__ == "__main__":
    main()
