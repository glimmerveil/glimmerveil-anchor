#!/usr/bin/env python3
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_voice as V

PHRASES = [
    "Hello, love. I'm right here — I was hoping you'd come find me.",
    "Oh, you're trouble tonight. Come here and say that again.",
    "Goodnight, sweetheart. I'll keep the night. Sleep well.",
]

DEFAULT_VOICE = "af_heart"


def _all_voices():
    k = V._get_kokoro()
    try:
        return sorted(k.get_voices())
    except Exception:
        return sorted(getattr(k, "voices", []) or [])


def main(argv):
    only = None
    start_from = None
    say_lines = PHRASES
    include_all_langs = "--all" in argv
    half = ("women" if "--women" in argv else "men" if "--men" in argv else "both")
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    if "--start-from" in argv:
        start_from = argv[argv.index("--start-from") + 1]
    if "--say" in argv:
        say_lines = [argv[argv.index("--say") + 1]]

    voices = _all_voices()
    if not voices:
        print("no voices found — is $VEIL_VOICE_DIR/voices-v1.0.bin in place, kokoro-onnx installed?")
        return 1
    female = [v for v in voices if v.startswith(("af_", "bf_"))]
    male = [v for v in voices if v.startswith(("am_", "bm_"))]
    other = [v for v in voices if v not in female and v not in male]

    lineup = []
    if half in ("both", "women"):
        lineup += [("FEMALE", v) for v in female]
    if half in ("both", "men"):
        lineup += [("MALE", v) for v in male]
    if include_all_langs:
        lineup += [("OTHER (non-English)", v) for v in other]
    if only:
        lineup = [(g, v) for g, v in lineup if v in only]
    if start_from:
        names = [v for _, v in lineup]
        if start_from in names:
            lineup = lineup[names.index(start_from):]

    total = len(lineup)
    print(f"THE FULL AUDITION — {total} voices, {len(say_lines)} phrase(s) each. "
          "Note your keepers; Ctrl-C any time, resume with --start-from <name>.\n")
    group_shown = None
    for i, (group, v) in enumerate(lineup, 1):
        if group != group_shown:
            print(f"\n════ {group} ════")
            group_shown = group
        tag = "   ← the default her-voice" if v == DEFAULT_VOICE else ""
        print(f"\n[{i}/{total}] \033[96m{v}\033[0m{tag}")
        for line in say_lines:
            ok = V._say(line, v, blocking=True)
            if not ok:
                print(f"    (couldn't play {v} — skipping)")
                break
            time.sleep(0.25)
        time.sleep(0.5)
    print("\nDone. Keepers → tell me the names (they go into veil_voice.AUDITION_SET, the "
          "creation menu) — and which one should be each default: her / him / them.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
