#!/usr/bin/env python3
"""Red-proof — every gate/refusal in intake_parsers.py watched going red.

Each arm feeds a LIVE-SHAPED input that must trip exactly one refusal/note, and a
control arm proving the same input passes when the trip condition is removed.
Exit 0 only if every red arm refuses/speaks AND every control arm passes.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shutil
import tempfile
SCRATCH = tempfile.mkdtemp(prefix="veil_intake_red_")
import veil_intake as P

reds, fails = [], []


def red(label, fn, must_contain=""):
    try:
        fn()
        print("  FAIL  %-58s NO REFUSAL" % label)
        fails.append(label)
    except ValueError as e:
        ok = (must_contain in str(e)) if must_contain else True
        print("  %s  %-58s %s" % ("ok  " if ok else "FAIL", label, str(e)[:60]))
        (reds if ok else fails).append(label)


def w(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows))


print("\nRED-PROOF — INTAKE GATES, WATCHED RED")
print("=" * 74)

H = {"user_name": "Rowan", "character_name": "Marigold"}
mk = lambda i, her, txt: {"name": "Marigold" if her else "Rowan", "is_user": not her,
                          "send_date": 1767366000000 + i * 60000, "mes": txt}

# 1. group merge -> REFUSE with names
g = [H] + [r for i in range(11) for r in (mk(i, False, "q"), mk(i, True, "a", ))]
g[4]["name"] = "Sable"  # index 4 = first HER row (1=header, 2,3=user,her pair 0)
p = os.path.join(SCRATCH, "red_group.jsonl")
w(p, g)
red("group with 2 hers REFUSES, names listed",
    lambda: P.read_st_export(p), "Sable")

# 1-control: same chat, one her -> passes
g[4]["name"] = "Marigold"
w(p, g)
meta, msgs = P.read_st_export(p)
print("  %s  %-58s %d lines" % ("ok  " if len(msgs) == 22 else "FAIL", "control: solo passes", len(msgs)))
if len(msgs) != 22:
    fails.append("control: solo passes")

# 2. one-sided chat -> gate refuses
o = [H] + [mk(i, False, "only me %d" % i) for i in range(12)]
q = os.path.join(SCRATCH, "red_one.jsonl")
w(q, o)
_, m2 = P.read_st_export(q)
ok2, pr2, _ = P.gate_intake(*P.read_st_export(q))
print("  %s  %-58s %s" % ("ok  " if not ok2 else "FAIL", "one-sided chat gate REFUSES", pr2))
(ok2 and fails.append("one-sided") or reds.append("one-sided"))

# 3. swipe disagree -> SPEAKS (gate carries the note, keeps saved text)
s = [H]
for i in range(11):
    s.append(mk(i, False, "q %d" % i))
    s.append({"name": "Marigold", "is_user": False, "send_date": 1767366000000 + i * 60000,
              "mes": "saved %d" % i, "swipes": ["STALE"], "swipe_id": 0})
r = os.path.join(SCRATCH, "red_swipe.jsonl")
w(r, s)
m3, v3 = P.read_st_export(r)
_, pr3, _ = P.gate_intake(m3, v3)
spoke = any("disagree" in x for x in pr3) and all("STALE" not in m["text"] for m in v3)
print("  %s  %-58s kept-saved=%s" % ("ok  " if spoke else "FAIL", "swipe disagree SPOKEN, saved kept", spoke))
(reds if spoke else fails).append("swipe-disagree")

# 4. empty file -> REFUSE
e = os.path.join(SCRATCH, "red_empty.jsonl")
open(e, "w").write("\n")
red("empty file REFUSES", lambda: P.read_st_export(e), "empty")

# 5. ChatGPT: bad index -> REFUSE
c = os.path.join(SCRATCH, "red_cgpt.json")
json.dump([{"title": "t", "mapping": {}, "current_node": None}], open(c, "w"))
red("chatgpt bad index REFUSES", lambda: P.read_chatgpt_conversation(c, 7), "not in this export")

# 8. the round-3 hole, watched red: a stale build emitting 'other' must FAIL the file check
import subprocess as _sp
stale = ("import json,sys; sys.path.insert(0,%r); import veil_intake as P\n" % HERE +
         "meta, msgs = P.read_st_export('hole.jsonl', her='Marigold')\n"
         "cj = {'messages': [{'who': m['who'], 'text': m['text']} for m in msgs]}\n"
         "bad = [m for m in cj['messages'] if m['who'] not in ('you','her')]\n"
         "sys.exit(1 if bad else 0)\n")
with open(os.path.join(SCRATCH, "hole.jsonl"), "w") as f:
    import json as _j
    # BOTH voices must be present: with no Marigold the parser REFUSES (exit 1 too) and the arm would be red for the
    # wrong reason — which is exactly how this arm first passed.
    h = [{"user_name": "Rowan"}]
    for i in range(11):
        h.append({"name": "Rowan", "is_user": True, "mes": "q"})
        h.append({"name": "Marigold" if i % 2 else "Sable", "is_user": False,
                  "mes": "MARIGOLD" if i % 2 else "SABLE"})
    f.write("\n".join(_j.dumps(r) for r in h))
r8 = _sp.run([sys.executable, "-c", stale], cwd=SCRATCH, capture_output=True)
hole_red = (r8.returncode == 1 and not r8.stderr.strip())   # an exit 1 from a refusal or ImportError is not this red
fixed = ("import json,sys; sys.path.insert(0,%r); import veil_intake as P\n" % HERE +
         "meta, msgs = P.read_st_export('hole.jsonl', her='Marigold')\n"
         "cj = P.to_chat_json(meta, msgs)\n"
         "sys.exit(1 if [m for m in cj['messages'] if m['who'] not in ('you','her')] else 0)\n")
r8c = _sp.run([sys.executable, "-c", fixed], cwd=SCRATCH, capture_output=True)
print("  %s  %-58s rc=%d" % ("ok  " if r8c.returncode == 0 else "FAIL",
      "control: the real to_chat_json emits only you/her", r8c.returncode))
if r8c.returncode != 0:
    fails.append("other-control")
print("  %s  %-58s rc=%d" % ("ok  " if hole_red else "FAIL",
      "stale emitter (other in file) goes RED", r8.returncode))
(reds if hole_red else fails).append("other-emitted")
try:
    os.remove(os.path.join(SCRATCH, "hole.jsonl"))
except OSError:
    pass

# 6. header 'unused' is IGNORED even when rows carry no names (Opus finding 1, hard arm)
h = [{"user_name": "unused", "character_name": "unused"}]
for i in range(11):
    h.append({"is_user": True, "send_date": 1767366000000 + i * 60000, "mes": "q %d" % i})
    h.append({"is_user": False, "send_date": 1767366030000 + i * 60000, "mes": "a %d" % i})
hu = os.path.join(SCRATCH, "red_hdr.jsonl")
w(hu, h)
mh, vh = P.read_st_export(hu)
hdr_ok = mh["user_name"] == "" and mh["her_name"] == ""
print("  %s  %-58s user=%r her=%r" % ("ok  " if hdr_ok else "FAIL",
      "nameless rows + 'unused' header -> EMPTY names, never 'unused'",
      mh["user_name"], mh["her_name"]))
(reds if hdr_ok else fails).append("header-unused")

# 7. narrator-only second voice does NOT trip the group gate (Opus finding 2, hard arm)
n2 = [{"user_name": "Rowan"}]
for i in range(11):
    n2.append({"name": "Rowan", "is_user": True, "send_date": 1767366000000 + i * 60000,
               "mes": "q %d" % i})
    n2.append({"name": "Marigold", "is_user": False, "send_date": 1767366030000 + i * 60000,
               "mes": "a %d" % i})
n2.append({"name": "System", "is_user": False, "send_date": 1767366066000,
           "mes": "Thunder.", "extra": {"type": "narrator"}})
nn = os.path.join(SCRATCH, "red_narr.jsonl")
w(nn, n2)
try:
    mn, vn = P.read_st_export(nn)
    nar_ok = mn["dropped_narrator"] == 1 and len(vn) == 22
    print("  %s  %-58s dropped=%s lines=%d" % ("ok  " if nar_ok else "FAIL",
          "narrator never trips group gate", mn["dropped_narrator"], len(vn)))
    (reds if nar_ok else fails).append("narrator-gate")
except ValueError as e:
    print("  FAIL  %-58s %s" % ("narrator never trips group gate", str(e)[:60]))
    fails.append("narrator-gate")

# 5-control: ChatGPT cycle guard terminates (self-parent loop -> empty, gate refuses short)
cyc = {"title": "loop", "current_node": "a",
       "mapping": {"a": {"message": {"author": {"role": "user"},
                                     "content": {"content_type": "text", "parts": ["hi"]},
                                     "create_time": 1},
                         "parent": "a", "children": []}}}
cy = os.path.join(SCRATCH, "red_cyc.json")
json.dump([cyc], open(cy, "w"))
mc, vc = P.read_chatgpt_conversation(cy)
okc, _, _ = P.gate_intake(mc, vc)
print("  %s  %-58s rows=%d" % ("ok  " if not okc else "FAIL", "cycle terminates, gate refuses", len(vc)))
(reds if not okc else fails).append("cycle-guard")

for f in ("red_group.jsonl", "red_one.jsonl", "red_swipe.jsonl", "red_empty.jsonl",
          "red_cgpt.json", "red_cyc.json", "red_hdr.jsonl", "red_narr.jsonl",
          "solo.jsonl", "group.jsonl", "short.jsonl",
          "compact.jsonl", "chatgpt.json", "hdr_unused.jsonl", "narr.jsonl", "multi.json"):
    try:
        os.remove(os.path.join(SCRATCH, f))
    except OSError:
        pass

shutil.rmtree(SCRATCH, ignore_errors=True)

if fails:
    print("\n  %d red arm(s) NOT watched red" % len(fails))
    sys.exit(1)
print("\n  RED-PROOF PASS  %d gates watched red, controls pass" % len(reds))
