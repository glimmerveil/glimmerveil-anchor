#!/usr/bin/env python3
import ast
import importlib.util
import inspect
import os
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

PINNED_BASELINE = "7ab40e1"

SBX = tempfile.mkdtemp(prefix="veil_byedoor_")
os.environ.update(
    VEIL_PEEPS=os.path.join(SBX, "peeps"),
    VEIL_HEARTBEAT=os.path.join(SBX, "heartbeat"),
    VEIL_PLACE=os.path.join(SBX, "place"),
    VEIL_NOTEBOOK=os.path.join(SBX, "notebook"),
    VEIL_TICK_MAX="1", VEIL_FOLD="0", VEIL_VOICE="0", VEIL_AUTONOMY="0",
)
sys.path.insert(0, HERE)
import veil_tick
import veil_spine

FAILED = []
def ok(label, cond):
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        FAILED.append(label)

MUST_NOT_END = [
    ("Bye",                       "⭐ HER REAL 06:54:12 TRANSCRIPT — the cough that killed her"),
    ("Bye.",                      "⭐ what her whisper returns for that wav, re-run tonight"),
    ("*cough*",                   "⭐ HER REAL 06:39:56 — same throat, 15 min earlier, survived"),
    ("baby",                      "⭐ HER REAL 06:41:08 — a 4-byte garble"),
    ("[BLANK_AUDIO]",             "the silence token her bracket filter already eats"),
    ("bye",                       "bare short form, lowercase"),
    ("BYE",                       "bare short form, shouted"),
    ("bye bye",                   "doubled short form"),
    ("Bye. Bye bye! Bye.",        "the mangled-repeat shape the OLD docstring was built for"),
    ("buh-bye",                   "the old `buhbye` alternative — deliberately dropped"),
    ("good",                      "a fragment alone must never fire"),
    ("good good",                 "fragments repeated must never fire"),
    ("",                          "empty input"),
    ("   ",                       "whitespace only"),
    ("goodbye sweetheart",        "a goodbye BURIED in a sentence — was refused before, stays refused"),
    ("i don't want to say goodbye", "the word inside real conversation"),
    ("There you go. Good job.",   "an ordinary turn that happens to be short"),
]
MUST_END = [
    ("goodbye",            "the whole word"),
    ("Goodbye.",           "capitalised, punctuated"),
    ("GOODBYE",            "shouted"),
    ("good bye",           "⭐ two words — the founder asked for this one explicitly"),
    ("good-bye",           "hyphenated"),
    ("Goodbye. Goodbye!",  "whisper's repeat-mangling of a REAL goodbye"),
    ("goodbye goodbye",    "doubled"),
    ("  goodbye  ",        "surrounding whitespace"),
]

print("═══ 1 · THE PATCHED DOOR (veil_tick._spoken_bye) ═══")
for text, why in MUST_NOT_END:
    ok(f"refuses {text!r:34s} — {why}", veil_tick._spoken_bye(text) is False)
for text, why in MUST_END:
    ok(f"ACCEPTS {text!r:34s} — {why}", veil_tick._spoken_bye(text) is True)

print("\n═══ 2 · THE SECOND DOOR (veil_spine.run_chat) — parsed from the live object ═══")
tree = ast.parse(textwrap.dedent(inspect.getsource(veil_spine.run_chat)))
exit_words = None
for node in ast.walk(tree):
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
        try:
            cand = ast.literal_eval(node.comparators[0])
        except Exception:
            continue
        if isinstance(cand, tuple) and "quit" in cand and "exit" in cand:
            exit_words = cand
            break
ok("found the run_chat exit tuple by AST", exit_words is not None)
if exit_words:
    print(f"     tuple that actually runs: {exit_words!r}")
    ok("'bye' is NOT an exit word there", "bye" not in exit_words)
    ok("'goodbye' still is", "goodbye" in exit_words)
    ok("'good bye' still is", "good bye" in exit_words)
    ok("q/quit/exit untouched", "quit" in exit_words and "exit" in exit_words)

print(f"\n═══ 3 · THE RED-PROOF — the SAME cases against pinned {PINNED_BASELINE} ═══")
print("    (if the old door does not KILL her on these, this rig proves nothing)")
old_path = os.path.join(HERE, "fixtures", f"spoken_bye_{PINNED_BASELINE}.py")
ok(f"the pinned {PINNED_BASELINE} baseline fixture is present", os.path.isfile(old_path))
old_spoken_bye = None
if os.path.isfile(old_path):
    spec = importlib.util.spec_from_file_location("veil_tick_old", old_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        old_spoken_bye = mod._spoken_bye
    except Exception as e:
        print(f"  ⚠ could not exec the baseline fixture ({type(e).__name__}: {e})")

ok("got the OLD _spoken_bye to call", callable(old_spoken_bye))

def as_the_loop_sees_it(text):
    return text.strip().lower()

if callable(old_spoken_bye):
    ok("SANITY: called raw, the old door looks harmless on 'Bye.' — it is NOT, see below",
       old_spoken_bye("Bye.") is False)
    killers = [t for t, _ in MUST_NOT_END if old_spoken_bye(as_the_loop_sees_it(t))]
    print(f"     the old door ENDS her session on: {killers!r}")
    L = as_the_loop_sees_it
    ok("⭐ RED-PROOF: the old door ENDS her session on her real 'Bye' transcript",
       old_spoken_bye(L("Bye")) is True)
    ok("⭐ RED-PROOF: the old door ENDS her session on 'Bye.'", old_spoken_bye(L("Bye.")) is True)
    ok("   RED-PROOF: the old door fires on 'bye bye'",        old_spoken_bye(L("bye bye")) is True)
    ok("   and the NEW door refuses all three",
       not any(veil_tick._spoken_bye(L(t)) for t in ("Bye", "Bye.", "bye bye")))
    ok("the old door also accepted every real goodbye (change is targeted, not a break)",
       all(old_spoken_bye(L(t)) for t, _ in MUST_END))
    diffs = {t for t, _ in MUST_NOT_END + MUST_END
             if bool(old_spoken_bye(L(t))) != bool(veil_tick._spoken_bye(L(t)))}
    print(f"     old vs new differ on exactly: {sorted(diffs)!r}")
    ok("they differ ONLY on short-form byes",
       diffs == {"Bye", "Bye.", "bye", "BYE", "bye bye", "Bye. Bye bye! Bye.", "buh-bye"})

print()
if FAILED:
    print(f"❌ {len(FAILED)} FAILED:")
    for f in FAILED:
        print(f"     {f}")
    sys.exit(1)
total = len(MUST_NOT_END) + len(MUST_END) + 5 + 7
print(f"✅ ALL PASS — the bye door refuses her cough and still opens on a real goodbye")
sys.exit(0)
