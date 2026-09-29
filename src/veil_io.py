#!/usr/bin/env python3

import os
import shutil
import subprocess

_COPY_TOOLS = [
    ("wl-copy", ["wl-copy"]),
    ("xclip", ["xclip", "-selection", "clipboard"]),
    ("xsel", ["xsel", "--clipboard", "--input"]),
]
_PASTE_TOOLS = [
    ("wl-paste", ["wl-paste", "--no-newline"]),
    ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
    ("xsel", ["xsel", "--clipboard", "--output"]),
]


def _find_tool(candidates):
    for name, argv in candidates:
        if shutil.which(name):
            return name, argv
    return None, None


def export_text(text, dest_path=None, clipboard=False):
    if not (text or "").strip():
        return {"success": False, "method": "none", "message": "Nothing to export."}

    if clipboard or not dest_path:
        name, argv = _find_tool(_COPY_TOOLS)
        if not name:
            return {"success": False, "method": "clipboard",
                    "message": "No clipboard tool found (wl-copy / xclip / xsel) — "
                               "export to a file instead."}
        try:
            subprocess.run(argv, input=text.encode("utf-8"), check=True, timeout=10)
        except Exception as e:
            return {"success": False, "method": "clipboard", "message": f"Clipboard failed: {e}"}
        return {"success": True, "method": f"clipboard ({name})",
                "message": "Snapshot copied to clipboard."}

    dest_path = os.path.abspath(os.path.expanduser(dest_path))
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(text)
    return {"success": True, "method": "file", "path": dest_path,
            "message": f"Written: {dest_path}"}


def import_text(src_path=None, clipboard=False):
    if clipboard or not src_path:
        name, argv = _find_tool(_PASTE_TOOLS)
        if not name:
            return {"success": False, "method": "clipboard", "data": "",
                    "message": "No clipboard tool found (wl-paste / xclip / xsel) — "
                               "import from a file instead."}
        try:
            out = subprocess.run(argv, capture_output=True, check=True, timeout=10)
            text = out.stdout.decode("utf-8", "replace")
        except Exception as e:
            return {"success": False, "method": "clipboard", "data": "",
                    "message": f"Clipboard failed: {e}"}
        if not text.strip():
            return {"success": False, "method": f"clipboard ({name})", "data": "",
                    "message": "Clipboard is empty — copy a snapshot first."}
        return {"success": True, "method": f"clipboard ({name})", "data": text, "message": ""}

    src_path = os.path.abspath(os.path.expanduser(src_path))
    if not os.path.isfile(src_path):
        return {"success": False, "method": "file", "data": "",
                "message": f"No such file: {src_path}"}
    with open(src_path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return {"success": False, "method": "file", "data": "",
                "message": f"File is empty: {src_path}"}
    return {"success": True, "method": "file", "data": text, "message": ""}
