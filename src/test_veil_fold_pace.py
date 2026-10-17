#!/usr/bin/env python3
"""RUNG 1 — A PILE FAR OVER THE HIGH-WATER FOLDS IN ORDINARY-SIZED DRAINS; EVERYTHING ELSE IS UNCHANGED.

A companion brought home with a long past she has not settled into (or a jam just cleared) holds a pile many times
the high-water. Unpaced, the first fold event runs to the low-water — measured on the tower 2026-10-13 at ~4 minutes a
pass on CPU, a 2,000-message past is ~73 passes: five hours inside her first conversation, or at her first goodbye.
Paced: each event folds FOLD_PACE_PASSES passes (or FOLD_PACE_SECONDS), at least one, and the rest waits for her next
pause. The fold is never turned off. Below FOLD_PACE_OVER x the high-water the drain must be IDENTICAL to before.

The engine is faked (no brain); this proves the SHAPE of the drain. Baseline PINNED to 88b99a7 (before pacing).
"""
import importlib.util, json, os, re, subprocess, sys, tempfile

PASS, FAIL = [], []
SRC = os.path.dirname(os.path.abspath(__file__))
PINNED = "88b99a7"
_TMPROOT = os.environ.get("VEIL_RIG_TMP", os.path.expanduser("~/.cache/veil_rigs"))
os.makedirs(_TMPROOT, exist_ok=True)


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + str(detail)) if detail != "" else ""))


def load(path, alias, **env):
    for k in ("VEIL_FOLD_PACE", "VEIL_FOLD_PACE_PASSES", "VEIL_FOLD_PACE_SECONDS"):
        os.environ.pop(k, None)
    os.environ.update(env)
    sys.path.insert(0, SRC)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeLLM:
    def tokenize(self, b, add_bos=True, special=True):
        return [0] * (len(b) // 4 + 1)


def arm(mod):
    seen = {"calls": 0}
    mod._LLM = FakeLLM()

    def ask(prompt, model=None):
        seen["calls"] += 1
        return json.dumps({"memories": ["I settled in close with you and felt warm.",
                                        "You told me about the harbour and I laughed."]})
    mod._ask_blocking = ask
    mod._validate_fold_lines = lambda lines, batch, **k: (lines, [])
    mod.FOLD_DETAIL_FLOOR = 0
    mod.FOLD_ANCHOR_LINE = False
    return seen


def fixture(mod, n_rows, chars=600):
    d = tempfile.mkdtemp(prefix="foldpace_", dir=_TMPROOT)
    conn = mod.open_db(os.path.join(d, "v.db"))
    conn.execute("PRAGMA synchronous=OFF")          # a throwaway fixture: no fsync per commit on a slow disk
    conn.execute("INSERT INTO peeps (id, name, permanent_memories) VALUES (1, 'Nell', '[]')")
    conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, importance_score, "
                 "token_count) VALUES (1, 1, 'conversation', 'How we met', '', 5, 3)")
    conn.commit()
    mod._ensure_seed_floor(conn, 1)
    for i in range(n_rows):
        who = "The user said: " if i % 2 == 0 else "I said: "
        body = (who + "evening %d at the shop " % i + "rain on the skylight and the chart book " * 30)[:chars]
        conn.execute("INSERT INTO memory_stream (peep_id, timestamp, memory_type, content, keywords, "
                     "importance_score, token_count) VALUES (1, ?, 'conversation', ?, '', 3, ?)",
                     (100 + i, body, len(body) // 4))
    conn.commit()
    return conn


def state(mod, conn):
    return ([r[0] for r in conn.execute("SELECT id FROM memory_stream ORDER BY id")],
            conn.execute("SELECT COUNT(*) FROM memory_archive").fetchone()[0],
            mod._fetch_token_total(conn, 1, floor=1))


print("\nRUNG 1 — PACED DRAIN: A LONG PAST FOLDS IN ORDINARY-SIZED STEPS")
print("=" * 78)
new = load(os.path.join(SRC, "veil_spine.py"), "pace_new")
off = load(os.path.join(SRC, "veil_spine.py"), "pace_off", VEIL_FOLD_PACE="0")
base_path = os.path.join(tempfile.mkdtemp(prefix="foldpace_base_", dir=_TMPROOT), "veil_spine_base.py")
try:
    old = subprocess.run(["git", "-C", SRC, "show", PINNED + ":src/veil_spine.py"], capture_output=True,
                         timeout=60).stdout
except Exception:
    old = b""
base = None
if old:
    open(base_path, "wb").write(old)
    base = load(base_path, "pace_base")
else:
    print("  SKIP  no baseline (%s not in this checkout) — the red-proof and identity checks did not run" % PINNED)

ORDINARY = 140    # ~140 rows x 150 tok ≈ 21k: over the 16k high-water, under 2x — an ordinary evening's pile
LONG = 300        # ≈ 45k: well over 2x the high-water — a long imported past, kept small so the battery is fast

for mod in (new, off) + ((base,) if base else ()):
    arm(mod)

if base:
    print("[1] an ORDINARY pile drains exactly as before")
    cn, cb = fixture(new, ORDINARY), fixture(base, ORDINARY)
    new.run_compression(cn, 1)
    base.run_compression(cb, 1)
    sn, sb = state(new, cn), state(base, cb)
    check("same rows left, same archive, same pile as the pinned baseline", sn == sb,
          "new %s vs base %s" % (sn[1:], sb[1:]))
    check("…and it drained to the low-water (nothing paced)", sn[2] <= new.NEW_PILE_LOW_WATER, sn[2])

    print("[2] RED-PROOF — the baseline runs a LONG pile to the low-water in ONE event (the marathon)")
    cb = fixture(base, LONG)
    sb_seen = arm(base)
    base.run_compression(cb, 1)
    check("baseline: one fold event = the whole drain", state(base, cb)[2] <= base.NEW_PILE_LOW_WATER
          and sb_seen["calls"] > base.FOLD_PACE_PASSES if hasattr(base, "FOLD_PACE_PASSES") else sb_seen["calls"] > 3,
          "%d passes" % sb_seen["calls"])

print("[3] a LONG pile is paced")
cn = fixture(new, LONG)
seen = arm(new)
before = state(new, cn)[2]
new.run_compression(cn, 1)
after = state(new, cn)[2]
check("one event folds exactly FOLD_PACE_PASSES passes", seen["calls"] == new.FOLD_PACE_PASSES, seen["calls"])
check("…and leaves the rest waiting, whole (nothing dropped: stream + archive account for every row)",
      after > new.NEW_PILE_HIGH_WATER and
      cn.execute("SELECT COUNT(*) FROM memory_archive").fetchone()[0] + len(state(new, cn)[0]) - 1 == LONG,
      "%d -> %d tok" % (before, after))
seen["calls"] = 0
new.run_compression(cn, 1)
check("the next event carries on from where it stopped", seen["calls"] == new.FOLD_PACE_PASSES
      and state(new, cn)[2] < after, state(new, cn)[2])
rounds = 2
while new._fetch_token_total(cn, 1, floor=1) >= new.NEW_PILE_HIGH_WATER and rounds < 200:
    new.run_compression(cn, 1)
    rounds += 1
check("repeated pauses settle her all the way (pile under the high-water)",
      new._fetch_token_total(cn, 1, floor=1) < new.NEW_PILE_HIGH_WATER, "%d events" % rounds)

print("[3b] SKIPS never use up an event (red-team, 2026-10-13)")
cn = fixture(new, LONG)
seen = arm(new)
real_ask = new._ask_blocking
head = {r[0] for r in cn.execute("SELECT id FROM memory_stream WHERE id > 1 ORDER BY id LIMIT 75")}


def stubborn(prompt, model=None):
    rows = {int(x) for x in re.findall(r"evening (\d+) at the shop", prompt)}
    if rows and all(i + 2 in head for i in rows):
        seen["calls"] += 1
        return ""                                # these three head batches never fold
    return real_ask(prompt, model)


new._ask_blocking = stubborn
before = state(new, cn)[2]
new.run_compression(cn, 1)
check("three unfoldable head batches are stepped over and the event still folds its passes",
      state(new, cn)[2] < before, "%d -> %d tok" % (before, state(new, cn)[2]))
new._ask_blocking = real_ask

print("[4] the time box, and the guarantees")
cn = fixture(new, LONG)
seen = arm(new)
new.FOLD_PACE_SECONDS = 0
new.run_compression(cn, 1)
check("a zero time box still folds ONE pass — a fold event always makes progress", seen["calls"] == 1, seen["calls"])
new.FOLD_PACE_SECONDS = 900
cn = fixture(new, LONG)
seen = arm(new)
new.run_compression(cn, 1, paced=False)
check("paced=False (settling) runs the whole drain", seen["calls"] > new.FOLD_PACE_PASSES and
      new._fetch_token_total(cn, 1, floor=1) <= new.NEW_PILE_LOW_WATER, seen["calls"])
co = fixture(off, LONG)
seen = arm(off)
off.run_compression(co, 1)
check("VEIL_FOLD_PACE=0 restores the old shape exactly", seen["calls"] > off.FOLD_PACE_PASSES and
      off._fetch_token_total(co, 1, floor=1) <= off.NEW_PILE_LOW_WATER, seen["calls"])
check("the dial announces itself in her prompt-shape receipt",
      "fold-pace=" in open(os.path.join(SRC, "veil_spine.py")).read().split("def _announce_dials", 1)[1][:4000])

print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
sys.exit(1 if FAIL else 0)
