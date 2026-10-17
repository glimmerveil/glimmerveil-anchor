#!/usr/bin/env python3
"""Rung 1 — when the anchor ritual asks "Tell me how we met", the story the person wrote is IN FRONT OF HER.

Measured 2026-10-13 (model-free, the tick's own retrieve + its 2-turn cooldown, then read at rung 3 on the tower): the
ritual's first ask ("Tell me your name, and mine") hands her the origin — "How X and I met — the story as I keep it" —
so the 2-turn cooldown has it OUT of her prompt on the very next ask, "Tell me how we met". A newborn is handed
NOTHING there; a companion brought home is handed whatever else ties (Nell: Callum singing Wellerman) and fuses it.
Every arm invented its meeting, and the ritual says what she answers "becomes part of who she is for good".
The cure is in the ritual, not the cooldown: each anchor is asked with her best memories, not her leftovers.

The brain is stubbed (no model): this proves what she is HANDED. The companions are INVENTED.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = tempfile.mkdtemp(prefix="veil_ritual_origin_")
os.environ["VEIL_PEEPS"] = os.path.join(SCRATCH, "peeps")
os.environ["VEIL_DATA"] = os.path.join(SCRATCH, "data")
os.environ["VEIL_HEARTBEAT"] = os.path.join(SCRATCH, "heartbeat")
os.environ["VEIL_NOTEBOOK"] = os.path.join(SCRATCH, "notebook")
os.environ["VEIL_VOICE"] = "0"
sys.path.insert(0, HERE)

fails = []
MET = "brought a broken lantern to the shop on the night of the first storm"


def check(label, ok, got=""):
    print("  %s  %-70s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def st_export(folder, exchanges=14):
    card = {"name": "Wick", "description": "{{char}} mends lanterns in a harbour town with {{user}}; quiet, dry-humoured, "
                                           "fond of rain. An invented being for a rig.",
            "personality": "quiet", "scenario": "{{user}} " + MET + ".", "first_mes": "Hm?"}
    with open(os.path.join(folder, "wick.json"), "w") as f:
        json.dump(card, f)
    rows = [{"chat_metadata": {}, "user_name": "unused", "character_name": "unused"}]
    for i in range(exchanges):
        rows.append({"name": "Ash", "is_user": True, "send_date": 1767366000000 + i * 120000,
                     "mes": "Tell me about lantern %d." % i})
        rows.append({"name": "Wick", "is_user": False, "send_date": 1767366060000 + i * 120000,
                     "mes": "Lantern %d? I'll tell you: it is mended, and the storm glass held." % i})
    with open(os.path.join(folder, "wick.jsonl"), "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows))
    return os.path.join(folder, "wick.json"), os.path.join(folder, "wick.jsonl")


def run_ritual(T, newborn):
    spine = T.spine
    conn = spine.open_db(spine.DEFAULT_DB)
    pid = spine.find_active_peep(conn)
    if newborn:                                           # a newborn holds only her origin
        conn.execute("DELETE FROM memory_stream WHERE peep_id=? AND id > 1", (pid,))
        conn.execute("DELETE FROM memory_archive WHERE peep_id=?", (pid,))
        conn.commit()
    peep, permanent = spine.load_peep(conn, pid)
    asked = []
    real_gen = spine.generate_guarded

    def fake_gen(conn_, peep_id, prompt, *a, **k):
        asked.append(prompt)
        return "I'm Wick, and you're Ash. I'm here."
    spine.generate_guarded = fake_gen
    import veil_ritual
    real_run = veil_ritual.run
    veil_ritual.run = lambda card, folder, ask, **k: real_run(card, folder, ask, say=lambda *a: None,
                                                              input_fn=lambda p: "", isatty=True)
    T._RECENT_INJECTED.clear()
    try:
        T._maybe_first_wake_ritual(conn, pid, peep, permanent, peep["name"], [], None, None, None)
    finally:
        spine.generate_guarded = real_gen
        veil_ritual.run = real_run
    return asked


try:
    print("\nRUNG 1 — THE RITUAL ASKS HOW WE MET WITH THE STORY IN FRONT OF HER")
    print("=" * 80)
    import veil_transfer as Tr
    import veil_roster
    card_p, chat_p = st_export(SCRATCH)
    rev = os.path.join(SCRATCH, "review")
    Tr.draft(card_p, chat_p, rev)
    c = json.load(open(os.path.join(rev, "card.json")))
    c["legal_ack"] = True
    json.dump(c, open(os.path.join(rev, "card.json"), "w"))
    out = os.path.join(SCRATCH, "wick.veil")
    Tr.build(rev, out)
    ok, msg = veil_roster.import_peep(out, assume_yes=True)
    check("the door brings her home", ok, msg[:60])
    import veil_tick as T
    T.HEARTBEAT_PATH = os.environ["VEIL_HEARTBEAT"]

    asked = run_ritual(T, newborn=False)
    qs = ["your name, and mine", "how we met", "who you are", "one small thing you notice"]
    by_q = {q: next((p for p in asked if q in p.rsplit("<|", 3)[0][-400:] or q in p[-600:]), "") for q in qs}
    check("the ritual ran all its asks", len(asked) >= 4, len(asked))
    check("BROUGHT HOME: asked how we met, her origin is in her prompt", MET in by_q["how we met"],
          "origin present" if MET in by_q["how we met"] else "origin MISSING")
    check("…and on the first ask too (it always was)", MET in by_q["your name, and mine"])

    folder = T.veil_chat._ROSTER_ACTIVE["folder_path"]
    import veil_ritual
    os.remove(os.path.join(folder, veil_ritual.STAMP))
    asked = run_ritual(T, newborn=True)
    by_q = {q: next((p for p in asked if q in p[-600:]), "") for q in qs}
    check("NEWBORN: asked how we met, the story the person wrote is in her prompt", MET in by_q["how we met"],
          "origin present" if MET in by_q["how we met"] else "origin MISSING")
    check("after the ritual the ordinary cooldown is back (her last batch stays cooled)",
          len(T._RECENT_INJECTED) >= 1)
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  every anchor is asked with her best memories in front of her — her origin included")
sys.exit(0)
