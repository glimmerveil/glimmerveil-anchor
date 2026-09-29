#!/usr/bin/env python3

import os
import struct
import subprocess
import sys
import time
import zlib

import veil_paths
DATA_DIR = veil_paths.data_dir()
OFFER_STAMP = os.path.join(DATA_DIR, "tile_offered")

TILE_NAME = "Glimmerveil Anchor"


def tile_supported():
    return not (sys.platform.startswith("win") or sys.platform == "darwin")


_OFF_PLATFORM = ("Steam tiles are a Linux/Game Mode feature — nothing to add on this platform "
                 "(launch her the normal way).")


def _parse_map(buf, i):
    d = {}
    while True:
        t = buf[i]
        if t == 0x08:
            return d, i + 1
        i += 1
        j = buf.index(b"\x00", i)
        key = buf[i:j].decode("utf-8", "replace")
        i = j + 1
        if t == 0x00:
            d[key], i = _parse_map(buf, i)
        elif t == 0x01:
            j = buf.index(b"\x00", i)
            d[key] = buf[i:j].decode("utf-8", "replace")
            i = j + 1
        elif t == 0x02:
            d[key] = int.from_bytes(buf[i:i + 4], "little")
            i += 4
        else:
            raise ValueError(f"unknown vdf type 0x{t:02x} at {i}")


def _emit_map(d):
    out = bytearray()
    for k, v in d.items():
        kb = k.encode("utf-8") + b"\x00"
        if isinstance(v, dict):
            out += b"\x00" + kb + _emit_map(v)
        elif isinstance(v, int):
            out += b"\x02" + kb + struct.pack("<I", v & 0xFFFFFFFF)
        else:
            out += b"\x01" + kb + str(v).encode("utf-8") + b"\x00"
    out += b"\x08"
    return bytes(out)


def _load(path):
    buf = open(path, "rb").read()
    if not buf:
        return {"shortcuts": {}}
    root, _ = _parse_map(buf, 0)
    return {"shortcuts": root.get("shortcuts", {})} if "shortcuts" in root else {"shortcuts": {}}


def _save(path, root):
    open(path, "wb").write(_emit_map(root))


def _steam_userconfigs():
    hits = []
    for base in ("~/.steam/steam/userdata", "~/.local/share/Steam/userdata"):
        base = os.path.expanduser(base)
        if not os.path.isdir(base):
            continue
        for uid in os.listdir(base):
            cfg = os.path.join(base, uid, "config")
            if uid.isdigit() and uid != "0" and os.path.isdir(cfg):
                hits.append(os.path.join(cfg, "shortcuts.vdf"))
    return hits


def _steam_running():
    try:
        return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0
    except OSError:
        return False


def _tile_icon():
    src = os.path.join(os.environ.get("APPDIR", ""), "glimmerveil-anchor.png")
    dst = os.path.join(DATA_DIR, "tile_icon.png")
    try:
        if os.path.isfile(src):
            import shutil
            os.makedirs(DATA_DIR, exist_ok=True)
            shutil.copyfile(src, dst)
        return dst if os.path.isfile(dst) else ""
    except Exception:
        return ""


def _launcher_script(target):
    import shutil
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, TILE_NAME)
    term = '/usr/bin/konsole -e ' if shutil.which("konsole") else ""
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n# Launch Glimmerveil Anchor (written by the setup pass — safe "
                "to re-run it).\n"
                'case "${LD_PRELOAD:-}" in *gameoverlayrenderer*) unset LD_PRELOAD ;; esac\n'
                + f'exec {term}"{target}"\n')
    os.chmod(path, 0o755)
    return path


def _make_entry(target):
    import shutil
    if shutil.which("konsole"):
        exe, opts = '"/usr/bin/konsole"', f'-e "{target}"'
    else:
        exe, opts = f'"{target}"', ""
    appid = (zlib.crc32((exe + TILE_NAME).encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
    return {
        "appid": appid, "AppName": TILE_NAME, "exe": exe,
        "StartDir": f'"{os.path.dirname(target) or "/"}"',
        "icon": _tile_icon(), "ShortcutPath": "", "LaunchOptions": opts,
        "IsHidden": 0, "AllowDesktopConfig": 1, "AllowOverlay": 1, "OpenVR": 0,
        "Devkit": 0, "DevkitGameID": "", "DevkitOverrideAppID": 0,
        "LastPlayTime": 0, "FlatpakAppID": "", "sortas": "", "tags": {},
    }


def add_tile(target):
    if not tile_supported():
        return _OFF_PLATFORM
    import shutil
    vdfs = _steam_userconfigs()
    if not vdfs:
        return "No Steam installation found — nothing to add (launch her from the desktop)."

    if _steam_running():
        launcher = _launcher_script(target)
        _tile_icon()
        helper = shutil.which("steamos-add-to-steam")
        try:
            if helper:
                subprocess.run([helper, launcher], check=True, timeout=30,
                               capture_output=True)
            else:
                from urllib.parse import quote
                subprocess.run(["steam", "steam://addnonsteamgame/" + quote(launcher, safe="")],
                               check=True, timeout=30, capture_output=True)
            return (f"Tile added to the running Steam ('{TILE_NAME}' under Non-Steam games — "
                    "no restart needed; set its icon from Properties if you like).")
        except Exception:
            return ("Steam is running and the live add didn't take — close Steam and run "
                    "this again for the direct write.")

    done = []
    for vdf in vdfs:
        root = _load(vdf) if os.path.isfile(vdf) else {"shortcuts": {}}
        cuts = root["shortcuts"]
        if any(isinstance(v, dict)
               and (v.get("AppName") or v.get("appname")) == TILE_NAME for v in cuts.values()):
            done.append(vdf)
            continue
        if os.path.isfile(vdf):
            shutil.copy2(vdf, vdf + ".bak_veil_" + time.strftime("%Y%m%d_%H%M%S"))
        cuts[str(len(cuts))] = _make_entry(target)
        _save(vdf, {"shortcuts": cuts})
        done.append(vdf)
    return (f"Tile added ({len(done)} Steam profile(s)). It appears under Non-Steam games "
            "after Steam restarts — on a Deck it's now launchable straight from Game Mode.")


def heal_tile_art(target=None):
    if not tile_supported():
        return None
    import shutil
    try:
        icon = _tile_icon()
        if not icon:
            return
        live = _steam_running()
        for vdf in _steam_userconfigs():
            if not os.path.isfile(vdf):
                continue
            try:
                root = _load(vdf)
            except Exception:
                continue
            cuts, dirty = root["shortcuts"], False
            for v in cuts.values():
                if not isinstance(v, dict):
                    continue
                label = v.get("AppName") or v.get("appname") or ""
                exe = (v.get("exe") or v.get("Exe") or "") + " " + (v.get("LaunchOptions") or "")
                if label != TILE_NAME and "GlimmerveilAnchor" not in exe \
                        and "GlimmerveilAnchor" not in label:
                    continue
                appid = v.get("appid")
                if appid:
                    grid = os.path.join(os.path.dirname(vdf), "grid")
                    os.makedirs(grid, exist_ok=True)
                    for suffix in ("p.png", ".png", "_hero.png", "_logo.png"):
                        dst = os.path.join(grid, f"{appid & 0xFFFFFFFF}{suffix}")
                        if not os.path.exists(dst):
                            shutil.copyfile(icon, dst)
                if not (v.get("icon") or v.get("Icon")) and not live:
                    v["icon"] = icon
                    dirty = True
            if dirty:
                shutil.copy2(vdf, vdf + ".bak_veil_" + time.strftime("%Y%m%d_%H%M%S"))
                _save(vdf, {"shortcuts": cuts})
    except Exception:
        pass


def offer_tile_once(target):
    if not tile_supported():
        return None
    if os.path.exists(OFFER_STAMP) or not _steam_userconfigs():
        return
    if not sys.stdin.isatty():
        return
    try:
        ans = input("\nAdd her to Steam as a Game Mode tile (Non-Steam shortcut)? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    if ans in ("", "y", "yes"):
        msg = add_tile(target)
        print(msg)
        open(OFFER_STAMP, "w").write("accepted\n")
    elif ans in ("n", "no"):
        print("Okay — add it any time later: run her with VEIL_TILE=1, or veil_tile.py "
              "<path-to-AppImage>.")
        open(OFFER_STAMP, "w").write("declined\n")


if __name__ == "__main__":
    tgt = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("APPIMAGE", "")
    if not tgt:
        print("usage: veil_tile.py /path/to/GlimmerveilAnchor.AppImage")
        sys.exit(2)
    print(add_tile(tgt))
