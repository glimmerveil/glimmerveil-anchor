#!/usr/bin/env python3
"""Put her brain into a Forge shell: forge_add_brain.py [--overlay DIR] <shell.zip> <model.gguf> <out.zip> [licence-note]

A .gguf is the same file on every OS, so this runs anywhere (the laptop, the Deck). The shell comes from
`package_windows.py --forge` on a Windows runner. The model is stored uncompressed (zip64), then read
back and hashed against the source before the zip is called good.

--overlay DIR: every file under DIR replaces (or adds) the same path under GlimmerveilForge/ — the product's
own files that do not live in this repository. Replaced, never appended: the zip never holds two copies.
"""
import hashlib
import os
import shutil
import sys
import zipfile

ROOT = "GlimmerveilForge"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _overlay_files(odir):
    got = {}
    for base, _, files in os.walk(odir):
        for fn in files:
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, odir).replace(os.sep, "/")
            got[f"{ROOT}/{rel}"] = full
    return got


def main(argv):
    overlay = {}
    if len(argv) > 2 and argv[1] == "--overlay":
        overlay = _overlay_files(argv[2])
        if not overlay:
            raise SystemExit("FAIL the overlay folder is empty: %s" % argv[2])
        argv = argv[:1] + argv[3:]
    if len(argv) not in (4, 5):
        print(__doc__)
        return 2
    shell, model, out = argv[1:4]
    note = argv[4] if len(argv) == 5 else ""
    with zipfile.ZipFile(shell) as z:
        names = z.namelist()
    if f"{ROOT}/Forge.bat" not in names:
        raise SystemExit("FAIL that is not a Forge shell (no %s/Forge.bat)" % ROOT)
    if any(n.endswith(".gguf") for n in names):
        raise SystemExit("FAIL the shell already carries a brain")
    want = sha256_file(model)
    tmp = out + ".part"
    if overlay:
        with zipfile.ZipFile(shell) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as dst:
            for info in src.infolist():
                if info.filename not in overlay:
                    dst.writestr(info, src.read(info.filename))
            for name, full in sorted(overlay.items()):
                dst.write(full, name)
        for name, full in sorted(overlay.items()):
            print("overlay  %s" % name)
    else:
        shutil.copyfile(shell, tmp)
    with zipfile.ZipFile(tmp, "a", zipfile.ZIP_STORED, allowZip64=True) as z:
        z.write(model, f"{ROOT}/brain/brain.gguf")
        z.writestr(f"{ROOT}/brain/BRAIN.txt",
                   "Her brain: %s\nsha256: %s\n%s\n" % (os.path.basename(model), want, note))
    h = hashlib.sha256()
    with zipfile.ZipFile(tmp) as z, z.open(f"{ROOT}/brain/brain.gguf") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with zipfile.ZipFile(tmp) as z:
        names = z.namelist()
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            os.remove(tmp)
            raise SystemExit("FAIL the zip holds two copies of: %s" % ", ".join(dup))
        for name, full in overlay.items():
            if z.read(name) != open(full, "rb").read():
                os.remove(tmp)
                raise SystemExit("FAIL overlay file did not land byte-for-byte: %s" % name)
    if h.hexdigest() != want:
        os.remove(tmp)
        raise SystemExit("FAIL the brain inside the zip does not match the source")
    os.replace(tmp, out)
    print("built %s  %.2f GB  brain sha256 %s (verified inside the zip)" % (out, os.path.getsize(out) / 1e9, want))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
