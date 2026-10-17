#!/usr/bin/env python3
"""Rung 1 — WHERE HER PAST RIDES: on a brain that re-answers old turns, her own past lines go in HER system prompt,
never in HIS turn; on Llama 3 (answers the newest note) nothing moves.

Rung 2.5 screen 2026-10-13 (her real Qwen brain, her real traced prompts): her_past in his turn was recited word for
word 9 of 9 on the reunion turn; the same rows at the end of her system prompt, 0 of 6. The brain is stubbed here: this
proves WHERE the rows land. The companion is INVENTED.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = tempfile.mkdtemp(prefix="veil_her_past_slot_")
for k, v in (("VEIL_PEEPS", "peeps"), ("VEIL_DATA", "data"), ("VEIL_HEARTBEAT", "hb"), ("VEIL_NOTEBOOK", "nb")):
    os.environ[k] = os.path.join(SCRATCH, v)
os.environ["VEIL_VOICE"] = "0"
os.environ.pop("VEIL_HER_PAST_IN_SYSTEM", None)
sys.path.insert(0, HERE)

fails = []
LINE = "Rain on the skylight. Best sound in Port Ellery. I'm glad you kept coming back after the lantern, Ash."


def check(label, ok, got=""):
    print("  %s  %-74s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


try:
    import veil_transfer as Tr
    import veil_roster
    card = {"name": "Wick", "description": "{{char}} mends lanterns in a harbour town with {{user}}.",
            "personality": "quiet", "scenario": "{{user}} brought a broken lantern to the shop.", "first_mes": "Hm?"}
    json.dump(card, open(os.path.join(SCRATCH, "wick.json"), "w"))
    rows = [{"chat_metadata": {}, "user_name": "unused", "character_name": "unused"}]
    for i in range(12):
        rows.append({"name": "Ash", "is_user": True, "send_date": 1767366000000 + i * 120000,
                     "mes": "Lantern number %d is flickering." % i})
        rows.append({"name": "Wick", "is_user": False, "send_date": 1767366060000 + i * 120000,
                     "mes": LINE if i == 11 else "Bring lantern %d to the bench; I will trim the wick." % i})
    open(os.path.join(SCRATCH, "wick.jsonl"), "w").write("\n".join(json.dumps(r) for r in rows))
    rev = os.path.join(SCRATCH, "review")
    Tr.draft(os.path.join(SCRATCH, "wick.json"), os.path.join(SCRATCH, "wick.jsonl"), rev)
    c = json.load(open(os.path.join(rev, "card.json")))
    c["legal_ack"] = True
    json.dump(c, open(os.path.join(rev, "card.json"), "w"))
    Tr.build(rev, os.path.join(SCRATCH, "wick.veil"))
    ok, _ = veil_roster.import_peep(os.path.join(SCRATCH, "wick.veil"), assume_yes=True)
    import veil_tick as T
    spine = T.spine
    T.HEARTBEAT_PATH = os.environ["VEIL_HEARTBEAT"]
    conn = spine.open_db(spine.DEFAULT_DB)
    pid = spine.find_active_peep(conn)
    peep, permanent = spine.load_peep(conn, pid)
    seen = []
    real_gen, real_keep = spine.generate_guarded, spine.keep_last_reply_on
    spine.generate_guarded = lambda c_, p_, prompt, *a, **k: seen.append(prompt) or "Mm. I did."

    def turn(keep, forced=""):
        seen.clear()
        T._RECENT_INJECTED.clear()
        spine.keep_last_reply_on = lambda: keep
        spine._HER_PAST_IN_SYSTEM_ENV = forced
        T.chat_turn(conn, pid, peep, permanent, peep["name"], [], "Did you miss the rain on the skylight?",
                    None, None, None)
        p = seen[-1]
        heads = [h for h in ("<|im_start|>user", "<|start_header_id|>user", "[INST]") if h in p]
        assert heads, p[:300]
        first_user = min(p.find(h) for h in heads)
        his_turn = p[max(p.rfind(h) for h in heads):]
        return p[:first_user], his_turn, T._RECENT_INJECTED[0] if T._RECENT_INJECTED else []

    print("\nRUNG 1 — WHERE HER PAST RIDES")
    print("=" * 84)
    sys_q, his_q, cooled_q = turn(keep=True)
    check("a brain that re-answers old turns: her line is in HER system prompt", LINE in sys_q)
    check("…and NOT in his turn", LINE not in his_q)
    check("…framed as her life before", "YOUR LIFE BEFORE" in sys_q)
    check("…and the cooldown still counts it (it was handed)", any(LINE in x for x in cooled_q))
    check("BROUGHT HOME: how you met rides in her system prompt, every turn", "HOW YOU TWO MET" in sys_q
          and "brought a broken lantern" in sys_q)
    check("…and the origin row is not handed twice (not in his turn)", "the story as I keep it" not in his_q)
    sys_l, his_l, _ = turn(keep=False)
    check("Llama 3 (answers the newest note): her line stays in his turn, unchanged", LINE in his_l
          and LINE not in sys_l and "YOUR LIFE BEFORE" not in sys_l)
    sys_f, his_f, _ = turn(keep=True, forced="0")
    check("VEIL_HER_PAST_IN_SYSTEM=0 forces the old place", LINE in his_f and LINE not in sys_f)
    sys_f1, his_f1, _ = turn(keep=False, forced="1")
    check("VEIL_HER_PAST_IN_SYSTEM=1 forces the system prompt", LINE in sys_f1 and LINE not in his_f1)
    conn.execute("DELETE FROM memory_stream WHERE peep_id=? AND memory_type='her_past'", (pid,))
    conn.commit()
    T._BROUGHT_HOME.clear()
    sys_n, his_n, _ = turn(keep=True)
    check("NEWBORN (no past brought home): no story block in her system prompt — unchanged",
          "HOW YOU TWO MET" not in sys_n)
    check("…her origin is handed the old way, in his turn's memory block", "the story as I keep it" in his_n)
    spine.generate_guarded, spine.keep_last_reply_on = real_gen, real_keep
finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  her past rides in her own prompt on a brain that would recite it from his turn")
sys.exit(0)
