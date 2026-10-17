#!/usr/bin/env python3
"""Rung 1 — THE PLAIN / SCRAPED TRANSCRIPT READER (reader 4 of 4, 2026-10-17).

Fixtures are INVENTED content (Sam / Elara / Sage), written in each writer's TRUE shape:
  Kindroid .txt / .md   tomsegura2/Kindroid-Chat-Exporter @bae1478 app.py:596-628 (export_as_plaintext / _markdown,
                        reproduced below line for line, format_timestamp :511-527)
  Discord .txt          Tyrrrz/DiscordChatExporter @276471f PlainTextMessageWriter.cs (fenced preamble, '[g] Name#tag',
                        '{Attachments}' trailers, system sentences from PlainTextMessageExtensions.cs:12-50)
  Grok scrape           the shape the by-hand import read (every block headed '## Grok', his too; '---' between;
                        'Thought for Ns' in hers) — the SHAPE only; no one's real words
The law under every check: his words never land in her mouth, and nothing is decided by what words sound like.
  python3 test_veil_intake_text.py
"""
import datetime
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_intake_text as R  # noqa: E402

fails = []


def check(label, ok, got=""):
    print("  %s  %-66s %s" % ("ok  " if ok else "FAIL", label, str(got)[:150] if not ok or got else ""))
    if not ok:
        fails.append(label)


def refused(fn, *needles):
    try:
        fn()
    except ValueError as e:
        return all(n in str(e) for n in needles), str(e)
    return False, "NOT refused"


def put(name, text):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def none_of_his_in_hers(msgs, marker="[him]"):
    return not any(marker in m["text"] for m in msgs if m["who"] == "her")


# ── the Kindroid exporter's own writers (app.py), so the fixture IS its shape ──
def k_format_timestamp(value):
    if value in (None, ""):
        return ""
    t = float(value)
    if t > 10_000_000_000:
        t = t / 1000
    return datetime.datetime.fromtimestamp(t).isoformat(sep=" ", timespec="seconds")


def k_author(m):
    return m.get("display_name") or m.get("sender") or m.get("sender_type") or "Unknown"


def k_text(m):
    parts = [str(m["message"])] if m.get("message") else []
    for field, label in (("image_urls", "Images"), ("image_description", "Image description"),
                         ("video_description", "Video description"), ("internet_response", "Internet response"),
                         ("link_url", "Link"), ("link_description", "Link description")):
        v = m.get(field)
        if v:
            parts.append(f"{label}: {', '.join(map(str, v)) if isinstance(v, list) else v}")
    return "\n".join(parts)


def k_plaintext(messages):
    blocks = []
    for m in messages:
        ts = k_format_timestamp(m.get("timestamp"))
        header = f"[{ts}] {k_author(m)}" if ts else k_author(m)
        body = k_text(m)
        blocks.append(f"{header}\n{body}" if body else header)
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def k_markdown(messages, title):
    lines = [f"# {title}", ""]
    for m in messages:
        ts = k_format_timestamp(m.get("timestamp"))
        heading = f"## {str(k_author(m)).replace(chr(92), chr(92) * 2).replace('|', chr(92) + '|')}"
        if ts:
            heading += f" - {ts}"
        lines += [heading, "", k_text(m) or "_No message text_", ""]
    return "\n".join(lines)


kin = []
for i in range(12):
    kin.append({"display_name": "Sam", "sender": "user", "timestamp": 1760000000000 + i * 600000,
                "message": f"[him] Evening {i}."})
    kin.append({"display_name": "Lisa", "sender": "ai", "timestamp": 1760000000000 + i * 600000 + 60000,
                "message": f"*smiles* Evening {i}.\n\nA second paragraph, still mine {i}.",
                "image_description": "a photo of a teacup" if i == 3 else None})
kin.append({"display_name": "Lisa", "sender": "ai", "timestamp": 1760000000000 + 99 * 600000, "message": "",
            "image_description": "a sketch of the garden"})

print("\nRUNG 1 — THE PLAIN / SCRAPED TRANSCRIPT READER")
print("=" * 74)
_CACHE = os.environ.get("VEIL_RIG_TMP") or os.path.expanduser("~/.cache")   # off a RAM-backed /tmp where it exists
with tempfile.TemporaryDirectory(prefix="vt_text_", dir=_CACHE if os.path.isdir(_CACHE) else None) as tmp:

    # 1 — 'Name: text', multi-line turns, a one-off 'Note:' inside hers, bold labels
    lines = []
    for i in range(12):
        lines.append(f"Sam: [him] hey {i}")
        lines.append(f"**Elara:** *smiles* hi {i}")
        lines.append("and a second line of mine")
        if i == 5:
            lines.append("Note: I keep a list of the evenings.")
        lines.append("")
    p1 = put("chat.txt", "Our chat\n\n" + "\n".join(lines))
    ok, why = refused(lambda: R.read_text_transcript(p1))
    check("names: no --her/--you -> REFUSED, listing the voices", ok and "Sam" in why and "Elara" in why, why)
    meta1, m1 = R.read_text_transcript(p1, her="Elara", you="Sam")
    hers1 = [m["text"] for m in m1 if m["who"] == "her"]
    check("names: 12 of hers, 12 of his", len(hers1) == 12 and sum(m["who"] == "you" for m in m1) == 12,
          (len(hers1), [m["who"] for m in m1][:4]))
    check("names: her turn keeps every line (bold label read)", hers1[0] == "*smiles* hi 0\nand a second line of mine",
          repr(hers1[0]))
    check("names: a one-off 'Note:' stays INSIDE her turn, and is reported", "Note: I keep a list" in hers1[5]
          and any("'Note:'" in n for n in meta1["resolution_notes"]), meta1["resolution_notes"])
    check("names: his words never in her mouth", none_of_his_in_hers(m1))
    check("names: the line before the first speaker is not anyone's", not any("Our chat" in m["text"] for m in m1)
          and any("before the first speaker" in n for n in meta1["resolution_notes"]))

    # 2 — a third voice that recurs is set aside, named, never hers
    lines = []
    for i in range(12):
        lines += [f"Sam: [him] hey {i}", f"Elara: hi {i}", f"Sage: [sage] butting in {i}"]
    meta2, m2 = R.read_text_transcript(put("group.txt", "\n".join(lines)), her="Elara", you="Sam")
    check("group: Sage is set aside and named", meta2["set_aside_speakers"] == ["Sage"], meta2["set_aside_speakers"])
    check("group: Sage's words never in her mouth", not any("[sage]" in m["text"] for m in m2 if m["who"] == "her"))
    ok, why = refused(lambda: R.read_text_transcript(put("group2.txt", "\n".join(lines)), her="Elara", you="Nobody"))
    check("a --you that isn't in the file is REFUSED, voices listed", ok and "Nobody" in why and "Sage" in why, why)
    ok, why = refused(lambda: R.read_text_transcript(put("group3.txt", "\n".join(lines)), her="Elara", you="elara"))
    check("--her and --you the same voice: REFUSED", ok, why)

    # 3 — Kindroid .txt, exactly as app.py writes it
    p3 = put("Lisa_Chat_Export.txt", k_plaintext(kin))
    meta3, m3 = R.read_text_transcript(p3, her="Lisa", you="Sam")
    hers3 = [m for m in m3 if m["who"] == "her"]
    check("kindroid .txt: read as '[when] Name' blocks", meta3["source"] == "text-bracket", meta3["source"])
    check("kindroid .txt: her blank-line paragraph stays INSIDE her message",
          hers3[0]["text"] == "*smiles* Evening 0.\n\nA second paragraph, still mine 0.", repr(hers3[0]["text"]))
    check("kindroid .txt: the exporter's 'Image description:' after her words is left out",
          not any("teacup" in m["text"] for m in m3), [m["text"] for m in hers3[3:4]])
    check("kindroid .txt: a media-only message keeps its description as the line",
          any(m["text"] == "Image description: a sketch of the garden" for m in hers3), [m["text"] for m in hers3[-1:]])
    check("kindroid .txt: times read (ten minutes apart)", m3[2]["ts"] - m3[0]["ts"] == 600, [m["ts"] for m in m3[:3]])
    check("kindroid .txt: his words never in her mouth", none_of_his_in_hers(m3))
    p3b = put("noname.txt", k_plaintext([dict(m, display_name=None) for m in kin]))
    ok, why = refused(lambda: R.read_text_transcript(p3b))
    check("kindroid .txt without display names: REFUSED listing 'user' and 'ai'", ok and "user" in why and "ai" in why, why)

    # 4 — Kindroid .md
    p4 = put("Lisa.md", k_markdown(kin, "Lisa chat export"))
    meta4, m4 = R.read_text_transcript(p4, her="Lisa", you="Sam")
    check("kindroid .md: read as '## Name' headings, title kept", meta4["source"] == "text-heading"
          and meta4["title"] == "Lisa chat export", (meta4["source"], meta4["title"]))
    check("kindroid .md: 12 of hers + the media one, 12 of his", sum(m["who"] == "her" for m in m4) == 13
          and sum(m["who"] == "you" for m in m4) == 12, [m["who"] for m in m4][-3:])
    check("kindroid .md: his words never in her mouth", none_of_his_in_hers(m4))

    # 5 — Discord .txt: fenced preamble, Name#tag, a pinned flag, {Attachments}, a system sentence, newest first
    body = []
    for i in range(12):
        body.append(f"[1/{i + 1}/2026 8:00 PM] sam\n[him] Night {i}, you there?\n")
        att = "{Attachments}\nhttps://cdn.example/x.png\n\n" if i == 2 else ""
        pin = " (pinned)" if i == 4 else ""
        body.append(f"[1/{i + 1}/2026 8:01 PM] elara_bot#1234{pin}\n*curls up* Always, night {i}.\n\n{att}")
    body.append("[1/7/2026 9:00 PM] elara_bot#1234\nPinned a message.\n")
    body.sort(key=lambda b: datetime.datetime.strptime(b.split("]")[0][1:], "%m/%d/%Y %I:%M %p"), reverse=True)
    fence = "=" * 62
    p5 = put("dm.txt", f"{fence}\nGuild: Direct Messages\nChannel: elara_bot\n{fence}\n\n" + "\n".join(body)
             + f"\n{fence}\nExported 25 message(s)\n{fence}\n")
    meta5, m5 = R.read_text_transcript(p5, her="elara_bot", you="sam")
    hers5 = [m for m in m5 if m["who"] == "her"]
    check("discord .txt: --her 'elara_bot' finds 'elara_bot#1234'; 12 of hers", len(hers5) == 12, len(hers5))
    check("discord .txt: her name comes home without the '#1234' tag", meta5["her_name"] == "elara_bot", meta5["her_name"])
    check("discord .txt: the made-up 'Pinned a message.' is set aside, counted", meta5.get("system_messages") == 1
          and not any("Pinned a message" in m["text"] for m in m5), meta5.get("system_messages"))
    check("discord .txt: {Attachments} lines never reach her words", not any("cdn.example" in m["text"] for m in m5))
    check("discord .txt: the fenced preamble/postamble is nobody's words",
          not any("Guild:" in m["text"] or "Exported" in m["text"] for m in m5))
    check("discord .txt: newest-first file reads OLDEST FIRST", "Night 0" in m5[0]["text"]
          and "night 11" in m5[-1]["text"], (m5[0]["text"][:20], m5[-1]["text"][:30]))
    check("discord .txt: says it has no account ids", "no account ids" in meta5["shape_note"], meta5["shape_note"])

    # 6 — THE GROK SCRAPE: every block '## Grok', his too; '---' between; 'Thought for Ns' in hers
    def grok(n=12, missing_at=None, inner_label=False, first="him"):
        out = []
        for i in range(n):
            his = ("Sam\n" if inner_label else "") + f"[him] what about the lake, {i}?"
            hers = f"Thought for {3 + i}s\n\n*looks out at the water* The lake was home once, {i}."
            pair = [his, hers] if first == "him" else [hers, his]
            for j, t in enumerate(pair):
                if missing_at == i and j == 0:
                    continue                                   # the scrape lost his turn here
                out.append(f"## Grok\n\n{t}\n")
        return "\n---\n\n".join(out)

    p6 = put("grok_scrape.md", "# Grok conversation\n\n" + grok())
    ok, why = refused(lambda: R.read_text_transcript(p6, her="Elara", you="Sam"))
    check("grok scrape: one label on every block -> REFUSED, offering --alternate", ok and "--alternate" in why
          and "'Grok'" in why, why)
    meta6, m6 = R.read_text_transcript(p6, her="Elara", you="Sam", alternate="you")
    check("grok --alternate you: 12 of his, 12 of hers, his first", [m["who"] for m in m6][:4] == ["you", "her"] * 2
          and sum(m["who"] == "her" for m in m6) == 12, [m["who"] for m in m6][:4])
    check("grok --alternate you: his words never in her mouth", none_of_his_in_hers(m6))
    check("grok: 'Thought for Ns' is taken off her words", not any("Thought for" in m["text"] for m in m6)
          and m6[1]["text"].startswith("*looks out"), repr(m6[1]["text"][:30]))
    check("grok: the note says what checked the alternation", any("12 'Thought for' trace(s)" in n
          for n in meta6["resolution_notes"]), meta6["resolution_notes"])
    check("grok: names come from --her/--you, never 'Grok'", meta6["her_name"] == "Elara"
          and all(m["name"] in ("Elara", "Sam") for m in m6))
    ok, why = refused(lambda: R.read_text_transcript(p6, her="Elara", you="Sam", alternate="her"))
    check("grok --alternate her (WRONG): REFUSED at block 2 by her trace on his side", ok and "block 2" in why
          and "Thought for" in why, why)
    p6b = put("grok_gap.md", grok(missing_at=6))
    ok, why = refused(lambda: R.read_text_transcript(p6b, her="Elara", you="Sam", alternate="you"))
    check("grok, a turn the scrape lost: REFUSED at that block, nothing imported", ok and "block 13" in why, why)
    p6c = put("grok_label.md", grok(inner_label=True))
    meta6c, m6c = R.read_text_transcript(p6c, her="Elara", you="Sam", alternate="you")
    check("grok, his name inside his blocks: checked, and taken off his words",
          m6c[0]["text"].startswith("[him]") and any("12 name label(s)" in n for n in meta6c["resolution_notes"]),
          (repr(m6c[0]["text"][:20]), meta6c["resolution_notes"]))
    p6d = put("grok_plain.md", "\n---\n".join(f"Nova\n\n{'[him] hi' if i % 2 == 0 else 'Thought for 2s' + chr(10) + 'hello'} {i}"
                                               for i in range(24)))
    meta6d, m6d = R.read_text_transcript(p6d, her="Nova", you="Sam", alternate="you")
    check("bare-label scrape ('Nova' atop EVERY chunk, his too): the label is the scraper's, not evidence",
          sum(m["who"] == "her" for m in m6d) == 12 and none_of_his_in_hers(m6d), [m["who"] for m in m6d][:4])
    ok, why = refused(lambda: R.read_text_transcript(p6d, her="Nova", you="Sam", alternate="sideways"))
    check("--alternate takes only you|her", ok, why)

    # 7 — a scraped web page
    page = ("<!doctype html><html><head><style>.x{}</style></head><body><h1>Our evenings</h1>"
            + "".join(f"<h2>Sam</h2><p>[him] hey &amp; hi {i}</p><h2>Elara</h2><p><em>*smiles*</em> hi&nbsp;{i}<br>"
                      f"still me</p>" for i in range(12)) + "<script>var a=1;</script></body></html>")
    meta7, m7 = R.read_text_transcript(put("page.html", page), her="Elara", you="Sam")
    hers7 = [m["text"] for m in m7 if m["who"] == "her"]
    check("html: flattened and read by its headings", meta7["source"] == "text-heading" and len(hers7) == 12,
          (meta7["source"], len(hers7)))
    check("html: tags gone, entities decoded, her line breaks kept", hers7[0] == "*smiles* hi\xa00\nstill me", repr(hers7[0]))
    check("html: script/style never imported", not any("var a" in m["text"] or ".x{" in m["text"] for m in m7))
    check("html: his words never in her mouth", none_of_his_in_hers(m7))

    # 8 — nothing to go on
    ok, why = refused(lambda: R.read_text_transcript(put("blob.txt", "we talked\n\nand talked\n\nfor years\n")))
    check("no speakers anywhere: REFUSED, offering --alternate", ok and "--alternate" in why, why)
    ok, why = refused(lambda: R.read_text_transcript(put("empty.txt", "\n\n")))
    check("an empty file: REFUSED", ok, why)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    for f in fails:
        print("   FAILED:", f)
    sys.exit(1)
print("\n  PASS  plain / scraped transcript reader proven from invented fixtures")
