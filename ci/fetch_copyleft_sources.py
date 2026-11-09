#!/usr/bin/env python3
"""The source of every copyleft part a build ships, ready to attach to its GitHub release (Opus 11-08).

    python ci/fetch_copyleft_sources.py <THIRD_PARTY_NOTICES.md> <out dir>

Reads the notices' "Copyleft parts" list (ci/third_party_notices.py) and downloads, for each part: a Python package's own
sdist from PyPI (the exact version), or the exact source archive its line names (eSpeak NG 1.52.0, libsndfile 1.2.2, ...).
Writes SHA256SUMS. Exit 1 if any part's source could not be fetched (a release must not go out claiming source it lacks).
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

notes, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
text = open(notes, encoding="utf-8").read()
block = text.split("## Copyleft parts", 1)[1].split("\n## ", 1)[0] if "## Copyleft parts" in text else ""
items = [l for l in block.splitlines() if l.startswith("- **")]
if not items:
    sys.exit("no copyleft parts listed: nothing to fetch")


def get(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "glimmerveil-anchor-ci"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest + ".part", "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(dest + ".part", dest)
    return dest


bad, got = [], []
for line in items:
    m = re.match(r"- \*\*(.+?)\*\*: (.+?)\. Source: (.+)$", line)
    if not m:
        bad.append(line[:80]); continue
    name, src = m.group(1), m.group(3)
    try:
        pm = re.search(r"https://pypi\.org/project/([^/]+)/([^/]+)/", src)
        if pm:
            pkg, ver = pm.group(1), pm.group(2)
            rel = json.load(urllib.request.urlopen("https://pypi.org/pypi/%s/%s/json" % (pkg, ver), timeout=60))
            sd = [u for u in rel["urls"] if u["packagetype"] == "sdist"]
            if not sd:
                raise RuntimeError("no sdist on PyPI")
            got.append(get(sd[0]["url"], os.path.join(out, sd[0]["filename"])))
        else:
            um = re.search(r"https://\S+?\.(?:tar\.gz|tar\.xz|zip)", src)
            if not um:
                raise RuntimeError("its line names no archive")
            url = um.group(0)
            got.append(get(url, os.path.join(out, url.rstrip("/").split("/")[-1] if "espeak-ng" not in url else "espeak-ng-" + url.split("/")[-1])))
        print("ok  ", name)
    except Exception as e:                                             # noqa: BLE001
        bad.append("%s: %s" % (name, e)); print("FAIL", name, e)
with open(os.path.join(out, "SHA256SUMS"), "w", encoding="utf-8") as f:
    for p in got:
        f.write("%s  %s\n" % (hashlib.sha256(open(p, "rb").read()).hexdigest(), os.path.basename(p)))
if bad:
    sys.exit("FAIL %d: %s" % (len(bad), "; ".join(bad)))
print("PASS %d sources in %s" % (len(got), out))
