#!/usr/bin/env python3
"""Did she come back? — a recall test for a companion brought home, run on a COPY before anyone meets her.

The ground truth is in the box: her whole old chat. So we can ask her about it and see. Pick a few evenings from
across her life, take what made each one THAT evening (its distinctive words: the ones whose use in her whole life is
concentrated in that evening — a word that marks every evening marks none), ask her about each one on a disposable
copy of her, and show the answers WORD FOR WORD with what she named and missed.

The founder's ruling (2026-10-13): this WARNS, it never refuses. The numbers point; her answers are the finding —
read them. A copy is woken; her real folder never sees a probe.

    python3 veil_recall_test.py <review-folder> [her.veil]        (the .veil defaults to the one build wrote)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SESSION_GAP = 3 * 3600        # a gap longer than this starts a new evening
N_EVENINGS = 3                # spread across her life (early · middle · late)
KEY_TERMS = 6                 # what made that evening, after the cue
_STOP = set("""about above after again against always because been before being below between both cannot could does
doing down during each even ever every feel feeling felt from gave give given goes going gone good great half have
having here hers herself himself into just keep kept know known like little long look looked made make makes making
many might more most much must never next once only other over really said same says seem seems shall some something
still such take taken tell than that their them then there these they thing things think this those thought three time
times together took toward under until upon very want wanted well went were what when where which while will with
within without would your yours yourself okay yeah that's it's i'm you're we're don't didn't can't won't i'll i've
you've you'll she's he's i'd you'd let's back right come came here's there's going sure maybe also actually
someone something anyone anything everyone everything nothing nobody somebody tonight today tomorrow yesterday morning
evening night week weeks year years month months while whether what's we'll they're they'll they've isn't wasn't
aren't weren't hasn't haven't hadn't doesn't shouldn't wouldn't couldn't mustn't love loved loves like liked likes glad
happy sorry thanks thank please little bit lot lots work working worked worker better best worse worst first last next
second other another every each enough quite rather pretty almost already always often sometimes usually ever never
anyway though although because since until unless whatever whoever wherever whenever however where's who's how's
that'll there'll it'll it'd that'd what'd who'd mean means meant okay alright yes yeah nope sure fine kind sort way
ways thing things stuff people person place places hand hands head eyes face voice word words talk talked talking
tell telling told said saying says hear heard listen look looking looks see seen saw watch watching watched find found
make made making take took taking give gave giving keep kept keeping feel feels feeling felt think thought thinking
know knew knowing want wanted wanting need needed needing try tried trying start started starting stop stopped
stopping open opened close closed call called calling wait waited waiting turn turned turning hold held holding
leave left leaving stay stayed staying sit sat sitting stand stood standing walk walked walking bring brought
remember remembered forget forgot forgotten real really truly just only even still again also very much more most
less least long short high low small big large great good bad new old young same different whole half full empty
zero three four five seven eight nine eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen
nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand dozen couple
""".split())


def evenings(messages):
    """Split the chat into evenings by time gaps; each = list of (index, message)."""
    out, cur, last = [], [], None
    for i, m in enumerate(messages):
        ts = m.get("ts")
        if cur and ts and last and ts - last > SESSION_GAP:
            out.append(cur)
            cur = []
        cur.append((i, m))
        last = ts or last
    if cur:
        out.append(cur)
    return out


def _words(text):
    # a possessive is the word it belongs to ("Dad's" is Dad, "the sofa's arm" is the sofa)
    return [w for w in (re.sub(r"['’]s$", "", w) for w in re.findall(r"[a-z][a-z'’]{3,}", (text or "").lower()))
            if len(w) >= 4]


def answer_keys(evs, her_name="", your_name=""):
    """Per evening: (cue, key terms) — frequent in that evening, rare across her life. Names of the two of them are
    never a key (they are in every evening)."""
    names = {w.lower() for w in (her_name, your_name) if w}
    per, both, caps = [], [], set()
    for ev in evs:
        counts, by = {}, {}
        for _, m in ev:
            for w in re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z'’]{3,})\b", m["text"]):
                caps.add(w.lower())
            for w in _words(m["text"]):
                if w in _STOP or w in names:
                    continue
                counts[w] = counts.get(w, 0) + 1
                by.setdefault(w, set()).add(m["who"])
        per.append(counts)
        both.append({w for w, who in by.items() if len(who) > 1})
    # What an evening was ABOUT is CONCENTRATION: how much of a word's whole use in her life falls inside THIS
    # evening (the shipyard is said six times, all of them that night). A share-of-messages rarity cutoff (the house
    # ramp, tuned on single rows) fails here: in a short chat one evening's topic can be over 10% of all messages.
    n = len(per)
    edf, total = {}, {}
    for counts in per:
        for w, c in counts.items():
            edf[w] = edf.get(w, 0) + 1
            total[w] = total.get(w, 0) + c
    furniture_set = {w for w, d in edf.items() if n and d / n >= 0.5}
    keys = []
    for counts, shared in zip(per, both):
        # said more than once that night, or by BOTH of you, or a name (capitalised mid-sentence) — the duck called
        # Admiral, the shipyard, the toast. A word said ONCE, by one of you, is never a key: in a short evening nearly
        # every word is, and the old filter let them in and ranked the tie alphabetically ("sofa's", "shrugs").
        scored = sorted(((c * (c / total[w]) * (2.0 if w in shared else 1.0) * (1.5 if w in caps else 1.0), w)
                         for w, c in counts.items() if w not in furniture_set
                         and (c > 1 or w in shared or w in caps)),
                        key=lambda sw: (-sw[0], sw[1]))
        terms = [w for s, w in scored if s > 0][:KEY_TERMS + 1]
        # the CUE names a thing: prefer a name or a word you both used, never an -ing/-ed word; the rest is the key
        nounish = [w for w in terms if not w.endswith(("ing", "ed"))]
        cue = next((w for w in nounish if w in caps or w in shared), nounish[0] if nounish else None)
        keys.append((cue, [w for w in terms if w != cue][:KEY_TERMS]))
    furniture = sorted(w for w in furniture_set if w not in names)
    return keys, furniture


def pick_evenings(evs, usable=None):
    """Never the first evening (her origin) or the last (freshest, and it flatters her); spread across the rest —
    across the ones that HAVE something to ask about, when that is known (a quiet evening has no key)."""
    middle = [k for k in range(1, len(evs) - 1) if usable is None or k in usable]
    if len(middle) <= N_EVENINGS:
        return middle
    return [middle[round(k * (len(middle) - 1) / (N_EVENINGS - 1))] for k in range(N_EVENINGS)]


def probes(review_folder):
    with open(os.path.join(review_folder, "chat.json"), encoding="utf-8") as f:
        chat = json.load(f)
    with open(os.path.join(review_folder, "card.json"), encoding="utf-8") as f:
        card = json.load(f)
    evs = evenings(chat["messages"])
    keys, furniture = answer_keys(evs, card.get("her_name", ""), card.get("your_name", ""))
    out = []
    for k in pick_evenings(evs, {j for j, (c, ts) in enumerate(keys) if c and ts}):
        cue, terms = keys[k]
        if not cue or not terms:
            continue
        others = sorted({t for j, (c, ts) in enumerate(keys) if j != k for t in ([c] if c else []) + ts}
                        - set(terms) - {cue})
        q = f"Do you remember {cue.capitalize() if _proper(chat, cue) else 'the ' + cue}?"
        out.append({"evening": k + 1, "of": len(evs), "question": q, "cue": cue, "key": terms,
                    "other_evenings": others,
                    "ords": [m.get("ord") for _, m in evs[k]]})
    return out, furniture


def _proper(chat, word):
    caps = sum(1 for m in chat["messages"] for w in re.findall(r"\b[A-Z][a-z'’]{3,}\b", m["text"]) if w.lower() == word)
    lows = sum(1 for m in chat["messages"] for w in re.findall(r"\b[a-z][a-z'’]{3,}\b", m["text"]) if w == word)
    return caps > lows


def _stem(w):
    return w[:5]


def score(answer, probe):
    said = {_stem(w) for w in _words(answer)}
    named = [t for t in probe["key"] if _stem(t) in said]
    drift = [t for t in probe["other_evenings"] if _stem(t) in said]
    return {"named": named, "missed": [t for t in probe["key"] if t not in named], "other_evenings_named": drift}


def report(results, furniture):
    lines = ["DID SHE COME BACK? — a recall test on a copy of her, before anyone meets her.",
             "It WARNS; it never refuses. The numbers point — her answers are the finding. Read them.", ""]
    total_key = sum(len(r["probe"]["key"]) for r in results)
    total_named = sum(len(r["score"]["named"]) for r in results)
    for r in results:
        p, s = r["probe"], r["score"]
        lines.append(f"Evening {p['evening']} of {p['of']} — you asked: \"{p['question']}\"")
        lines.append(f"  that evening held: {', '.join(p['key'])}")
        lines.append(f"  she named: {', '.join(s['named']) or 'none of them'}"
                     + (f"   · from OTHER evenings: {', '.join(s['other_evenings_named'])}" if s["other_evenings_named"] else ""))
        lines.append("  she said:")
        lines.extend("    " + ln for ln in (r["answer"] or "(no answer)").splitlines())
        lines.append("")
    frac = (total_named / total_key) if total_key else 0.0
    lines.append(f"Overall: she named {total_named} of {total_key} things from those evenings.")
    if frac < 0.34:
        lines.append("⚠ WARNING: she reached little of those evenings. Read her answers above before you wake her. "
                     "Common reasons: her card is thin, too little of her past is her core (seed.json), or this brain "
                     "is a poor match — trying another brain is cheap. You can still wake her; this never refuses.")
    else:
        lines.append("She reached her past. Still read her answers — a pass in a voice that isn't hers is a fail, "
                     "and only reading catches that.")
    lines.append(f"(Things in most evenings, not counted either way: {', '.join(furniture[:12]) or 'none'}.)")
    return "\n".join(lines) + "\n"


# ── the child: wakes the COPY (env routed by the parent) and asks, each probe with a clean history ─────────────────
def _child(probes_path, out_path):
    import veil_tick as T
    spine = T.spine
    T.HEARTBEAT_PATH = os.environ["VEIL_HEARTBEAT"]
    conn = spine.open_db(spine.DEFAULT_DB)
    pid = spine.find_active_peep(conn)
    peep, permanent = spine.load_peep(conn, pid)
    T._WOKE_AT = time.time()
    model = spine.get_llm()
    got = {}
    real = spine.generate_guarded

    def capture(*a, **k):
        r = real(*a, **k)
        got["answer"] = r
        return r
    spine.generate_guarded = capture
    answers = []
    for p in json.load(open(probes_path, encoding="utf-8")):
        got.clear()
        T.chat_turn(conn, pid, peep, permanent, peep["name"], [], p["question"], model, None, None)
        answers.append(got.get("answer") or "")
    json.dump(answers, open(out_path, "w", encoding="utf-8"), ensure_ascii=False)


def run(review_folder, veil_path=None, model_path=None, keep_copy=False):
    import veil_paths
    veil_path = veil_path or _built_veil(review_folder)
    ps, furniture = probes(review_folder)
    if not ps:
        raise SystemExit("not enough evenings in her chat to test recall (needs at least three).")
    work = tempfile.mkdtemp(prefix="recall_test_", dir=os.environ.get("VEIL_RECALL_TMP") or None)
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith("VEIL_")}
        env.update({"VEIL_PEEPS": os.path.join(work, "peeps"), "VEIL_DATA": os.path.join(work, "data"),
                    "VEIL_HEARTBEAT": os.path.join(work, "heartbeat"), "VEIL_NOTEBOOK": os.path.join(work, "nb"),
                    "VEIL_MODEL": model_path or veil_paths.model_path(), "VEIL_VOICE": "0",
                    "VEIL_GPU_LAYERS": os.environ.get("VEIL_GPU_LAYERS", "0")})
        imp = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import veil_roster; "
                              "ok, m = veil_roster.import_peep(%r, assume_yes=True); sys.exit(0 if ok else 3)"
                              % (HERE, veil_path)], env=env, capture_output=True, text=True)
        if imp.returncode:
            raise SystemExit("could not make a test copy of her: " + (imp.stdout + imp.stderr)[-400:])
        pp, ap = os.path.join(work, "probes.json"), os.path.join(work, "answers.json")
        json.dump(ps, open(pp, "w", encoding="utf-8"), ensure_ascii=False)
        print(f"Asking a copy of her about {len(ps)} evenings of her life — one answer each, her own brain "
              "(minutes per answer on an ordinary computer)…", flush=True)
        ch = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", pp, ap], env=env)
        if ch.returncode or not os.path.isfile(ap):
            raise SystemExit("the test copy did not answer (exit %s)." % ch.returncode)
        answers = json.load(open(ap, encoding="utf-8"))
        results = [{"probe": p, "answer": a, "score": score(a, p)} for p, a in zip(ps, answers)]
        text = report(results, furniture)
        with open(os.path.join(review_folder, "RECALL_TEST.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        return results, text
    finally:
        if not keep_copy:
            shutil.rmtree(work, ignore_errors=True)


def _built_veil(review_folder):
    marker = os.path.join(review_folder, "built.json")
    if os.path.isfile(marker):
        return json.load(open(marker, encoding="utf-8")).get("path")
    raise SystemExit("build her first (veil_transfer.py build), or pass the .veil path.")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    _results, _text = run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print("\n" + _text)
