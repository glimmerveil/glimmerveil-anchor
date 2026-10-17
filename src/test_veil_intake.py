#!/usr/bin/env python3
"""Rung 1 — Transference intake parsers: ST proof fields + ChatGPT path, all from invented data.

Companions here are INVENTED (Marigold/Rowan; ChatGPT fixture is a made-up lighthouse chat).
Fixtures live in a temp scratch folder, never beside the code.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shutil
import tempfile
SCRATCH = tempfile.mkdtemp(prefix="veil_intake_rig_")
import veil_intake as P

fails = []


def check(label, ok, got=""):
    print("  %s  %-62s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def st_row(i, name, user, text, **kw):
    r = {"name": name, "is_user": user, "send_date": 1767366000000 + i * 60000, "mes": text}
    r.update(kw)
    return r


def write_st(path, rows):
    if isinstance(rows, (str, bytes)):
        raise TypeError("write_st takes the ROW LIST, not the path — refusing to join a string")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows))


print("\nRUNG 1 — TRANSFERENCE INTAKE PARSERS")
print("=" * 74)

# --- A. solo ST, 12 exchanges, header row, one crash-mid-stream row, one display_text row ---
solo = [{"user_name": "Rowan", "character_name": "Marigold"}]
for i in range(12):
    solo.append(st_row(2 * i + 1, "Rowan", True, "Line %d from me, Marigold?" % i))
    her = {"name": "Marigold", "is_user": False, "send_date": 1767366060000 + i * 60000,
           "mes": "The lighthouse at Gull Point, line %d." % i,
           "swipes": ["The lighthouse at Gull Point, line %d." % i], "swipe_id": 0}
    solo.append(her)
solo[6]["swipes"] = ["STALE BRANCH — never shown"]  # crash between swipe-write and finalize
solo[8]["extra"] = {"display_text": "Shown words for line 3."}
solo.append({"name": "System", "is_system": True, "mes": "[note]"})
sp = os.path.join(SCRATCH, "solo.jsonl")
write_st(sp, solo)
meta, msgs = P.read_st_export(sp)
ok, problems, stats = P.gate_intake(meta, msgs)
check("solo: 24 lines, header+system skipped", len(msgs) == 24, len(msgs))
check("solo: ordinals are source positions", [m["ord"] for m in msgs][:3] == [1, 2, 3])
check("solo: gate passes, swipe mismatch SPOKEN not silent",
      ok and any("disagree" in p for p in problems), problems)
check("solo: crash row kept the SAVED text",
      "Gull Point, line 2." in next(m["text"] for m in msgs if m["ord"] == 6))
check("solo: display_text preferred + marked",
      next(m["shown_as"] for m in msgs if m["ord"] == 8) == "display_text")
check("solo: stats shape mirrors veil_transfer.gate",
      stats == {"your_lines": 12, "her_lines": 12, "source": "sillytavern"}, stats)

# --- B. group ST refused with the names listed ---
def grp_rows():
    rows = [{"user_name": "Rowan", "character_name": "Group"}]
    for i in range(11):
        rows.append(st_row(i, "Rowan", True, "hi %d" % i))
        rows.append(st_row(i, "Marigold" if i % 2 else "Sable", False, "reply %d" % i))
    return rows


grp = grp_rows()
gp = os.path.join(SCRATCH, "group.jsonl")
write_st(gp, grp)
try:
    P.read_st_export(gp)
    check("group: REFUSED with names", False)
except ValueError as e:
    check("group: REFUSED with names", "Marigold" in str(e) and "Sable" in str(e), str(e)[:80])

# --- C. short ST refused by the shared gate ---
sh = [{"user_name": "Rowan"}]
for i in range(3):
    sh.append({"name": "Rowan", "is_user": True, "send_date": 1767366000000 + i * 60000,
               "mes": "short %d" % i})
    sh.append({"name": "Marigold", "is_user": False, "send_date": 1767366030000 + i * 60000,
               "mes": "brief %d" % i})
shp = os.path.join(SCRATCH, "short.jsonl")
write_st(shp, sh)
write_st(shp, sh)
ok3, p3, _ = P.gate_intake(*P.read_st_export(shp))
check("short: gate refuses <10 exchanges", not ok3, p3)

# --- D. compact single-swipe row (ST #6091): no swipes[] at all, reads fine ---
cp = [{"user_name": "Rowan"}]
for i in range(11):
    cp.append(st_row(i, "Rowan", True, "q %d" % i))
    cp.append({"name": "Marigold", "is_user": False, "mes": "a %d" % i})
cpp = os.path.join(SCRATCH, "compact.jsonl")
write_st(cpp, cp)
_, msgs4 = P.read_st_export(cpp)
check("compact: mes-without-swipes reads, not failure", len(msgs4) == 22, len(msgs4))

# --- E. ChatGPT: branch off-path ignored, system/tool/hidden dropped, path order kept ---
def node(nid, role, text, parent, kids=(), ctype="text", hidden=False):
    m = {"author": {"role": role}, "content": {"content_type": ctype, "parts": [text]},
         "create_time": 1767366000.0 + nid}
    if hidden:
        m["metadata"] = {"is_visually_hidden_from_conversation": True}
    return {"id": nid, "message": m, "parent": parent, "children": list(kids)}


def conv(path, current, nodes):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{"title": "Lighthouse", "mapping": {n: nodes[n] for n in nodes},
                          "current_node": current}], f)


cn = {}
cn[1] = node(1, "system", "sys", None, [2])
for i in range(12):
    u, a = 2 + 2 * i, 3 + 2 * i
    cn[u] = node(u, "user", "q %d" % i, u - 1 if i else 1, [a])
    cn[a] = node(a, "assistant", "a %d, Gull Point." % i, u, [a + 1] if i < 11 else [90, 91])
cn[90] = node(90, "assistant", "REGEN BRANCH — never shown", 24, [])
cn[91] = node(91, "tool", "tool output", 24, [])
cn[92] = node(92, "assistant", "HIDDEN", 25, [], hidden=True)
cn[25] = node(25, "assistant", "a 11, Gull Point.", 24, [92])
ep = os.path.join(SCRATCH, "chatgpt.json")
conv(ep, 25, cn)
meta5, msgs5 = P.read_chatgpt_conversation(ep)
ok5, _, stats5 = P.gate_intake(meta5, msgs5)
check("chatgpt: 24 path rows, branch/hidden/tool/system dropped",
      len(msgs5) == 24 and not any("REGEN" in m["text"] or "HIDDEN" in m["text"] for m in msgs5),
      len(msgs5))
check("chatgpt: ordinals are path positions (system root excluded)",
      msgs5[0]["ord"] == 1 and msgs5[-1]["ord"] == 24)
check("chatgpt: gate passes (12 exchanges)", ok5 and stats5["her_lines"] == 12, stats5)
check("chatgpt: lister names the conversation",
      P.list_chatgpt_conversations(ep)[0]["title"] == "Lighthouse")

# --- F. chat.json shape build() already reads ---
cj = P.to_chat_json(meta, msgs)
check("chat.json: who/text/ts (+ord additive)", set(cj["messages"][0]) == {"who", "text", "ts", "ord"})

# --- H. Opus round-3 hole (2026-10-13): who='other' must NEVER reach chat.json ---
hole = [{"user_name": "Rowan"}]
for i in range(11):
    hole.append({"name": "Rowan", "is_user": True, "send_date": 1767366000000 + i * 60000,
                 "mes": "q %d" % i})
    hole.append({"name": "Marigold" if i % 2 else "Sable", "is_user": False,
                 "send_date": 1767366030000 + i * 60000,
                 "mes": "SABLE SPEAKS %d" % i if not i % 2 else "a %d" % i})
hop = os.path.join(SCRATCH, "hole.jsonl")
with open(hop, "w", encoding="utf-8") as f:
    f.write("\n".join(json.dumps(r) for r in hole))
metaH, msgsH = P.read_st_export(hop, her="Marigold")
cjH = P.to_chat_json(metaH, msgsH)
whosH = {m["who"] for m in cjH["messages"]}
check("other rows NEVER emitted (build would voice them as hers)",
      whosH <= {"you", "her"} and not any("SABLE" in m["text"] for m in cjH["messages"]),
      whosH)
okH, probsH, statsH = P.gate_intake(metaH, msgsH)
check("set-aside named in gate notes + stats",
      any("Sable" in p for p in probsH) and statsH.get("other_lines") == 6,
      (probsH, statsH))

# --- G. Opus round-2 fixes (2026-10-13): header-unused, narrator, her=, counts, multimodal ---
hdr = [{"user_name": "unused", "character_name": "unused"}]
for i in range(11):
    hdr.append({"name": "Rowan", "is_user": True, "send_date": 1767366000000 + i * 60000,
                "mes": "q %d" % i})
    hdr.append({"name": "Wren", "is_user": False, "send_date": 1767366030000 + i * 60000,
                "mes": "a %d" % i})
hp = os.path.join(SCRATCH, "hdr_unused.jsonl")
with open(hp, "w", encoding="utf-8") as f:
    f.write("\n".join(json.dumps(r) for r in hdr))
meta7, msgs7 = P.read_st_export(hp)
check("header 'unused' NEVER names him",
      meta7["user_name"] == "Rowan" and meta7["her_name"] == "Wren", meta7)

nar = [{"user_name": "Rowan"}]
for i in range(11):
    nar.append({"name": "Rowan", "is_user": True, "send_date": 1767366000000 + i * 60000,
                "mes": "q %d" % i})
    nar.append({"name": "Marigold", "is_user": False, "send_date": 1767366030000 + i * 60000,
                "mes": "a %d" % i})
nar.insert(5, {"name": "System", "is_user": False, "is_system": False,
               "send_date": 1767366015000, "mes": "The candles gutter.",
               "extra": {"type": "narrator"}})
np = os.path.join(SCRATCH, "narr.jsonl")
with open(np, "w", encoding="utf-8") as f:
    f.write("\n".join(json.dumps(r) for r in nar))
meta8, msgs8 = P.read_st_export(np)
ok8, _, _ = P.gate_intake(meta8, msgs8)
check("narrator row dropped, never a speaker (solo still passes)",
      ok8 and meta8["dropped_narrator"] == 1 and len(msgs8) == 22,
      (meta8["dropped_narrator"], len(msgs8)))
check("display_text count carried in meta", meta.get("display_text_rows") == 1, meta)

gp2 = os.path.join(SCRATCH, "group.jsonl")
with open(gp2, "w", encoding="utf-8") as f:
    f.write("\n".join(json.dumps(r) for r in grp_rows()))
meta9, msgs9 = P.read_st_export(gp2, her="Marigold")
hers9 = [m for m in msgs9 if m["who"] == "her"]
oths9 = [m for m in msgs9 if m["who"] == "other"]
check("her=: hers kept, others set aside + NAMED",
      all(m["name"] == "Marigold" for m in hers9) and len(oths9) > 0
      and meta9["set_aside_speakers"] == ["Sable"], meta9["set_aside_speakers"])
try:
    P.read_st_export(gp2, her="Nobody")
    check("her= unknown name REFUSES", False)
except ValueError as e:
    check("her= unknown name REFUSES", "Nobody" in str(e), str(e)[:60])

mm = {"title": "Picnic", "current_node": 3,
      "mapping": {
          "1": {"message": {"author": {"role": "user"},
                            "content": {"content_type": "multimodal_text",
                                        "parts": [{"content_type": "image_asset_pointer", "asset_pointer": "file-x"},
                                                  {"content_type": "text", "text": "look at this cake"}]},
                            "create_time": 1767366000.0}, "parent": None, "children": [2]},
          "2": {"message": {"author": {"role": "assistant"},
                            "content": {"content_type": "text", "parts": ["what a cake"]},
                            "create_time": 1767366010.0}, "parent": "1", "children": [3]},
          "3": {"message": {"author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["we ate it"]},
                            "create_time": 1767366020.0}, "parent": "2", "children": []}}}
mp = os.path.join(SCRATCH, "multi.json")
json.dump([mm], open(mp, "w"))
_, msgs10 = P.read_chatgpt_conversation(mp)
check("multimodal: image dropped, str text survives",
      msgs10[0]["text"] == "look at this cake", msgs10[0]["text"] if msgs10 else "EMPTY")

shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  ST proven from source, ChatGPT from the path, gates speak")
