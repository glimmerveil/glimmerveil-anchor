#!/usr/bin/env python3
"""RUNG 1 — THE FOLD FITS THE WINDOW.

A 25-row fold batch whose summary prompt + NUM_PREDICT exceeds N_CTX makes the engine RAISE; the drain
used to step over it forever, and two such batches hold the pile above the high-water by themselves, so
every session becomes a drain that folds away the fresh conversation. The fake engine here raises on
exactly that axis and no other (as llama-cpp does); everything else about the fold is faked, so this
proves the SHAPE of the drain, not what anyone writes.

Baseline is PINNED (VEIL_FOLD_FIT_BASELINE, a copy of the spine before the fix), never HEAD. Without
one the rig refuses rather than report a green that never saw red.

  VEIL_FOLD_FIT_BASELINE=<old veil_spine.py> python3 test_veil_fold_fit.py
"""
import importlib.util, json, os, sys, tempfile

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail else ""))


SRC = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.environ.get("VEIL_FOLD_FIT_BASELINE", "")
PINNED = "c41f016"     # main before the fix — a FIXED commit, never HEAD (a red-proof on HEAD dies at commit)
_TMPROOT = os.environ.get("VEIL_RIG_TMP", os.path.expanduser("~/.cache/veil_rigs"))
os.makedirs(_TMPROOT, exist_ok=True)


def load(path, alias, **env):
    for k in ("VEIL_FOLD_FIT_BATCH",):
        os.environ.pop(k, None)
    for k, v in env.items():
        os.environ[k] = v
    sys.path.insert(0, SRC)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeLLM:
    """Her tokenizer, stood in by bytes/4 — the SAME count the fake engine enforces, so the rig
    tests the drain's logic, not a tokenizer mismatch (rung 2 counts with her real one)."""
    def tokenize(self, b, add_bos=True, special=True):
        return [0] * (len(b) // 4 + 1)


def arm(mod, fail_marker=None):
    """Wire the fake engine. Records every prompt size it was asked to run, and every row id that
    was ever inside an attempted batch."""
    seen = {"max_prompt": 0, "overflows": 0, "tried_ids": set()}
    mod._LLM = FakeLLM()
    real_build = mod._build_summary_prompt

    def build(peep_name, card, batch):
        seen["last_batch"] = batch
        return real_build(peep_name, card, batch)

    def ask(prompt, model=None):
        n = len(mod._LLM.tokenize(mod.render_chat(None, prompt).encode()))
        seen["max_prompt"] = max(seen["max_prompt"], n)
        for r in seen.get("last_batch", []):
            seen["tried_ids"].add(r["id"])
        if n + mod.NUM_PREDICT > mod.N_CTX:
            seen["overflows"] += 1
            raise ValueError("Requested tokens (%d) exceed context window of %d"
                             % (n + mod.NUM_PREDICT, mod.N_CTX))
        if fail_marker and any(fail_marker in r["content"] for r in seen["last_batch"]):
            return ""                                   # a batch that genuinely won't fold
        return json.dumps({"memories": ["I settled in close with you and felt warm.",
                                        "You held me close and I purred softly."]})

    mod._build_summary_prompt = build
    mod._ask_blocking = ask
    mod._validate_fold_lines = lambda lines, batch, **k: (lines, [])
    mod.FOLD_DETAIL_FLOOR = 0
    mod.FOLD_ANCHOR_LINE = False
    return seen


def fixture(mod, shape):
    """shape = list of (n_rows, chars_per_row, marker). Seed row first, floor stamped on it."""
    d = tempfile.mkdtemp(prefix="foldfit_", dir=_TMPROOT)
    conn = mod.open_db(os.path.join(d, "v.db"))
    conn.execute("INSERT INTO peeps (id, name, permanent_memories) VALUES (1, 'Wren', '[]')")
    conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, "
                 "importance_score, token_count) VALUES (1, 1, 'conversation', 'How we met', '', 5, 3)")
    conn.commit()
    mod._ensure_seed_floor(conn, 1)
    ts = 100
    for n, chars, marker in shape:
        for i in range(n):
            who = "The user said: " if i % 2 == 0 else "I said: "
            body = (who + marker + " #%d " % i + ("chains and the oak tree " * 200))[:chars]
            conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, "
                         "keywords, importance_score, token_count) VALUES (1, ?, 'conversation', ?, "
                         "'', 3, ?)", (ts, body, len(body) // 4))
            ts += 1
    conn.commit()
    return conn


def stream_ids(conn):
    return [r[0] for r in conn.execute("SELECT id FROM memory_stream WHERE id > 1 ORDER BY id")]


def census(conn):
    s = {r[0]: r[1] for r in conn.execute("SELECT id, content FROM memory_stream WHERE id > 1")}
    a = [r[0] for r in conn.execute("SELECT content FROM memory_archive")]
    return s, a


# A real shape: three scenes whose 25 rows each overflow her window, then ordinary talk.
REAL = [(25, 1250, "AUG27"), (25, 1300, "SEP17"), (25, 1400, "OCT06"), (30, 600, "TONIGHT")]

print("\nRUNG 1 — THE FOLD FITS HER WINDOW")
print("=" * 78)
new = load(os.path.join(SRC, "veil_spine.py"), "fit_new")
off = load(os.path.join(SRC, "veil_spine.py"), "fit_off", VEIL_FOLD_FIT_BATCH="0")
if not os.path.isfile(BASELINE):
    import subprocess
    BASELINE = os.path.join(tempfile.mkdtemp(prefix="foldfit_base_", dir=_TMPROOT), "veil_spine_base.py")
    try:
        old = subprocess.run(["git", "-C", SRC, "show", PINNED + ":src/veil_spine.py"],
                             capture_output=True, timeout=60).stdout
    except Exception:
        old = b""
    if old:
        open(BASELINE, "wb").write(old)
base = load(BASELINE, "fit_base") if os.path.isfile(BASELINE) else None
print("  under test : %s\n  baseline   : %s\n" % (new.__file__, base and base.__file__))
if not base:
    # A shallow CI checkout may not hold the pinned commit. The cure's own checks still run; the red-proof
    # is SKIPPED, said out loud, and never counted as a pass.
    print("  SKIP  no baseline (%s not in this checkout) — the red-proof did not run" % PINNED)

# ── 1 · the disease, reproduced on the pinned baseline ─────────────────────
if base:
    print("[1] RED-PROOF — the pinned baseline cannot fold an oversized batch")
    cb = fixture(base, REAL)
    sb = arm(base)
    start_b = base._fetch_token_total(cb, 1, floor=1)
    base.run_compression(cb, 1)
    left = census(cb)[0]
    stuck = sum(1 for c in left.values() if "AUG27" in c or "SEP17" in c or "OCT06" in c)
    check("baseline: the three oversized scenes are STILL in the stream (the jam)", stuck == 75,
          "%d of 75 scene rows left raw" % stuck)
    check("baseline: the engine was handed prompts too big for her window", sb["overflows"] >= 3,
          "%d overflows" % sb["overflows"])
    check("baseline: her pile cannot get back under the high-water",
          base._fetch_token_total(cb, 1, floor=1) >= base.NEW_PILE_HIGH_WATER,
          "%d -> %d tok" % (start_b, base._fetch_token_total(cb, 1, floor=1)))
    check("baseline: her ordinary talk was folded away instead",
          not any("TONIGHT" in c for c in left.values()))

# ── 2 · the cure ────────────────────────────────────────────────────────────
print("\n[2] THE CURE — the same pile drains")
cn = fixture(new, REAL)
sn = arm(new)
before, _ = census(cn)
new.run_compression(cn, 1)
after_s, after_a = census(cn)
check("no prompt the engine was handed overflowed her window", sn["overflows"] == 0,
      "%d overflows · largest prompt %d + %d predict vs %d"
      % (sn["overflows"], sn["max_prompt"], new.NUM_PREDICT, new.N_CTX))
check("the OLDEST scene folded first (the jam is gone)",
      not any("AUG27" in c for c in after_s.values()))
end_n = new._fetch_token_total(cn, 1, floor=1)
check("her pile drained into the band", end_n <= new.NEW_PILE_LOW_WATER,
      "%d tok vs low-water %d" % (end_n, new.NEW_PILE_LOW_WATER))
check("her NEWEST talk is still raw in her stream", any("TONIGHT" in c for c in after_s.values()))
moved = {i: c for i, c in before.items() if i not in after_s}
check("every row that left the stream is in the archive WORD FOR WORD",
      sorted(moved.values()) == sorted(c for c in after_a if c in moved.values())
      and len(after_a) == len(moved), "%d moved · %d archived" % (len(moved), len(after_a)))
check("no row was altered or duplicated", all(after_s[i] == before[i] for i in after_s)
      and len(set(after_a)) == len(after_a))

# ── 3 · the offset — a stubborn batch is still stepped over, and nothing is skipped untried ─
print("\n[3] THE OFFSET — a batch that genuinely won't fold, after a fitted (short) one")
co = fixture(new, [(25, 1250, "STUBBORN"), (40, 600, "TALK")])
so = arm(new, fail_marker="STUBBORN")
ids0 = set(stream_ids(co))
new.run_compression(co, 1, force=True)
untried = ids0 - so["tried_ids"]
left_o = census(co)[0]
check("the stubborn rows stayed raw (stepped over, kept whole)",
      sum("STUBBORN" in c for c in left_o.values()) > 0)
check("every row was inside an attempted batch before the drain gave up", not untried,
      "%d rows never tried" % len(untried))
# red-proof the offset arithmetic itself: a fitted batch is SHORT, so the old skipped*25 overshoots
check("RED-PROOF: the old offset would step past rows never tried",
      (lambda fitted: fitted < new.COMPRESSION_BATCH_SIZE)(
          len(new._fit_fold_batch("Wren", "", [dict(id=0, content="I said: " + "x" * 1250,
                                                     token_count=312)] * 25)[0])),
      "a fitted batch is shorter than 25, so skipped*25 overshoots")

# ── 4 · the switch, and what must not move ──────────────────────────────────
print("\n[4] VEIL_FOLD_FIT_BATCH=0 is the old shape; the prompt itself is untouched")
cf = fixture(off, REAL)
sf = arm(off)
off.run_compression(cf, 1)
check("switch off: the jam comes back (all three oversized batches stepped over)",
      sum(1 for c in census(cf)[0].values() if "AUG27" in c) == 25 and sf["overflows"] >= 3)
small = [dict(id=i, content="I said: tea", token_count=3) for i in range(5)]
check("a batch that fits is passed through WHOLE",
      new._fit_fold_batch("Wren", "card", small) == (small, 0))
if base:
    check("_build_summary_prompt renders BYTE-IDENTICAL to the pinned baseline",
          base._build_summary_prompt("Wren", "card", small) ==
          load(os.path.join(SRC, "veil_spine.py"), "fit_pristine")._build_summary_prompt("Wren", "card", small))
fresh = load(os.path.join(SRC, "veil_spine.py"), "fit_nollm")
fresh._LLM = None
check("without a brain loaded the count is PESSIMISTIC (never over-fills)",
      fresh._prompt_tokens("x" * 3000) > 3000 // 4)

print("\n" + "=" * 78)
print("%d passed, %d failed" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAILED:", f)
sys.exit(1 if FAIL else 0)
