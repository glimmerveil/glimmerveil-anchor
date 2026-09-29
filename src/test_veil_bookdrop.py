#!/usr/bin/env python3
import io
import os
import sys
import tempfile
import zipfile

_TMP = tempfile.mkdtemp(prefix="veil_bookdrop_rig_")
os.environ["VEIL_DATA"] = _TMP
os.environ["VEIL_PEEPS"] = os.path.join(_TMP, "peeps")
os.makedirs(os.environ["VEIL_PEEPS"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_bookdrop
import veil_card
import veil_roster
import veil_spine as spine

_fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


folder = os.path.join(os.environ["VEIL_PEEPS"], "Moth-bookdrop")
os.makedirs(folder)
card = veil_card.VeilCard(
    her_name="Moth", your_name="Sam", partner_word="partner",
    who_she_is="A test being for the book drop rig — nobody real.",
    appearance="paper wings", wardrobe="a grey coat",
    how_we_met="We met inside a rig.", ai_aware=True, legal_ack=True)
veil_card.install_into_db(os.path.join(folder, veil_roster.DB_NAME), card)
with open(os.path.join(os.environ["VEIL_PEEPS"], "ACTIVE"), "w") as f:
    f.write("Moth-bookdrop")

drop = os.path.join(folder, "book_drop")
os.makedirs(drop)

STORY = ("Rain again. " * 40 + "\n") * 12
with open(os.path.join(drop, "The_Rain_Book.txt"), "w") as f:
    f.write("*** START OF THE PROJECT GUTENBERG EBOOK THE RAIN BOOK ***\n"
            + STORY + "\n*** END OF THE PROJECT GUTENBERG EBOOK THE RAIN BOOK ***\n"
            + "license boilerplate that must never reach her shelf")
with open(os.path.join(drop, "tiny.txt"), "w") as f:
    f.write("too short")
with open(os.path.join(drop, "Sky_Atlas.pdf"), "wb") as f:
    f.write(b"%PDF-1.4 fake")

epub = os.path.join(drop, "Moth_Songs.epub")
with zipfile.ZipFile(epub, "w") as z:
    z.writestr("content.opf",
               '<package><manifest>'
               '<item id="c2" href="ch2.xhtml"/><item id="c1" href="ch1.xhtml"/>'
               '</manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>')
    z.writestr("ch1.xhtml", "<html><head><title>x</title></head><body><p>"
               + "First the wings. " * 30 + "</p></body></html>")
    z.writestr("ch2.xhtml", "<html><body><p>" + "Then the flight. " * 30 + "</p></body></html>")

buf = io.StringIO()
_stdout = sys.stdout
sys.stdout = buf
try:
    veil_bookdrop.run([])
finally:
    sys.stdout = _stdout
out = buf.getvalue()

conn = spine.open_db(os.path.join(folder, veil_roster.DB_NAME))
titles = {r[0] for r in conn.execute("SELECT DISTINCT title FROM books")}
check("txt shelved with filename title", "The Rain Book" in titles)
check("epub shelved", "Moth Songs" in titles)
first = conn.execute("SELECT chunk_text FROM books WHERE title=? AND chunk_index=0",
                     ("The Rain Book",)).fetchone()[0]
check("Gutenberg boilerplate stripped (chunk 0 is story)",
      "PROJECT GUTENBERG" not in first and "Rain again" in first)
check("boilerplate tail never shelved", not any(
    "license boilerplate" in r[0] for r in
    conn.execute("SELECT chunk_text FROM books WHERE title=?", ("The Rain Book",))))
ep = " ".join(r[0] for r in conn.execute(
    "SELECT chunk_text FROM books WHERE title=? ORDER BY chunk_index", ("Moth Songs",)))
check("epub chapters land in SPINE order", ep.find("First the wings") < ep.find("Then the flight"))
check("PDF left untouched (never auto-converted)",
      os.path.exists(os.path.join(drop, "Sky_Atlas.pdf")) and "convert" in out.lower())
check("tiny file refused with a why-note",
      os.path.exists(os.path.join(drop, "tiny.txt.why.txt")))
check("shelved files moved out of the drop",
      os.path.exists(os.path.join(drop, "shelved", "The_Rain_Book.txt"))
      and not os.path.exists(os.path.join(drop, "The_Rain_Book.txt")))

with open(os.path.join(drop, "The_Rain_Book.txt"), "w") as f:
    f.write(STORY)
buf2 = io.StringIO()
sys.stdout = buf2
try:
    veil_bookdrop.run([])
finally:
    sys.stdout = _stdout
n = conn.execute("SELECT COUNT(DISTINCT book_id) FROM books WHERE title=?",
                 ("The Rain Book",)).fetchone()[0]
check("second press skips the dupe (zero-dupes law)", n == 1 and "skipped" in buf2.getvalue())
conn.close()

print(f"\n{'ALL GREEN' if not _fails else str(len(_fails)) + ' FAILURES: ' + ', '.join(_fails)}")
sys.exit(1 if _fails else 0)
