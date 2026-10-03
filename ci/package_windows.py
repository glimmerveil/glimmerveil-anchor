#!/usr/bin/env python3
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, "dist")
NAME = "GlimmerveilAnchor"
ROOT = os.path.join(DIST, NAME)
PY_VERSION = os.environ.get("ANCHOR_PY_EMBED", "3.12.10")
PY_URL = "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (PY_VERSION, PY_VERSION)
ENGINE = "llama-cpp-python==0.3.34"
ENGINE_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_python(dest):
    os.makedirs(DIST, exist_ok=True)
    z = os.path.join(DIST, os.path.basename(PY_URL))
    if not os.path.isfile(z):
        with urllib.request.urlopen(PY_URL, timeout=120) as r, open(z + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(z + ".part", z)
    print("python embed %s  sha256 %s" % (os.path.basename(z), sha256(z)))
    with zipfile.ZipFile(z) as zf:
        zf.extractall(dest)
    tag = "python%s%s" % tuple(PY_VERSION.split(".")[:2])
    pth = os.path.join(dest, tag + "._pth")
    if not os.path.isfile(pth):
        raise SystemExit("FAIL no %s in the embeddable zip" % os.path.basename(pth))
    with open(pth, "w", encoding="ascii") as f:
        f.write("%s.zip\n.\nLib\\site-packages\n..\\app\\src\nimport site\n" % tag)


def install_engine(site_packages):
    if sys.version_info[:2] != tuple(int(x) for x in PY_VERSION.split(".")[:2]):
        raise SystemExit("FAIL packaging python %d.%d does not match the embedded %s (wheel ABI)"
                         % (sys.version_info[0], sys.version_info[1], PY_VERSION))
    os.makedirs(site_packages, exist_ok=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--only-binary=:all:",
                           "--target", site_packages, ENGINE, "--extra-index-url", ENGINE_INDEX])


def copy_app(app):
    src_out = os.path.join(app, "src")
    os.makedirs(src_out)
    for n in sorted(os.listdir(os.path.join(REPO, "src"))):
        if n.endswith(".py") and not n.startswith("test_"):
            shutil.copy2(os.path.join(REPO, "src", n), src_out)
    shutil.copytree(os.path.join(REPO, "docs"), os.path.join(app, "docs"))
    shutil.copytree(os.path.join(REPO, "examples"), os.path.join(app, "examples"))


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT)
    fetch_python(os.path.join(ROOT, "python"))
    install_engine(os.path.join(ROOT, "python", "Lib", "site-packages"))
    copy_app(os.path.join(ROOT, "app"))
    os.makedirs(os.path.join(ROOT, "models"))
    win = os.path.join(REPO, "packaging", "windows")
    shutil.copy2(os.path.join(win, "Anchor.bat"), ROOT)
    shutil.copy2(os.path.join(win, "README_WINDOWS.txt"), os.path.join(ROOT, "README.txt"))
    shutil.copy2(os.path.join(REPO, "LICENSE"), ROOT)
    with open(os.path.join(ROOT, "models", "PUT_YOUR_GGUF_HERE.txt"), "w", encoding="utf-8") as f:
        f.write("Put one ChatML / Qwen-family instruct model (.gguf) in this folder, then run Anchor.bat.\n")

    for bad in (".db", ".gguf", "card.json", ".veil"):
        for d, _, files in os.walk(ROOT):
            hit = [n for n in files if n.endswith(bad)]
            if hit:
                raise SystemExit("FAIL the package carries %s in %s" % (hit, d))

    out = os.path.join(DIST, "%s-windows-x64.zip" % NAME)
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for d, _, files in os.walk(ROOT):
            for n in files:
                p = os.path.join(d, n)
                zf.write(p, os.path.relpath(p, DIST))
    print("package %s  %.1f MB  sha256 %s" % (os.path.basename(out), os.path.getsize(out) / 1e6, sha256(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
