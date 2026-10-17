#!/usr/bin/env python3
"""Rung 1 — cleaning module: invented fixtures only.

Companions here are INVENTED (Marigold/Rowan). No real person's words.
Set TRANSFER_CLEANING_STUB=1 to run against the identity stub.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if os.environ.get("TRANSFER_CLEANING_STUB"):
    import cleaning_stub as C
else:
    import veil_intake_clean as C

fails = []


def check(label, ok, got=""):
    print("  %s  %-62s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def counts_ok(label, got, want):
    for k, v in want.items():
        check("%s count[%s]=%d" % (label, k, v), got.get(k, 0) == v, got.get(k, 0))


print("\nRUNG 1 — TRANSFERENCE CLEANING")
print("=" * 74)

# --- OOC aside: whole-line shapes removed, inline left alone ---
ooc_cases = [
    ("(OOC: Marigold is just a fixture)", "paren-colon"),
    ("((Rowan narrates quietly))", "double-paren"),
    ("[OOC] this is not in her voice", "bracket"),
    ("OOC: an old-style aside", "prefix"),
    ("  OOC: leading whitespace counts  ", "prefix-ws"),
]
for raw, tag in ooc_cases:
    out, c = C.clean_text(raw)
    check("OOC %s removed" % tag, out == "", repr(out))
    check("OOC %s counted" % tag, c["ooc_lines"] == 1, c)

mixed = "Keep this line.\n(OOC: drop this)\nKeep this too."
out, c = C.clean_text(mixed)
check("OOC only whole lines", out == "Keep this line.\nKeep this too.", repr(out))
check("OOC mixed count", c["ooc_lines"] == 1, c)

inline = "Say hello (OOC: not really) world."
out, c = C.clean_text(inline)
check("inline OOC left alone", out == inline, repr(out))
check("inline OOC not counted", c["ooc_lines"] == 0, c)

# --- HTML strip: tags + entities ---
html = "<b>hi</b> &amp; bye"
out, c = C.clean_text(html)
check("HTML tags stripped + entities decoded", out == "hi & bye", repr(out))
check("HTML tag count", c["html_tags"] == 2, c)
check("HTML entity count", c["html_entities"] == 1, c)

# --- Markdown structure strip ---
md = "# Hello\n## There\n[click here](http://example.com)\n![cute cat](cat.png)"
out, c = C.clean_text(md)
expected = "Hello\nThere\nclick here\ncute cat"
check("MD structure stripped", out == expected, repr(out))
check("MD header count", c["md_headers"] == 2, c)
check("MD link count", c["md_links"] == 1, c)
check("MD image count", c["md_images"] == 1, c)

comment = "before <!-- secret --> after"
out, c = C.clean_text(comment)
check("HTML comment removed", out == "before  after", repr(out))
check("HTML comment counted", c["md_comments"] == 1, c)

# --- Emote / punctuation byte-preservation ---
emote = "*hugs you*"
out, c = C.clean_text(emote)
check("asterisk emote preserved byte-exact", out == emote and c["md_links"] == 0, repr(out))

punct = "...!!"
out, c = C.clean_text(punct)
check("punctuation runs preserved byte-exact", out == punct, repr(out))

bold_md = "**strong** and _soft_"
out, c = C.clean_text(bold_md)
check("markdown emphasis never touched", out == bold_md, repr(out))

# --- Empty after cleaning ---
empty_ooc = "(OOC: alone)"
out, c = C.clean_text(empty_ooc)
check("empty-after-OOC dropped", out == "", repr(out))
check("empty-after-OOC counted", c["ooc_lines"] == 1 and c["emptied"] == 1, c)

empty_comment = "<!-- only -->"
out, c = C.clean_text(empty_comment)
check("empty-after-comment dropped", out == "", repr(out))
check("empty-after-comment counted", c["md_comments"] == 1 and c["emptied"] == 1, c)

# --- Combined counts ---
combo = "(OOC: drop)\n<b>hi</b> [see](url) ![alt](img) <!--note-->"
out, c = C.clean_text(combo)
check("combined: remaining text", out == "hi see alt", repr(out))
counts_ok("combined", c,
          {"ooc_lines": 1, "html_tags": 2, "html_entities": 0,
           "md_headers": 0, "md_links": 1, "md_images": 1,
           "md_comments": 1, "emptied": 0})

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  cleaning transformations proven, her voice untouched")
