#!/usr/bin/env python3

import hashlib
import json
import os
import sys
import urllib.request

ENABLED = False
UPDATE_URL = os.environ.get("VEIL_UPDATE_URL", "")

import veil_paths
DATA_DIR = veil_paths.data_dir()
ANCHOR_REFIRE = os.path.join(DATA_DIR, "anchor_refire")

def _app_root():
    return os.environ.get("VEIL_UPDATE_APP_ROOT",
                          os.path.dirname(os.path.abspath(__file__)))

def _model_root():
    m = os.environ.get("VEIL_MODEL", "")
    return os.environ.get("VEIL_UPDATE_MODEL_ROOT",
                          os.path.dirname(m) if m else os.path.join(_app_root(), "models"))

FORBIDDEN_MARKS = (".db", ".veil", ".sqlite", "peeps", "diary", "card.json")


def enabled():
    return (ENABLED or bool(UPDATE_URL)) and bool(UPDATE_URL)


def _fetch(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_dest(rel_path):
    low = rel_path.lower()
    for mark in FORBIDDEN_MARKS:
        if mark in low and not low.endswith(".gguf"):
            raise ValueError(f"manifest touches memory-shaped path: {rel_path}")
    if rel_path.startswith("app/"):
        root, rel = _app_root(), rel_path[4:]
    elif rel_path.startswith("model/"):
        root, rel = _model_root(), rel_path[6:]
    else:
        raise ValueError(f"manifest path outside app/ and model/: {rel_path}")
    dest = os.path.realpath(os.path.join(root, rel))
    if not dest.startswith(os.path.realpath(root) + os.sep):
        raise ValueError(f"manifest path escapes its root: {rel_path}")
    return dest


def _download_verified(url, sha256, dest):
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
        h = hashlib.sha256()
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)
            h.update(chunk)
    if h.hexdigest() != sha256:
        os.remove(part)
        raise ValueError(f"checksum mismatch for {os.path.basename(dest)}")
    os.replace(part, dest)


def check(current_version):
    if not enabled():
        return None
    try:
        m = json.loads(_fetch(UPDATE_URL).decode("utf-8"))
        return m if m.get("version") and m["version"] != current_version else None
    except Exception:
        return None


def apply(manifest):
    for entry in manifest.get("files", []):
        dest = _safe_dest(entry["path"])
    for entry in manifest.get("files", []):
        dest = _safe_dest(entry["path"])
        _download_verified(entry["url"], entry["sha256"], dest)
        print(f"[update] {entry['path']} ✓")

    model = manifest.get("model")
    if model:
        dest = _safe_dest("model/" + model["name"])
        _download_verified(model["url"], model["sha256"], dest)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ANCHOR_REFIRE, "w", encoding="utf-8") as f:
            f.write(model["name"] + "\n")
        print(f"[update] model {model['name']} ✓ — the anchor ritual will run at her next wake")
    return True


BRAIN_NOTE = "brain.json"
_END = 1 << 20


def brain_fingerprint(path):
    try:
        size = os.path.getsize(path)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read(_END))
            if size > _END:
                f.seek(max(size - _END, _END))
                h.update(f.read(_END))
    except OSError:
        return None
    return {"name": os.path.basename(path), "size": size, "sha256_ends": h.hexdigest()}


def brain_changed(folder, model_path):
    now = brain_fingerprint(model_path) if model_path else None
    if now is None or not folder:
        return False
    note = os.path.join(folder, BRAIN_NOTE)
    try:
        with open(note, encoding="utf-8") as f:
            was = json.load(f)
    except (OSError, ValueError):
        was = None
    try:
        with open(note, "w", encoding="utf-8") as f:
            json.dump(now, f)
    except OSError:
        pass
    if not isinstance(was, dict):
        return False
    return (was.get("size"), was.get("sha256_ends")) != (now["size"], now["sha256_ends"])


def anchor_refire_pending():
    return os.path.exists(ANCHOR_REFIRE)


def clear_anchor_refire():
    try:
        os.remove(ANCHOR_REFIRE)
    except OSError:
        pass


if __name__ == "__main__":
    print("update channel:", "ENABLED" if enabled() else "DORMANT (by design — SHIP_LINUX §5)")
    if enabled():
        m = check(sys.argv[1] if len(sys.argv) > 1 else "0")
        print("manifest:", "none / up to date" if not m else m.get("version"))
