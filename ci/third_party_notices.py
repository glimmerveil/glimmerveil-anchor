#!/usr/bin/env python3
"""THIRD-PARTY NOTICES for a build, from what the build actually installed (Opus 11-08: the voice builds of Anchor and the
Forge carried GPL/LGPL code without its licence text or source pointer; a hand-written list goes stale because the Windows
build does not pin versions, so the notices are read off the build itself).

    python ci/third_party_notices.py --out <dir> [--tag vX.Y.Z] [--extra NAME=TEXT ...] <site-packages dir> [...]

Writes <dir>/THIRD_PARTY_NOTICES.md and <dir>/licenses/<name>-<version>/ (every licence/notice file each package ships).
Stdlib only, so it runs on the Windows CI and in the AppImage build alike. Exit 1 if a package's licence cannot be named.
"""
import argparse
import importlib.metadata as md
import os
import re
import shutil
import sys

# what some packages carry INSIDE them (native code built from another project), and its licence + exact source. Versioned:
# a package version not mapped here, or a bundled library whose version cannot be read, STOPS the build (Haiku 11-08: notices
# naming the wrong library version are worse than none; the Windows build does not pin its voice packages)
ESPEAK_IN_LOADER = {"0.2.4": ("1.52.0", "146599e29be31bf17d99f0bcb7dbb2f92aef3d95")}   # loader version -> (eSpeak NG tag, loader commit)


def embedded(key, d):
    if key == "espeakng-loader":
        if d.version not in ESPEAK_IN_LOADER:
            raise SystemExit("FAIL espeakng-loader %s: which eSpeak NG it bundles is not mapped (ESPEAK_IN_LOADER)" % d.version)
        tag, commit = ESPEAK_IN_LOADER[d.version]
        return [("eSpeak NG %s (libespeak-ng and espeak-ng-data)" % tag, "GPL-3.0-or-later",
                 "https://github.com/espeak-ng/espeak-ng/archive/refs/tags/%s.tar.gz (the tag the loader's CI clones), and the scripts "
                 "that built it: https://github.com/thewh1teagle/espeakng-loader/archive/%s.tar.gz (build.sh and "
                 ".github/workflows/build.yml; cmake -DBUILD_SHARED_LIBS=ON -DCOMPILE_INTONATIONS=OFF)" % (tag, commit))]
    if key == "soundfile":
        ver = None
        for f in d.files or []:
            s = str(f).replace("\\", "/")
            if "_soundfile_data/" in s and "sndfile" in s.lower() and not s.endswith((".py", ".pyc", ".txt", ".md")):
                try:
                    m = re.search(rb"libsndfile-(\d+\.\d+\.\d+)", open(d.locate_file(f), "rb").read())
                    if m:
                        ver = m.group(1).decode(); break
                except OSError:
                    pass
        if not ver:
            raise SystemExit("FAIL soundfile %s: the bundled libsndfile's version could not be read" % d.version)
        return [("libsndfile %s (the shared library in _soundfile_data/)" % ver, "LGPL-2.1-or-later",
                 "https://github.com/libsndfile/libsndfile/releases/download/%s/libsndfile-%s.tar.xz (built by "
                 "https://github.com/bastibe/libsndfile-binaries); a separate shared library you may replace with your own build" % (ver, ver))]
    return {
        "sounddevice": [("PortAudio (Windows: the DLL in _sounddevice_data/)", "MIT", "https://github.com/PortAudio/portaudio; licenses/PortAudio-LICENSE.txt")],
        "pywhispercpp": [("whisper.cpp (compiled in)", "MIT", "https://github.com/ggml-org/whisper.cpp; licenses/whisper.cpp-LICENSE.txt")],
        "llama-cpp-python": [("llama.cpp / ggml (compiled in)", "MIT", "https://github.com/ggml-org/llama.cpp; licenses/llama.cpp-LICENSE.txt")],
    }.get(key, [])
# packages whose wheel declares no licence, named from their own repository (checked by hand, 11-08)
KNOWN = {
    "espeakng-loader": "MIT (the loader's code, per its repository; the wheel itself declares none: licenses/espeakng-loader-LICENSE.txt) "
                       "+ eSpeak NG inside it, GPL-3.0-or-later (below)",
}
COPYLEFT = re.compile(r"\b(A?GPL|LGPL|MPL|EPL|CDDL|GNU (Lesser |Library |Affero )?General Public)", re.I)
LICENSE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS|ThirdPartyNotices)[^/]*$", re.I)


def licence_of(d):
    m = d.metadata
    expr = (m.get("License-Expression") or "").strip()
    if expr:
        return expr
    lic = (m.get("License") or "").strip()
    if re.fullmatch(r"(unknown|none|n/?a|other|proprietary)( licen[cs]e)?", lic, re.I):   # (a placeholder is no licence: Haiku 11-08)
        lic = ""
    cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")
           and not re.search(r"OSI Approved$|Other/Proprietary", c)]
    if lic and len(lic) < 80 and "\n" not in lic:
        return lic
    if cls:
        return " / ".join(cls)
    if lic:                                                             # (a whole licence text in the field: name it by its first line)
        first = lic.splitlines()[0].strip()
        return first[:80] if re.search(r"\b(MIT|BSD|Apache|ISC|Mozilla|GNU|GPL|PSF|Python Software|Unlicense)\b", first, re.I) else ""
    return ""


def licence_files(d):
    out = []
    for f in d.files or []:
        s = str(f).replace("\\", "/")
        if ".dist-info/" in s and (LICENSE_FILE.search(s) or "/licenses/" in s):
            out.append(f)
        elif "/" in s and LICENSE_FILE.search(s) and not s.endswith((".py", ".pyc")):   # (notices a package keeps beside its code)
            out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--extra", action="append", default=[], help="NAME=one line, for parts that are not Python packages")
    ap.add_argument("--common", default="", help="a folder of licence texts copied whole into licenses/ (GPL-3.0, LGPL-2.1)")
    ap.add_argument("--sources-attached", action="store_true",
                    help="only when ci/fetch_copyleft_sources.py's output IS attached to the release named by --tag")
    ap.add_argument("sites", nargs="+")
    a = ap.parse_args()
    dists = {}
    for d in md.distributions(path=a.sites):
        name = (d.metadata.get("Name") or "").strip()
        if name and name.lower() not in dists:
            dists[name.lower()] = d
    if not dists:
        sys.exit("FAIL no packages found in %s" % a.sites)
    lic_dir = os.path.join(a.out, "licenses")
    shutil.rmtree(lic_dir, ignore_errors=True)
    os.makedirs(lic_dir)
    if a.common:
        for n in sorted(os.listdir(a.common)):
            if os.path.isfile(os.path.join(a.common, n)):
                shutil.copy2(os.path.join(a.common, n), os.path.join(lic_dir, n))
    rows, copyleft, unnamed = [], [], []
    for key in sorted(dists):
        d = dists[key]
        name, ver = d.metadata["Name"], d.version
        lic = licence_of(d) or KNOWN.get(key, "")
        if not lic:                                                     # (no licence field: its own licence file names it)
            for f in licence_files(d):
                try:
                    first = next((l.strip() for l in open(d.locate_file(f), encoding="utf-8", errors="replace") if l.strip()), "")
                except OSError:
                    first = ""
                if re.search(r"\b(MIT|BSD|Apache|ISC|Mozilla|GNU|GPL|Unlicense|Public Domain|PSF|Python Software)\b", first, re.I):
                    lic = "%s (named by its licence file; the package declares none)" % first[:60]
                    break
        if not lic:
            unnamed.append("%s %s" % (name, ver))
        dest = os.path.join(lic_dir, "%s-%s" % (re.sub(r"[^A-Za-z0-9._-]", "_", name), ver))
        copied = []
        for f in licence_files(d):
            try:
                src = d.locate_file(f)
                if os.path.isfile(src):
                    os.makedirs(dest, exist_ok=True)
                    tgt = os.path.join(dest, os.path.basename(str(f)))
                    if os.path.exists(tgt):
                        tgt = os.path.join(dest, str(f).replace("\\", "/").replace("/", "__"))
                    shutil.copy2(src, tgt)
                    copied.append(os.path.basename(tgt))
            except OSError:
                pass
        home = d.metadata.get("Home-page") or next((u.split(",", 1)[1].strip() for u in (d.metadata.get_all("Project-URL") or [])
                                                  if re.match(r"(source|repository|homepage)", u, re.I)), "")
        rows.append((name, ver, lic or "UNNAMED", home, copied))
        if COPYLEFT.search(lic) and key not in KNOWN:                    # (a KNOWN package's copyleft part is its embedded entry)
            copyleft.append((name, ver, lic, "the package's own sdist on PyPI: https://pypi.org/project/%s/%s/#files" % (name, ver)))
        for part, plic, src in embedded(key, d):
            if COPYLEFT.search(plic):
                copyleft.append(("%s, inside %s %s" % (part, name, ver), "", plic, src))
            rows.append(("  ↳ " + part, "", plic, src, []))
    lines = ["# Third-party notices", "",
             "This build of Glimmerveil Anchor is Apache-2.0 (see LICENSE). It also contains the open-source parts below, each under "
             "its own licence, exactly as this build installed them%s. The licence and notice files each part ships, and the "
             "texts named below for parts whose packages carry none, are in `licenses/`." %
             (" (release %s)" % a.tag if a.tag else ""), ""]
    if copyleft:
        lines += ["## Copyleft parts (GPL / LGPL / MPL): their source", "",
                  "These are free software under copyleft licences, included as separate parts, as built by their upstream "
                  "projects (named below); Glimmerveil changed nothing in them. You may get their complete source from the places "
                  "named (the exact versions this build used)%s, and the copyleft licence texts are in `licenses/`. For a copy on "
                  "request, for at least three years: glimmerveilAI@proton.me." %
                  ("; a copy of each is also attached to https://github.com/glimmerveil/glimmerveil-anchor/releases/tag/%s" % a.tag
                   if a.tag and a.sources_attached else ""), ""]
        for c in copyleft:
            name, ver, lic, src = (c[0], c[1], c[2], c[3])
            lines.append("- **%s%s**: %s. Source: %s" % (name, (" " + ver) if ver else "", lic, src))
        lines.append("")
    lines += ["## Every part", "", "| part | version | licence | where from | licence files |", "|---|---|---|---|---|"]
    for name, ver, lic, home, copied in rows:
        lines.append("| %s | %s | %s | %s | %s |" % (name, ver, lic.replace("|", "/"), home, ", ".join(copied) or ""))
    for e in a.extra:
        n, _, t = e.partition("=")
        lines.append("| %s |  | %s |  |  |" % (n, t))
    lines.append("")
    with open(os.path.join(a.out, "THIRD_PARTY_NOTICES.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("notices: %d packages, %d copyleft parts, licences in %s" % (len(dists), len(copyleft), lic_dir))
    if unnamed:
        sys.exit("FAIL no licence could be named for: %s" % ", ".join(unnamed))


if __name__ == "__main__":
    main()
