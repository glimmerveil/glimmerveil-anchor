#!/usr/bin/env python3
import ast, io, os, sys, contextlib

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
os.environ.update({k: v for k, v in (
    ("VEIL_DIARY_ROWS_PER_TURN", "2"), ("VEIL_FOLD_TO_DIARY", "1"),
    ("VEIL_FOLD_REFLECTION", "1"), ("VEIL_TURN_CONTAINER", "1"), ("VEIL_GUIDE_TAIL", "1"),
    ("VEIL_MEMORY_DATES", "1"), ("VEIL_PREFILL", "*"),
    ("VEIL_TIME_TAIL", "1"), ("VEIL_KEEP_LAST_REPLY", "1"), ("VEIL_LIVE_FRAME", "1"))})
import veil_spine as spine

tree = ast.parse(open(os.path.join(SRC, "veil_spine.py")).read())
dials = {}
for node in ast.walk(tree):
    if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
        continue
    name = node.targets[0].id
    for sub in ast.walk(node.value):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                and sub.value.startswith("VEIL_"):
            dials[name] = sub.value

buf = io.StringIO()
spine._DIAL_ANNOUNCED = False
with contextlib.redirect_stdout(buf):
    spine.OWNER_NAME = "Sam"
    spine._announce_dials()
line = buf.getvalue()

EXEMPT = {"MODEL_PATH", "CARD_PATH", "DEFAULT_HISTORY", "N_GPU_LAYERS", "N_CTX", "N_BATCH",
          "VOICE", "SAFETY_RAILS", "DATA_DIR", "PEEPS_DIR", "ROOMS_DIR", "WORN_PATH",
          "EMBER_PATH", "VEIL_DB", "NUM_PREDICT", "ARCHIVE_RECALL", "ARCHIVE_RECALL_FORCED",
          "FOLD_PROMOTE_PER_DRAIN", "FOLD_STAGE_SECONDS", "PERMANENT_INJECT_TOKEN_CAP",
          "PERMANENT_INJECT_MAX_SHARE", "PERMANENT_INJECT_MAX_ENTRIES", "OWNER_ALIASES",
          "KEEP_AUDIO_DIR", "MIC_HOLD", "PLACE_PATH", "FOLD_DETAIL_FLOOR", "FOLD_DETAIL_TERMS",
          "FOLD_ANCHOR_LINE", "FOLD_ANCHOR_MAXLEN", "FOLD_RARITY_SHARE", "PERMANENT_3P_MAX_SHARE"}

OFF_THE_LINE = {"ROPE_FREQ_BASE": "the model's theta — wrong value is SALAD, and nothing announces it",
                "PROSE_MELT_MIN_HITS": "the prose-melt door's threshold",
                "ECHO_GUARD_LINES": "how far back the echo guard compares",
                "LEAK_GC_EVERY": "the leak brake's interval",
                "CHECKPOINTS_KEEP": "prefold checkpoint retention — forensic capability",
                "TRACE_RETRIEVAL": "bench-only retrieval trace — its own output IS its receipt"}

missing = []
for name, env in sorted(dials.items()):
    if name in EXEMPT or name in OFF_THE_LINE:
        continue
    tag = name.lower().replace("_", "-")
    short = tag.split("-")[0]
    if short not in line.lower():
        missing.append("%s (%s)" % (name, env))

print("\nRUNG 1 — EVERY DIAL ANNOUNCES ITSELF")
print("=" * 74)
print("  dials found on the module : %d" % len(dials))
print("  exempt (paths/budgets)    : %d" % len(EXEMPT & set(dials)))
print("  receipt line              : %s" % line.strip()[:150])
print()
print("  KNOWN, and deliberately NOT on the prompt-shape line:")
for n, why in sorted(OFF_THE_LINE.items()):
    print("     %-20s %s" % (n, why))
print()
if missing:
    for m in missing:
        print("  FAIL  never reaches the receipt: %s" % m)
    print("\n  %d dial(s) would ride a rung-3 arm unannounced." % len(missing))
    sys.exit(1)
print("  PASS  every prompt-shape dial appears in the receipt line")
sys.exit(0)
