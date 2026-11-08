#!/usr/bin/env python3
"""Rung 1 — Transference from Claude (claude.ai "Export data"), 2026-11-07: invented fixtures only.

The companion here is INVENTED (Wren, and her person Sage). No real person's words, no real export.
The fixtures are built in the shape independent parsers of claude.ai's export read (docs/transference/PROOF_CLAUDE.md):
a ZIP holding conversations.json (+ users.json, projects.json); conversations carry chat_messages; a message carries
sender human|assistant, text, content blocks, created_at, attachments, files; parent_message_uuid when a turn was edited.

The command-line half runs FIRST and through the real veil_transfer.py, so against the code before this change it goes
RED with plain failures (every .zip went to Character.AI; conversations.json was refused; claude-list did not exist).
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
fails = []


def check(label, ok, got=""):
    print("  %s  %-74s %s" % ("ok  " if ok else "FAIL", label, str(got)[:120]))
    if not ok:
        fails.append(label)


def run(*args):
    return subprocess.run([sys.executable, os.path.join(HERE, "veil_transfer.py"), *args],
                          capture_output=True, text=True, cwd=HERE)


def iso(i):
    return "2026-10-01T20:%02d:%02d.123456Z" % (i // 60, i % 60)


def msg(uid, sender, text, i, parent=None, content=None, **extra):
    m = {"uuid": uid, "sender": sender, "text": text, "created_at": iso(i), "updated_at": iso(i),
         "attachments": [], "files": [],
         "content": content if content is not None else [{"type": "text", "text": text}]}
    if parent is not None:
        m["parent_message_uuid"] = parent
    m.update(extra)
    return m


def long_convo():
    """12 exchanges with everything a real export can carry, in one conversation."""
    ms = []
    for i in range(12):
        human = f"Evening {i}, Wren. How was the garden today?"
        her = f"*brushes soil off her hands* Evening {i}, Sage. The roses opened by the window."
        content = None
        if i == 2:     # a thinking block before her words: activity, never her words
            content = [{"type": "thinking", "thinking": "SECRET-THOUGHT the user wants warmth"},
                       {"type": "text", "text": her}]
        if i == 3:     # a tool call and its result beside her words
            content = [{"type": "tool_use", "name": "web_search", "input": {"q": "SECRET-TOOL roses"}},
                       {"type": "tool_result", "content": "SECRET-TOOL result"},
                       {"type": "text", "text": her}]
        if i == 4:     # markdown structure and an OOC line: cleaned, her *emote* kept
            her = "## A note\n(OOC: brb, phone)\n" + her
            content = [{"type": "text", "text": her}]
        ms.append(msg(f"h{i}", "human", human, 2 * i,
                      **({"attachments": [{"file_name": "notes.txt", "extracted_content": "SECRET-ATTACHMENT"}]}
                         if i == 5 else {})))
        if i == 6:     # an older export: no content list at all, only the top-level text
            m = msg(f"a{i}", "assistant", her, 2 * i + 1)
            del m["content"]
            ms.append(m)
        elif i == 7:   # content present but empty: fall back to text
            ms.append(msg(f"a{i}", "assistant", her, 2 * i + 1, content=[]))
        else:
            ms.append(msg(f"a{i}", "assistant", her, 2 * i + 1, content=content))
    return {"uuid": "c-long", "name": "Wren's garden", "created_at": iso(0), "updated_at": iso(30),
            "account": {"uuid": "acct"}, "chat_messages": ms}


def short_convo():
    ms = []
    for i in range(3):
        ms += [msg(f"sh{i}", "human", f"Quick question {i}?", 2 * i), msg(f"sa{i}", "assistant", f"Quick answer {i}.", 2 * i + 1)]
    return {"uuid": "c-short", "name": "a quick one", "created_at": iso(0), "chat_messages": ms}


def branched_convo(leaf_field=True):
    """12 exchanges; at exchange 5 his message was EDITED, so two branches hang off a4. The shown one is 'b'."""
    ms, parent = [], None
    for i in range(12):
        for branch in (("a", "b") if i == 5 else ("",)):
            pid = parent if i <= 5 else parent
            hid, aid = f"h{i}{branch}", f"a{i}{branch}"
            word = "OLD-BRANCH" if branch == "a" else "kept"
            ms.append(msg(hid, "human", f"Turn {i} {word}, Wren.", 2 * i, parent=pid))
            ms.append(msg(aid, "assistant", f"*smiles* Turn {i} {word}, Sage.", 2 * i + 1, parent=hid))
        parent = f"a{i}b" if i == 5 else f"a{i}"
    c = {"uuid": "c-branch", "name": "edited", "created_at": iso(0), "chat_messages": ms}
    if leaf_field:
        c["current_leaf_message_uuid"] = "a11"
    return c


print("\nRUNG 1 — TRANSFERENCE FROM CLAUDE")
print("=" * 90)
_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
with tempfile.TemporaryDirectory(dir=_CACHE if os.path.isdir(_CACHE) else None) as T:
    export = [short_convo(), long_convo()]
    zpath = os.path.join(T, "data-2026-11-07.zip")
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("conversations.json", json.dumps(export))
        z.writestr("users.json", json.dumps([{"uuid": "u", "full_name": "Sage"}]))
        z.writestr("projects.json", "[]")
    nested = os.path.join(T, "nested.zip")
    with zipfile.ZipFile(nested, "w") as z:
        z.writestr("data-export/conversations.json", json.dumps(export))
    cjson = os.path.join(T, "conversations.json")
    json.dump(export, open(cjson, "w"))
    single = os.path.join(T, "one.json")
    json.dump([long_convo()], open(single, "w"))

    print("\n  -- the command line (red before this change) --")
    r = run("claude-list", zpath)
    check("claude-list on the export ZIP names both conversations with their lines", r.returncode == 0
          and "[0] a quick one" in r.stdout and "[1] Wren's garden" in r.stdout and "24 lines" in r.stdout, r.stdout + r.stderr)
    r = run("claude-list", cjson)
    check("claude-list on the bare conversations.json, the same", r.returncode == 0 and "24 lines" in r.stdout, r.stdout + r.stderr)
    r = run("claude-list", nested)
    check("claude-list finds conversations.json inside a folder in the ZIP", r.returncode == 0 and "24 lines" in r.stdout,
          r.stdout + r.stderr)
    rev = os.path.join(T, "review")
    r = run("draft-claude", zpath, "1", "Wren", rev)
    check("draft-claude from the ZIP writes her review folder", r.returncode == 0 and os.path.isfile(os.path.join(rev, "chat.json")),
          (r.stdout + r.stderr)[-200:])
    r = run("check-file", zpath)
    check("check-file on a two-conversation ZIP says how to pick (claude-list), never Character.AI",
          r.returncode != 0 and "claude-list" in (r.stdout + r.stderr) and "cai" not in (r.stdout + r.stderr).lower(),
          (r.stdout + r.stderr)[-160:])
    r = run("check-file", single)
    check("check-file on a one-conversation export reads it as claude, ready", r.returncode == 0
          and r.stdout.startswith("claude: 12 of her lines, 12 of yours") and "ready to draft" in r.stdout, r.stdout + r.stderr)
    r = run("draft-file", single, os.path.join(T, "review_file"), "--her", "Wren")
    check("draft-file on a one-conversation export, --her names her", r.returncode == 0, (r.stdout + r.stderr)[-160:])
    r = run("chatgpt-list", zpath)
    check("chatgpt-list on a Claude export points to claude-list (it showed '(untitled) 0 lines')",
          r.returncode == 1 and "claude-list" in r.stdout, r.stdout + r.stderr)
    r = run("draft-claude", zpath, "0", "Wren", os.path.join(T, "too_short"))
    check("a 3-exchange conversation is refused as too short, as every reader's is", r.returncode != 0
          and "too short" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-120:])
    r = run("draft-claude", zpath, "7", "Wren", os.path.join(T, "nope"))
    check("a conversation number not in the export is refused, naming claude-list", r.returncode != 0
          and "claude-list" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-120:])

    print("\n  -- what reached her review folder --")
    if os.path.isfile(os.path.join(rev, "chat.json")):
        card = json.load(open(os.path.join(rev, "card.json")))
        chat = json.load(open(os.path.join(rev, "chat.json")))
        lines = chat["messages"]
        alltext = "\n".join(m["text"] for m in lines)
        readme = open(os.path.join(rev, "READ_ME_FIRST.txt"), encoding="utf-8").read()
        check("her card starts EMPTY, her name only, unread (ChatGPT's cardless path)",
              card["her_name"] == "Wren" and not card["who_she_is"] and not card["your_name"] and card["legal_ack"] is False)
        check("12 of his lines and 12 of hers, alternating, his first", len(lines) == 24
              and [m["who"] for m in lines] == ["you", "her"] * 12, [m["who"] for m in lines][:4])
        check("no thinking, no tool call, no attachment text ever reaches her words",
              "SECRET" not in alltext, [m["text"][:30] for m in lines if "SECRET" in m["text"]][:1])
        check("her *emote* survives byte for byte", lines[1]["text"].startswith("*brushes soil off her hands*"), lines[1]["text"][:40])
        check("the OOC aside and the markdown heading are cleaned; her line kept",
              "(OOC" not in alltext and "## A note" not in alltext and "A note" in lines[9]["text"], lines[9]["text"][:60])
        check("an old message with no content list falls back to its text",
              lines[13]["text"].endswith("roses opened by the window."), lines[13]["text"][-40:])
        check("content present but empty falls back to its text", lines[15]["text"].endswith("window."), lines[15]["text"][-30:])
        tss = [m["ts"] for m in lines]
        check("every line keeps its own real time (ISO, fractional seconds, Z)",
              all(isinstance(t, int) for t in tss) and tss == sorted(tss) and len(set(tss)) == 24, tss[:3])
        check("ord follows the conversation as shown", [m["ord"] for m in lines] == list(range(24)))
        check("the review names what was set aside (thinking/tools, the attachment, the cleaning)",
              "activity" in readme and "attachments" in readme and "out-of-character" in readme, "")
        card.update(legal_ack=True)
        json.dump(card, open(os.path.join(rev, "card.json"), "w"))
        import veil_transfer as V
        try:
            V.build(rev, os.path.join(T, "wren.veil"))
            check("build refuses until who she is has been written", False)
        except SystemExit as e:
            check("build refuses until who she is has been written", "who_she_is" in str(e), str(e)[:60])
        card.update(your_name="Sage", who_she_is="Wren keeps the garden behind the old house; gentle, dry-humoured, loves roses.")
        json.dump(card, open(os.path.join(rev, "card.json"), "w"))
        r2 = V.build(rev, os.path.join(T, "wren.veil"))
        check("once written she builds: her 12 turns, all 24 lines kept verbatim",
              r2["rows"] == 12 and r2["archive"] == 24, (r2["rows"], r2["archive"]))
    else:
        check("(the review folder was not written; the lines above say why)", False)

    print("\n  -- the reader itself --")
    import veil_intake_claude as C
    import veil_transfer as V
    check("detect_format: the Claude ZIP is 'claude'", V.detect_format(zpath) == "claude", V.detect_format(zpath))
    check("detect_format: its conversations.json is 'claude'", V.detect_format(cjson) == "claude", V.detect_format(cjson))
    cai = os.path.join(T, "cai_export.zip")
    with zipfile.ZipFile(cai, "w") as z:
        z.writestr("chats.json", json.dumps([{"author": "Elara", "text": "hello", "is_human": False}]))
    check("detect_format: a Character.AI ZIP still goes to cai-official", V.detect_format(cai) == "cai-official",
          V.detect_format(cai))
    gpt = os.path.join(T, "gpt_conversations.json")
    json.dump([{"title": "x", "mapping": {}, "current_node": None}], open(gpt, "w"))
    check("detect_format: ChatGPT's conversations.json is never taken for Claude", V.detect_format(gpt) != "claude",
          V.detect_format(gpt))
    for leaf in (True, False):
        bp = os.path.join(T, f"branch_{leaf}.json")
        json.dump([branched_convo(leaf_field=leaf)], open(bp, "w"))
        meta, msgs = C.read_claude_conversation(bp, 0)
        texts = "\n".join(m["text"] for m in msgs)
        check(f"an edited turn: the shown branch only, 24 lines ({'current_leaf' if leaf else 'last message'})",
              len(msgs) == 24 and "OLD-BRANCH" not in texts and "Turn 5 kept" in texts, (len(msgs), "OLD-BRANCH" in texts))
        check("…and the left-out branch is named, never silent",
              any("not on the branch" in n for n in meta["resolution_notes"]), meta["resolution_notes"][:1])
    loop = {"uuid": "c-loop", "name": "loop", "current_leaf_message_uuid": "x",
            "chat_messages": [msg("x", "human", "a", 0, parent="y"), msg("y", "assistant", "b", 1, parent="x")]}
    lp = os.path.join(T, "loop.json")
    json.dump([loop], open(lp, "w"))
    meta, msgs = C.read_claude_conversation(lp, 0)
    check("a parent loop in a broken file ends (cycle-guarded), no hang", len(msgs) == 2, len(msgs))
    other = {"uuid": "c-o", "name": "o", "chat_messages": [msg("s", "system", "SECRET-SYSTEM", 0)] + long_convo()["chat_messages"]}
    op = os.path.join(T, "other.json")
    json.dump([other], open(op, "w"))
    meta, msgs = C.read_claude_conversation(op, 0)
    check("a message from neither of them is set aside and counted",
          "SECRET-SYSTEM" not in "\n".join(m["text"] for m in msgs) and any("neither of you" in n for n in meta["resolution_notes"]))
    roled = {"uuid": "c-r", "name": "r", "chat_messages": [dict({k: v for k, v in m.items() if k != "sender"},
                                                              role="user" if m["sender"] == "human" else "assistant")
                                                         for m in long_convo()["chat_messages"]]}
    rp = os.path.join(T, "roled.json")
    json.dump([roled], open(rp, "w"))
    meta, msgs = C.read_claude_conversation(rp, 0)
    check("a variant that says role (user/assistant) instead of sender reads the same", len(msgs) == 24, len(msgs))
    def zip_with(name, body):
        def make(p):
            with zipfile.ZipFile(p, "w") as z:
                z.writestr(name, body)
        return make

    def not_a_zip(p):
        with open(p, "w") as f:
            f.write("hello")

    for label, make in (("a zip with no conversations.json", zip_with("users.json", "[]")),
                        ("a zip whose conversations.json is not JSON", zip_with("conversations.json", "[{oops")),
                        ("a file that is not a zip at all", not_a_zip)):
        p = os.path.join(T, label.replace(" ", "_") + ".zip")
        make(p)
        try:
            C.list_claude_conversations(p)
            check(f"refused, plainly: {label}", False)
        except ValueError as e:
            check(f"refused, plainly: {label}", str(e).startswith("refused:"), str(e)[:70])
        check(f"…and detect_format never calls it Claude: {label}", V.detect_format(p) != "claude", V.detect_format(p))
    try:
        C.list_claude_conversations(gpt)
        check("claude-list on a ChatGPT file is refused (not a Claude export)", False)
    except ValueError as e:
        check("claude-list on a ChatGPT file is refused (not a Claude export)", "not a Claude export" in str(e), str(e)[:70])
    print("\n  -- Haiku's breaks, 11-07 (each was a traceback or a quiet wrong answer before) --")
    good = json.dumps([long_convo()]).encode()
    crc = os.path.join(T, "badcrc.zip")
    with zipfile.ZipFile(crc, "w", zipfile.ZIP_STORED) as z:
        z.writestr("conversations.json", good)
    blob = bytearray(open(crc, "rb").read())
    i = blob.find(b'"chat_messages"') + 3
    blob[i] ^= 0x20                                         # one byte flipped inside the stored member: its CRC fails
    open(crc, "wb").write(bytes(blob))
    r = run("claude-list", crc)
    check("a damaged member (bad CRC): a plain refusal, no traceback", r.returncode != 0 and "Traceback" not in r.stderr
          and "refused" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-120:])
    check("…and it is still Claude's to refuse, never handed to Character.AI", V.detect_format(crc) == "claude",
          V.detect_format(crc))
    enc = os.path.join(T, "encrypted.zip")
    with zipfile.ZipFile(enc, "w", zipfile.ZIP_STORED) as z:
        z.writestr("conversations.json", good)
    blob = bytearray(open(enc, "rb").read())                # zipfile will not WRITE encryption: set the flag by hand,
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):   # in the local header AND the central directory
        at = blob.find(sig)
        blob[at + off] |= 0x01
    open(enc, "wb").write(bytes(blob))
    r = run("claude-list", enc)
    check("an encrypted member: a plain refusal, no traceback", r.returncode != 0 and "Traceback" not in r.stderr,
          (r.stdout + r.stderr)[-120:])
    deep = os.path.join(T, "deep.json")
    open(deep, "w").write("[" * 200000 + "]" * 200000)
    try:
        C.list_claude_conversations(deep)
        check("a file nested 200,000 deep is refused, no stack overflow", False)
    except ValueError as e:
        check("a file nested 200,000 deep is refused, no stack overflow", str(e).startswith("refused:"), str(e)[:60])
    check("…and detect_format survives it", V.detect_format(deep) is None, V.detect_format(deep))
    inf = os.path.join(T, "inf.json")
    c = long_convo()
    c["chat_messages"][0]["created_at"] = 1e400
    open(inf, "w").write(json.dumps([c]).replace("Infinity", "1e400"))
    meta, msgs = C.read_claude_conversation(inf, 0)
    check("an impossible time (1e400) is no time, never a crash", msgs[0]["ts"] is None and len(msgs) == 24, msgs[0]["ts"])
    nouuid = {"uuid": "c-n", "name": "n", "chat_messages": [
        msg("h1", "human", "first question", 0), msg("a1", "assistant", "first answer", 1, parent="h1"),
        msg("h2x", "human", "OLD edited q", 2, parent="a1"), msg("a2x", "assistant", "OLD answer", 3, parent="h2x"),
        msg("h2", "human", "NEW edited q", 4, parent="a1"), msg(None, "assistant", "NEW answer", 5, parent="h2")]}
    np_ = os.path.join(T, "nouuid.json")
    json.dump([nouuid], open(np_, "w"))
    meta, msgs = C.read_claude_conversation(np_, 0)
    texts = [m["text"] for m in msgs]
    check("an edit whose last reply has no id: the shown branch whole, her last reply KEPT, never interleaved",
          texts == ["first question", "first answer", "NEW edited q", "NEW answer"], texts)
    check("…and only the old branch is said as left out (2)",
          any(n.startswith("2 message(s) not on the branch") for n in meta["resolution_notes"]),
          meta["resolution_notes"][:1])
    print("\n  -- Haiku's second pass, 11-07 --")
    noedit = {"uuid": "c-ne", "name": "ne", "chat_messages": [            # never edited: no message has two replies
        msg("h1", "human", "first question", 0), msg("a1", "assistant", "first answer", 1, parent="h1"),
        msg("h2", "human", "second question", 2, parent="a1"), msg(None, "assistant", "second answer, no id", 3, parent="h2")]}
    ne = os.path.join(T, "noedit.json")
    json.dump([noedit], open(ne, "w"))
    meta, msgs = C.read_claude_conversation(ne, 0)
    check("a chat never edited, last reply with no id: every message kept, nothing said as left out",
          [m["text"] for m in msgs][-1] == "second answer, no id" and len(msgs) == 4
          and not any("not on the branch" in n for n in meta["resolution_notes"]), [m["text"] for m in msgs])
    early = [msg(f"e{i}", "human" if i % 2 == 0 else "assistant", f"early {i}", i) for i in range(6)]   # NO parent keys
    late = [msg("o1", "human", "OLD-BRANCH late", 6, parent="e5"), msg("n1", "human", "late 6", 7, parent="e5"),
            msg("n2", "assistant", "late 7", 8, parent="n1"), msg("n3", "human", "late 8", 9, parent="n2"),
            msg("n4", "assistant", "late 9", 10, parent="n3")]
    mixed = {"uuid": "c-mx", "name": "mx", "current_leaf_message_uuid": "n4", "chat_messages": early + late}
    mx = os.path.join(T, "mixed.json")
    json.dump([mixed], open(mx, "w"))
    meta, msgs = C.read_claude_conversation(mx, 0)
    texts = [m["text"] for m in msgs]
    check("an unlinked opening (no parent keys) before an edited later turn: the opening KEPT in front",
          texts == [f"early {i}" for i in range(6)] + [f"late {i}" for i in range(6, 10)], texts)
    check("…and only the one old-branch message is said as left out",
          any(n.startswith("1 message(s) not on the branch") for n in meta["resolution_notes"]), meta["resolution_notes"][:1])
    lone = {"uuid": "c-lone", "name": "lone", "chat_messages": [
        {"uuid": "l1", "sender": "human", "text": "a question", "created_at": iso(0)},
        {"uuid": "l2", "sender": "assistant", "text": "SECRET-LONE-TOOL", "created_at": iso(1),
         "content": {"type": "tool_use", "name": "x", "input": {}}},                # one block, NOT in a list
        {"uuid": "l3", "sender": "assistant", "text": "SECRET-NUMBER", "created_at": True, "content": 7}]}
    lp2 = os.path.join(T, "lone.json")
    json.dump([lone], open(lp2, "w"))
    meta, msgs = C.read_claude_conversation(lp2, 0)
    texts = "\n".join(m["text"] for m in msgs)
    check("a lone tool block (a dict, not a list) or a number as content never lets top-level text in as her words",
          "SECRET" not in texts, texts)
    check("a created_at of true is no time (it read as 1970)", all(m["ts"] != 1 for m in msgs), [m["ts"] for m in msgs])
    r = run("draft-claude", zpath, "x", "Wren", os.path.join(T, "badnum"))
    check("a conversation 'number' that is not a number: a plain refusal", r.returncode != 0
          and "refused: the conversation number must be a number" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-100:])
    print("\n  -- Haiku's third pass, 11-07: an ambiguous file is never guessed at --")

    def read_chat(chat, leaf=None, name="r3"):
        c = {"uuid": name, "name": name, "chat_messages": chat}
        if leaf:
            c["current_leaf_message_uuid"] = leaf
        p = os.path.join(T, name + ".json")
        json.dump([c], open(p, "w"))
        meta, msgs = C.read_claude_conversation(p, 0)
        return [m["text"] for m in msgs], meta["resolution_notes"]

    def m3(uid, who, text, parent=None):
        d = {"uuid": uid, "sender": "human" if who == "h" else "assistant", "text": text}
        if parent is not None:
            d["parent_message_uuid"] = parent
        return d

    unknown = lambda notes: any("does not say clearly which branch" in n for n in notes)
    t, n = read_chat([m3("u0", "h", "U0"), m3("a0", "a", "A0", "u0"), m3("u1", "h", "U1", "a0"),
                      m3("a1", "a", "A1 shown", "u1"), m3("a1", "a", "A1 OLD dup", "u1")], leaf="a1", name="dup")
    check("two messages with ONE id: no copy picked; all kept, in file order, and SAID", unknown(n)
          and "A1 shown" in t and "A1 OLD dup" in t, (t, n[:1]))
    t, n = read_chat([m3("u1", "h", "OLD OPENER"), m3("a1", "a", "A-old", "u1"), m3("u1b", "h", "NEW OPENER"),
                      m3("a1b", "a", "A-new", "u1b"), m3("u2", "h", "U2", "a1b"), m3("a2", "a", "A2", "u2"),
                      m3("a2b", "a", "A2b", "u2")], leaf="a2b", name="opener")
    check("an abandoned first message (something replies to it) is never pulled in front",
          t == ["NEW OPENER", "A-new", "U2", "A2b"], t)
    t, n = read_chat([m3("u1", "h", "OLD OPENER"), m3("a1", "a", "A-old", "u1"), m3("u1b", "h", "NEW OPENER"),
                      m3("a1b", "a", "A-new", "u1b"), m3("u2", "h", "U2", "a1b"), m3("a2", "a", "A2", "u2")],
                     name="opener2")
    check("…the same with no later fork (two first messages, each answered): still one branch, never interleaved",
          t == ["NEW OPENER", "A-new", "U2", "A2"], t)
    t, n = read_chat([m3("o", "h", "OPENER"), m3("u0", "h", "U0", "gone"), m3("a0", "a", "A0", "u0"),
                      m3("u1", "h", "U1", "a0"), m3("a1", "a", "A1", "u1"), m3("a1b", "a", "A1b", "u1")],
                     leaf="a1", name="dangling")
    check("a parent missing from the file is the chat's start: the unlinked opening before it is KEPT",
          t == ["OPENER", "U0", "A0", "U1", "A1"], t)
    base = [m3("u0", "h", "U0"), m3("a0", "a", "A0", "u0"), m3("u1", "h", "U1", "a0"), m3("a1", "a", "A1", "u1"),
            m3("a1b", "a", "A1b", "u1")]
    t, n = read_chat(base + [{"sender": "assistant", "text": "T1", "parent_message_uuid": "a1"},
                             {"sender": "assistant", "text": "T2", "parent_message_uuid": "a1"}], leaf="a1", name="twotail")
    check("two unlabelled replies to the shown end: neither is chosen over the other; all kept and SAID",
          unknown(n) and "T1" in t and "T2" in t, (t, n[:1]))
    t, n = read_chat([m3("u0", "h", "U0"), m3("a0", "a", "A0", "u0"), m3("u1", "h", "U1", "a0"),
                      m3("a1", "a", "A1 self", "a1"), m3("u1b", "h", "U1b", "a0")], leaf="a1", name="selfloop")
    check("a message that is its own parent: the chat never collapses to one line; all kept and SAID",
          unknown(n) and len(t) == 5, (t, n[:1]))
    t, n = read_chat([m3("u0", "h", "a question"),
                      {"uuid": "e1", "sender": "assistant", "text": "TOP LEAK", "content": [{"type": "text", "text": ""}]},
                      {"uuid": "e2", "sender": "assistant", "text": "TOP LEAK 2", "content": [None]},
                      {"uuid": "e3", "sender": "assistant", "text": "x", "content": [{"text": "a block with no type"}]}],
                     name="emptyblocks")
    check("once a message HAS blocks, its top-level text is never used (an empty text block, a null block)",
          "TOP LEAK" not in "\n".join(t) and "a block with no type" in t, t)

    deepcrc = os.path.join(T, "deep_badcrc.zip")
    with zipfile.ZipFile(deepcrc, "w", zipfile.ZIP_STORED) as z:
        z.writestr("chats/conversations.json", json.dumps([{"author": "Elara", "text": "hi there"}]))
    blob = bytearray(open(deepcrc, "rb").read())
    i = blob.find(b"Elara")
    blob[i] ^= 0x20
    open(deepcrc, "wb").write(bytes(blob))
    check("an unreadable conversations.json DEEPER in a zip is not claimed for Claude (only the top-level one is)",
          V.detect_format(deepcrc) == "cai-official", V.detect_format(deepcrc))
    plain = {"uuid": "c-p", "name": "p", "chat_messages": [
        {"uuid": "p1", "sender": "human", "content": "hi there, plain content", "created_at": iso(0)},
        {"uuid": "p2", "sender": "assistant", "content": ["hello, a string block"], "created_at": iso(1)},
        {"uuid": "p3", "sender": "assistant", "text": "SECRET-TOOL-FALLBACK",
         "content": [{"type": "tool_use", "name": "x", "input": {}}], "created_at": iso(2)},
        "junk-entry"]}
    pp = os.path.join(T, "plain.json")
    json.dump([plain], open(pp, "w"))
    meta, msgs = C.read_claude_conversation(pp, 0)
    texts = [m["text"] for m in msgs]
    check("a content that is plain text, or a string block, is read as her/his words",
          texts[:2] == ["hi there, plain content", "hello, a string block"], texts)
    check("a turn that is ONLY a tool call never imports its top-level text as her words",
          "SECRET-TOOL-FALLBACK" not in texts, texts)
    check("…and the wordless turn and the non-message entry are both said",
          any("carried no words" in n for n in meta["resolution_notes"])
          and any("were not messages" in n for n in meta["resolution_notes"]), meta["resolution_notes"])
    two = os.path.join(T, "two_members.zip")
    with zipfile.ZipFile(two, "w") as z:
        z.writestr("old/conversations.json", json.dumps([{"x": 1}]))     # listed FIRST, deeper, not Claude's
        z.writestr("conversations.json", good)
    check("two conversations.json in one ZIP: the sniffer and the reader pick the SAME (top-most) one",
          V.detect_format(two) == "claude" and C.list_claude_conversations(two)[0]["lines"] == 24, V.detect_format(two))

    big = os.path.join(T, "big.zip")
    with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("conversations.json", json.dumps(export))
    saved, C.MAX_JSON_BYTES = C.MAX_JSON_BYTES, 64            # the bound, proven at a size a test can hold
    try:
        C.list_claude_conversations(big)
        check("an export that would unpack past the bound is refused, unread", False)
    except ValueError as e:
        check("an export that would unpack past the bound is refused, unread", "more than I will read" in str(e), str(e)[:70])
    finally:
        C.MAX_JSON_BYTES = saved

print("\n" + ("ALL PASS" if not fails else "%d FAILED:\n  " % len(fails) + "\n  ".join(fails)))
sys.exit(1 if fails else 0)
