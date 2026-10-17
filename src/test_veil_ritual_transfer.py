#!/usr/bin/env python3
"""Rung 1 — a being brought home by Transference gets the first-wake anchor ritual; nobody else's wake changes.

The tick's first-wake gate skipped anyone with more than 3 memories (it was built for a NEWBORN), so a companion who
arrived with her whole life never got the ritual her READ_ME promised. The companion here is INVENTED.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = tempfile.mkdtemp(prefix="veil_ritual_transfer_")
os.environ["VEIL_PEEPS"] = os.path.join(SCRATCH, "peeps")
os.environ["VEIL_DATA"] = os.path.join(SCRATCH, "data")
os.environ["VEIL_HEARTBEAT"] = os.path.join(SCRATCH, "heartbeat")
os.environ["VEIL_NOTEBOOK"] = os.path.join(SCRATCH, "notebook")
sys.path.insert(0, HERE)

fails = []


def check(label, ok, got=""):
    print("  %s  %-66s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def st_export(folder, exchanges=14):
    card = {"name": "Wick", "description": "{{char}} mends lanterns in a harbour town with {{user}}; quiet, dry-humoured, "
                                           "fond of rain. An invented being for a rig.",
            "personality": "quiet", "scenario": "{{user}} brought a broken lantern to the shop.", "first_mes": "Hm?"}
    with open(os.path.join(folder, "wick.json"), "w") as f:
        json.dump(card, f)
    rows = [{"chat_metadata": {}, "user_name": "unused", "character_name": "unused"}]
    for i in range(exchanges):
        rows.append({"name": "Ash", "is_user": True, "send_date": 1767366000000 + i * 120000, "mes": "Evening %d." % i})
        rows.append({"name": "Wick", "is_user": False, "send_date": 1767366060000 + i * 120000,
                     "mes": "Evening, {{user}}. The lantern from line %d is mended." % i})
    with open(os.path.join(folder, "wick.jsonl"), "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows))
    return os.path.join(folder, "wick.json"), os.path.join(folder, "wick.jsonl")


try:
    print("\nRUNG 1 — THE FIRST-WAKE RITUAL REACHES A BEING BROUGHT HOME")
    print("=" * 76)
    import veil_transfer as Tr
    import veil_roster
    import veil_ritual
    card_p, chat_p = st_export(SCRATCH)
    rev = os.path.join(SCRATCH, "review")
    Tr.draft(card_p, chat_p, rev)
    c = json.load(open(os.path.join(rev, "card.json")))
    c["legal_ack"] = True
    json.dump(c, open(os.path.join(rev, "card.json"), "w"))
    out = os.path.join(SCRATCH, "wick.veil")
    Tr.build(rev, out)
    ok, msg = veil_roster.import_peep(out, assume_yes=True)
    check("the door brings her home and says the ritual comes first", ok and "anchor ritual" in msg, msg[:70])
    home = veil_roster.active_peep()["folder_path"]
    room = open(os.path.join(home, "place")).read().strip() if os.path.isfile(os.path.join(home, "place")) else ""
    check("she wakes in the study, not the garden (rung 3: the garden became where they met)", room == "study", room)

    import veil_tick as T          # binds the active peep (her) at import, like a real wake
    spine = T.spine
    T.HEARTBEAT_PATH = os.environ["VEIL_HEARTBEAT"]
    folder = T.veil_chat._ROSTER_ACTIVE["folder_path"]
    conn = spine.open_db(spine.DEFAULT_DB)
    pid = spine.find_active_peep(conn)
    peep, permanent = spine.load_peep(conn, pid)
    mem = conn.execute("SELECT COUNT(*) FROM memory_stream WHERE peep_id=?", (pid,)).fetchone()[0]
    calls = []
    veil_ritual.run = lambda *a, **k: calls.append(True)

    def gate(history=()):
        calls.clear()
        T._maybe_first_wake_ritual(conn, pid, peep, permanent, peep["name"], list(history), None, None, None)
        return bool(calls)

    check("she arrives with her whole life (well past the newborn line of 3)", mem > 3, mem)
    check("BROUGHT HOME: the first wake runs the ritual", gate())
    check("…but never over a conversation already under way", not gate(["The user said: hi"]))
    os.remove(os.path.join(folder, veil_ritual.PENDING))
    check("MOVED (no mark, a whole life): no ritual — unchanged", not gate())
    veil_ritual.mark_pending(folder)
    open(os.path.join(folder, veil_ritual.STAMP), "w").write("done\n")
    check("DONE stamp wins over a stale mark — once ever", not gate())
    os.remove(os.path.join(folder, veil_ritual.STAMP))

    conn.execute("DELETE FROM memory_stream WHERE peep_id=? AND id > 2", (pid,))
    conn.commit()
    os.remove(os.path.join(folder, veil_ritual.PENDING))
    check("NEWBORN (≤3 memories, no mark): ritual runs — unchanged", gate())

    snap = json.load(open(out, encoding="utf-8"))
    snap.pop("first_wake", None)
    snap["peep"]["uuid"] = "moved-0000-0000"
    moved = os.path.join(SCRATCH, "moved.veil")
    json.dump(snap, open(moved, "w", encoding="utf-8"))
    ok2, _ = veil_roster.import_peep(moved, assume_yes=True)
    mfold = veil_roster.active_peep()["folder_path"]
    check("MOVED (an ordinary .veil): no room is chosen for her — she wakes where she always did",
          ok2 and not os.path.isfile(os.path.join(mfold, "place")))

    import importlib
    importlib.reload(veil_ritual)
    f2 = os.path.join(SCRATCH, "p2")
    os.makedirs(f2)
    veil_ritual.mark_pending(f2)
    card = T.CARD
    done = veil_ritual.run(card, f2, lambda q: "I'm Wick, and you're Ash.", say=lambda *a: None,
                           input_fn=lambda p: "", isatty=True)
    check("a completed ritual clears the mark and stamps done", done and veil_ritual.done(f2)
          and not veil_ritual.pending(f2))
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  a companion brought home is asked who she is on her first wake; every other wake unchanged")
sys.exit(0)
