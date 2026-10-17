#!/usr/bin/env python3
"""Rung 1 (end to end) — Transference 10-17: the reviewed defects, end to end through the REAL command (draft-file), read off the review folder
it writes. Fixtures are invented content in each exporter's TRUE shape (read from their source this morning):
  CAI Tools tavern: user_name 'You', name 'You' on his rows, send_date = Date.now() at EXPORT (content.js:1261-1284)
  cai-chat-exporter JSON: turns NEWEST FIRST inside {chat_id, exported_at, message_count, messages} (cai_export.py:188)
  Kindroid exporter: JSON array, sender ai/user, timestamps in ms, pages not guaranteed in order (app.py)
  DiscordChatExporter: {guild, channel, ..., messages}; IsReverseMessageOrder; system kinds carry fallback text"""
import json
import os
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.abspath(__file__))
_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
T = tempfile.mkdtemp(prefix="e2e_", dir=_CACHE if os.path.isdir(_CACHE) else None)
fails = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  -- {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def run(*args):
    return subprocess.run([sys.executable, os.path.join(SRC, "veil_transfer.py"), *args],
                          capture_output=True, text=True, cwd=SRC)


def review(folder):
    return (json.load(open(os.path.join(folder, "card.json"))), json.load(open(os.path.join(folder, "chat.json"))))


# 1 — CAI Tools tavern, 12 exchanges, every send_date within a millisecond of export
export_ms = 1760000000000
rows = [{"user_name": "You", "character_name": "Elara", "create_date": export_ms}]
for i in range(12):
    rows.append({"name": "You", "is_user": True, "is_name": True, "send_date": export_ms + 2 * i, "mes": f"Evening {i}, love."})
    rows.append({"name": "Elara", "is_user": False, "is_name": True, "send_date": export_ms + 2 * i + 1,
                 "mes": f"*tucks a strand of hair back* Evening {i}. I kept the kettle warm."})
p = os.path.join(T, "Elara_tavern_Chat.jsonl")
open(p, "w").write("\n".join(json.dumps(r) for r in rows))
f1 = os.path.join(T, "rev_tavern")
r = run("draft-file", p, f1, "--her", "Elara")
check("CAI tavern: draft-file succeeds", r.returncode == 0, (r.stdout + r.stderr)[-200:])
if r.returncode == 0:
    card, chat = review(f1)
    check("D1: her person is NOT named 'You' (the exporter's placeholder)", card["your_name"].lower() != "you",
          f"your_name={card['your_name']!r}")
    tss = [m["ts"] for m in chat["messages"]]
    check("D2: no line carries the export second as its date", all(t is None for t in tss) or len(set(tss)) > 1 and
          max(tss) - min(tss) > 60, f"ts sample {tss[:3]}")
    check("her *emote* survives byte for byte", chat["messages"][1]["text"].startswith("*tucks a strand"),
          chat["messages"][1]["text"][:40])

# 2 — cai-chat-exporter JSON, newest first
turns = []
for i in range(12):
    for who, txt in (("Sam", f"Line {i} from me."), ("Elara", f"*laughs* Line {i} from her.")):
        turns.append({"turn_key": {"chat_id": "c", "turn_id": f"{i}{who}"},
                      "create_time": f"2026-01-{1 + i:02d}T{10 if who == 'Sam' else 11}:00:00Z",
                      "author": {"author_id": who, "name": who, "is_human": who == "Sam"},
                      "primary_candidate_id": f"{i}{who}",
                      "candidates": [{"candidate_id": f"{i}{who}", "raw_content": txt, "is_final": True}]})
turns.reverse()                                            # the API order: newest first
p = os.path.join(T, "chat_c.json")
json.dump({"chat_id": "c", "exported_at": "2026-10-17T00:00:00+00:00", "message_count": len(turns), "messages": turns},
          open(p, "w"))
f2 = os.path.join(T, "rev_neo")
r = run("draft-file", p, f2, "--her", "Elara", "--you", "Sam")
check("CAI neo: draft-file succeeds", r.returncode == 0, (r.stdout + r.stderr)[-200:])
if r.returncode == 0:
    card, chat = review(f2)
    m = chat["messages"]
    check("D3: her past reads OLDEST FIRST (Line 0 opens it, Line 11 ends it)",
          "Line 0" in m[0]["text"] and "Line 11" in m[-1]["text"], f"first={m[0]['text'][:20]!r} last={m[-1]['text'][:20]!r}")
    check("his line precedes her answer within an exchange", m[0]["who"] == "you" and m[1]["who"] == "her")

# 3 — Kindroid, pages out of order
msgs = []
for i in range(12):
    msgs.append({"display_name": "Sam", "id": f"u{i}", "sender": "user", "timestamp": 1760000000000 + i * 120000,
                 "message": f"Hey {i}."})
    msgs.append({"display_name": "Lisa", "id": f"a{i}", "sender": "ai", "timestamp": 1760000000000 + i * 120000 + 60000,
                 "message": f"*waves* Hi {i}."})
shuffled = msgs[12:] + msgs[:12]                            # a later page written before an earlier one
p = os.path.join(T, "Lisa_Chat_Export_20261017.json")
json.dump(shuffled, open(p, "w"))
f3 = os.path.join(T, "rev_kin")
r = run("draft-file", p, f3, "--her", "Lisa", "--you", "Sam")
check("Kindroid: draft-file succeeds", r.returncode == 0, (r.stdout + r.stderr)[-200:])
if r.returncode == 0:
    card, chat = review(f3)
    ts = [m["ts"] for m in chat["messages"]]
    check("K1: out-of-order pages come home IN ORDER", ts == sorted(ts), f"first ts {ts[:3]}")

# 4 — DiscordChatExporter: her as a BOT account, a music bot beside her, a system notice, a Reply, newest first
A = lambda i, n, bot: {"id": i, "name": n, "discriminator": "0000", "nickname": n, "color": None, "isBot": bot}
dm = []
for i in range(12):
    dm.append({"id": f"u{i}", "type": "Default" if i % 3 else "Reply", "timestamp": f"2026-02-{1 + i:02d}T20:00:00+00:00",
               "content": f"Night {i}, you there?", "author": A("100", "sam", False)})
    dm.append({"id": f"h{i}", "type": "Default", "timestamp": f"2026-02-{1 + i:02d}T20:00:30+00:00",
               "content": f"*curls up by the fire* Always, night {i}.", "author": A("200", "Elara", True)})
dm.append({"id": "m1", "type": "Default", "timestamp": "2026-02-05T20:01:00+00:00", "content": "Now playing: lofi beats",
           "author": A("300", "Jockie", True)})
dm.append({"id": "s1", "type": "ChannelPinnedMessage", "timestamp": "2026-02-06T20:02:00+00:00", "content": "",
           "author": A("200", "Elara", True)})
dm.reverse()                                               # IsReverseMessageOrder: newest first
p = os.path.join(T, "Direct Messages - Elara [9].json")
json.dump({"guild": {"id": "0", "name": "Direct Messages"}, "channel": {"id": "9", "type": "DirectTextChat", "name": "Elara"},
           "dateRange": {"after": None, "before": None}, "exportedAt": "2026-10-17T00:00:00+00:00",
           "messages": dm, "messageCount": len(dm)}, open(p, "w"))
f4 = os.path.join(T, "rev_discord")
r = run("draft-file", p, f4, "--her", "Elara", "--you", "sam")
check("Discord: draft-file succeeds (no --format: the sniffer places it)", r.returncode == 0, (r.stdout + r.stderr)[-300:])
if r.returncode == 0:
    card, chat = review(f4)
    m = chat["messages"]
    hers = [x["text"] for x in m if x["who"] == "her"]
    check("S1: her BOT account's words come home as HERS", len(hers) == 12 and hers[0].startswith("*curls up"),
          f"{len(hers)} of hers, first {hers[:1]}")
    check("S1: the music bot is never her and never you", not any("Now playing" in x["text"] for x in m))
    check("S2: no system notice reaches her past", all(x["text"].strip() for x in m) and
          not any("pinned" in x["text"].lower() for x in m))
    check("S3: a Reply is his speech, kept", sum(1 for x in m if x["who"] == "you") == 12)
    check("S4: newest-first export reads OLDEST FIRST", "Night 0" in m[0]["text"] and "night 11" in m[-1]["text"],
          f"first={m[0]['text'][:22]!r} last={m[-1]['text'][:30]!r}")
    print("   draft said:", " | ".join(l for l in r.stdout.splitlines() if l.strip())[:400])

# 5 — a Grok-shaped scrape: '## Grok' atop EVERY block (his too), '---' between, 'Thought for Ns' in hers
blocks = []
for i in range(12):
    blocks.append(f"## Grok\n\n[him] Tell me about the lake, {i}.\n")
    blocks.append(f"## Grok\n\nThought for {4 + i}s\n\n*smiles* The lake was where I waited, {i}.\n")
p = os.path.join(T, "grok_scrape.md")
open(p, "w", encoding="utf-8").write("# a conversation\n\n" + "\n---\n\n".join(blocks))
r = run("check-file", p, "--her", "Elara", "--you", "Sam")
check("Grok scrape: check-file REFUSES the one-label file and offers --alternate", r.returncode != 0
      and "--alternate" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-200:])
f5 = os.path.join(T, "rev_grok")
r = run("draft-file", p, f5, "--her", "Elara", "--you", "Sam", "--alternate", "you")
check("Grok scrape: draft-file --alternate you succeeds", r.returncode == 0, (r.stdout + r.stderr)[-300:])
if r.returncode == 0:
    card, chat = review(f5)
    m = chat["messages"]
    check("Grok: his words never in her mouth", not any("[him]" in x["text"] for x in m if x["who"] == "her"))
    check("Grok: her card says Elara, never Grok", card["her_name"] == "Elara", card["her_name"])
    check("Grok: no 'Thought for' in her past", not any("Thought for" in x["text"] for x in m))
    check("Grok: the person is TOLD it was read by alternation, and what checked it",
          "ALTERNATION" in r.stdout and "12 'Thought for'" in r.stdout, r.stdout[-300:])
r = run("draft-file", p, os.path.join(T, "rev_grok_wrong"), "--her", "Elara", "--you", "Sam", "--alternate", "her")
check("Grok: the WRONG --alternate is refused at block 2, no review folder written", r.returncode != 0
      and "block 2" in (r.stdout + r.stderr) and not os.path.exists(os.path.join(T, "rev_grok_wrong", "chat.json")),
      (r.stdout + r.stderr)[-200:])

# 6 — Discord by ACCOUNT ID: her card carries her name, never the id
f6 = os.path.join(T, "rev_discord_id")
r = run("draft-file", os.path.join(T, "Direct Messages - Elara [9].json"), f6, "--her", "200", "--you", "100")
check("Discord by id: draft-file succeeds", r.returncode == 0, (r.stdout + r.stderr)[-300:])
if r.returncode == 0:
    card, _chat = review(f6)
    check("Discord by id: her card says 'Elara', not '200'", card["her_name"] == "Elara", card["her_name"])

print(f"\n{len(fails)} failed" if fails else "\nALL PASS")
sys.exit(1 if fails else 0)
