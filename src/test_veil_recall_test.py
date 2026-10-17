#!/usr/bin/env python3
"""RUNG 1 — DID SHE COME BACK? The recall test's own logic: evenings, which ones it asks about, what counts as
remembering, and that it WARNS (never refuses). Her brain is not loaded here — the asking is proven at rung 3.
The companion is INVENTED."""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_recall_test as R

fails = []


def check(label, ok, got=""):
    print("  %s  %-70s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


SCRATCH = tempfile.mkdtemp(prefix="veil_recall_rig_")
DAY = 86400
EVENINGS = [
    ["The atlas came back with green endbands.", "I mended the atlas spine and sewed green endbands."],
    ["A duck walked in out of the storm.", "I named the duck Admiral; Pickles glared from the bookcase."],
    ["Callum took me out on The Persistent.", "You were sick four times on The Persistent, Captain."],
    ["The shipyard let thirty of us go.", "Stay tonight by the stove; the shipyard does not get the last word."],
    ["Happy birthday — a green fountain pen.", "A green fountain pen! I'll write every docket with it."],
    ["Why does it smell of smoke?", "I burnt the toast reading; the alarm sent Pickles under the plan chest."],
    ["Orkney in the spring, to see the stones.", "Orkney and the standing stones — I'm writing it in green ink."],
]
msgs, t, o = [], 1_760_000_000, 0
for d, (his, hers) in enumerate(EVENINGS):
    for k in range(3):
        o += 1
        msgs.append({"who": "you", "text": his + " Pickles says hello.", "ts": t + d * DAY + k * 120, "ord": o})
        o += 1
        msgs.append({"who": "her", "text": hers + " The rain is on the skylight.", "ts": t + d * DAY + k * 120 + 60,
                     "ord": o})
review = os.path.join(SCRATCH, "review")
os.makedirs(review)
json.dump({"her": "Nell", "you": "Theo", "messages": msgs}, open(os.path.join(review, "chat.json"), "w"))
json.dump({"her_name": "Nell", "your_name": "Theo"}, open(os.path.join(review, "card.json"), "w"))

try:
    print("\nRUNG 1 — THE RECALL TEST'S OWN LOGIC")
    print("=" * 80)
    evs = R.evenings(msgs)
    check("a gap of more than three hours starts a new evening", len(evs) == 7, len(evs))
    picks = R.pick_evenings(evs)
    check("never her first evening (her origin) nor her last (it would flatter her)",
          0 not in picks and 6 not in picks and len(picks) == 3, picks)
    keys, furniture = R.answer_keys(evs, "Nell", "Theo")
    check("what is in every evening is furniture, never a key", "pickles" in furniture and "skylight" in furniture
          and not any("pickles" in ([c] + k) for c, k in keys), furniture)
    check("the two of them are never a key", not any(n in ([c] + k) for c, k in keys for n in ("nell", "theo")))
    # rung 3 on the tower, 2026-10-13: on a short real-shaped chat nearly every word is said once, and the old filter
    # let them all in and broke the tie alphabetically — the keys came out "used, squeezes, somewhere, sofa's".
    short = [[(0, {"who": "you", "text": "Morning. The ferry was late again."}),
              (1, {"who": "her", "text": "*shrugs* Then the ferry can wait for the kettle."})],
             [(2, {"who": "you", "text": "The lighthouse keeper waved at me."}),
              (3, {"who": "her", "text": "*squeezes your hand* Old Moira? She waves at everyone."})],
             [(4, {"who": "you", "text": "Snowdrops by the wall."}), (5, {"who": "her", "text": "Snowdrops already."})],
             [(6, {"who": "you", "text": "Mackerel for tea."}), (7, {"who": "her", "text": "Mackerel again."})]]
    k2, _ = R.answer_keys(short, "Nell", "Theo")
    flat = [w for c, ks in k2 for w in ([c] if c else []) + ks]
    check("a word said ONCE, by one of them, is never a key (said twice, by both, or a name is)",
          "ferry" in flat and "moira" in flat and not {"shrugs", "squeezes", "kettle", "lighthouse"} & set(flat),
          k2)
    check("a possessive is the word it belongs to", R._words("the sofa's arm and Callum's boat") ==
          ["sofa", "callum", "boat"], R._words("the sofa's arm and Callum's boat"))
    check("an evening with nothing to ask about is never picked",
          R.pick_evenings(evs, {2, 4}) == [2, 4], R.pick_evenings(evs, {2, 4}))
    ps, _ = R.probes(review)
    qs = [p["question"] for p in ps]
    check("each probe points at its evening by what made it THAT evening",
          any("shipyard" in (p["cue"], *p["key"]) or "stove" in (p["cue"], *p["key"]) for p in ps), qs)
    check("a name is asked as a name, a thing as a thing",
          all(q.startswith("Do you remember ") and q.endswith("?") for q in qs), qs)
    p = next(p for p in ps if "shipyard" in [p["cue"]] + p["key"] or "stove" in [p["cue"]] + p["key"])
    good = R.score("Of course — the night the shipyard let you go, we sat by the stove and I made you stay.", p)
    bad = R.score("I remember the duck! Admiral, standing in the doorway.", p)
    check("remembering that evening counts", len(good["named"]) >= 1, good)
    check("naming ANOTHER evening's things is drift, not recall", not bad["named"] and bad["other_evenings_named"],
          bad)
    results = [{"probe": q, "answer": "I don't know.", "score": R.score("I don't know.", q)} for q in ps]
    text = R.report(results, furniture)
    check("a thin recall WARNS — and says it never refuses", "WARNING" in text and "never refuses" in text)
    results = [{"probe": q, "answer": " ".join([q["cue"]] + q["key"]), "score": R.score(" ".join([q["cue"]] + q["key"]), q)}
               for q in ps]
    text = R.report(results, furniture)
    check("a full recall does not warn, and still asks you to read her words",
          "WARNING" not in text and "read" in text.lower())
    check("her answers are printed WORD FOR WORD in the report", all(r["answer"] in text for r in results))
    check("the test never touches the network", "import socket" not in open(R.__file__).read()
          and "urllib" not in open(R.__file__).read())
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  the recall test asks about real evenings, counts honestly, and warns without refusing")
sys.exit(0)
