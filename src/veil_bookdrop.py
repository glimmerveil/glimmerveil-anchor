#!/usr/bin/env python3
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import veil_roster
import veil_shelf
import veil_spine as spine

MIN_CHARS = 200

import re
_GUT_START = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)
_GUT_END = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)


def _strip_gutenberg(text):
    m = _GUT_START.search(text)
    if m:
        text = text[m.end():]
    m = _GUT_END.search(text)
    if m:
        text = text[:m.start()]
    return text.strip()


def _read_text(path):
    for enc in ("utf-8", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    return ""


def _epub_text(path):
    import html.parser
    import re
    import zipfile

    class _Text(html.parser.HTMLParser):
        SKIP = {"script", "style", "head", "title"}
        BREAK = {"p", "div", "br", "h1", "h2", "h3", "h4", "li", "tr", "section"}

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self._skip = [], 0

        def handle_starttag(self, tag, attrs):
            if tag in self.SKIP:
                self._skip += 1
            if tag in self.BREAK:
                self.out.append("\n")

        def handle_endtag(self, tag):
            if tag in self.SKIP and self._skip:
                self._skip -= 1

        def handle_data(self, data):
            if not self._skip:
                self.out.append(data)

    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            docs = [n for n in names if n.lower().endswith((".xhtml", ".html", ".htm"))]
            opf = next((n for n in names if n.lower().endswith(".opf")), None)
            if opf:
                try:
                    manifest = z.read(opf).decode("utf-8", "replace")
                    hrefs = dict(re.findall(r'id="([^"]+)"[^>]*href="([^"]+)"', manifest))
                    order = [hrefs.get(i) for i in re.findall(r'idref="([^"]+)"', manifest)]
                    base = os.path.dirname(opf)
                    ordered = [os.path.join(base, h).replace("\\", "/") for h in order if h]
                    ordered = [n for n in ordered if n in names]
                    if ordered:
                        docs = ordered
                except Exception:
                    pass
            parts = []
            for n in docs:
                p = _Text()
                p.feed(z.read(n).decode("utf-8", "replace"))
                parts.append("".join(p.out))
        text = "\n".join(parts)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:
        return ""


def _title_of(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    return base.replace("_", " ").replace("-", " ").strip()


def run(argv=None):
    active = veil_roster.active_peep()
    if not active:
        print("No one lives here yet — make her first (python3 veil_card.py).")
        return 1
    folder = active["folder_path"]
    drop = os.path.join(folder, "book_drop")
    done = os.path.join(drop, "shelved")
    os.makedirs(done, exist_ok=True)

    files = sorted(f for f in os.listdir(drop)
                   if os.path.isfile(os.path.join(drop, f)) and not f.endswith(".why.txt"))
    if not files:
        print(f"The drop is empty — put .txt, .md, or .pdf files in:\n  {drop}\nthen press "
              "this button again.")
        return 0

    conn = spine.open_db(active["db"])
    have = {r[0].strip().lower() for r in conn.execute("SELECT DISTINCT title FROM books")}
    shelved = skipped = refused = 0
    for name in files:
        path = os.path.join(drop, name)
        title = _title_of(name)
        ext = os.path.splitext(name)[1].lower()
        if title.lower() in have:
            print(f"  · skipped '{title}' — already on {active['name']}'s shelf")
            skipped += 1
            continue
        if ext in (".txt", ".md"):
            text = _read_text(path)
            reason = "" if len(text.strip()) >= MIN_CHARS else \
                "file is (nearly) empty — not a book"
        elif ext == ".epub":
            text = _epub_text(path)
            reason = "" if len(text.strip()) >= MIN_CHARS else \
                "couldn't read this epub — convert it to .txt by hand"
        elif ext == ".pdf":
            print(f"  · left '{name}' — PDFs are never auto-converted (the conversions come "
                  "out jumbled); convert it to .txt yourself, EYEBALL it, then drop the .txt")
            continue
        else:
            print(f"  · left '{name}' — .txt, .md, or .epub (PDFs by hand)")
            continue
        if reason:
            with open(path + ".why.txt", "w", encoding="utf-8") as f:
                f.write(f"Not shelved: {reason}\n")
            print(f"  · REFUSED '{title}' — {reason}")
            refused += 1
            continue
        got = veil_shelf.ingest_book(conn, title, _strip_gutenberg(text))
        if got:
            have.add(title.lower())
            shutil.move(path, os.path.join(done, name))
            shelved += 1
    conn.close()
    print(f"\n{shelved} shelved · {skipped} skipped (already hers) · {refused} refused "
          f"(see the .why.txt notes)")
    if shelved:
        print(f"{active['name']} will find them on her own — or hand her one tonight.")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
