#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys

import veil_paths
DATA_DIR = veil_paths.data_dir()

SETTINGS_PATH   = os.path.join(DATA_DIR, "settings.json")
BREADCRUMB_PATH = os.path.join(DATA_DIR, ".attempting_gpu")

IGPU_SAFE_LAYERS = 16
DISCRETE_LAYERS = -1


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(s):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, SETTINGS_PATH)


def cpu_flags():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("flags"):
                    return set(line.split(":", 1)[1].split())
    except OSError:
        pass
    return set()


def avx2_present():
    flags = cpu_flags()
    if flags:
        return "avx2" in flags
    if sys.platform.startswith("win"):
        try:
            import ctypes
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))
        except Exception:
            return None
    return None


def cpu_supported():
    if os.environ.get("VEIL_FORCE_CPU") == "1":
        return True
    return avx2_present() is not False


CPU_SORRY = (
    "This computer's processor is older than the AI engine supports (it needs AVX2,\n"
    "found on most CPUs made after ~2013). She can't run here — on a newer machine\n"
    "the same install works as-is. (If you believe this is wrong, VEIL_FORCE_CPU=1\n"
    "skips this check.)"
)


def _vulkan_summary():
    for cmd in (["vulkaninfo", "--summary"],):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return r.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ""


def probe_gpu():
    out = _vulkan_summary()
    if not out:
        return {"kind": "none", "name": "", "layers": 0}

    names = re.findall(r"deviceName\s*=\s*(.+)", out)
    types = re.findall(r"deviceType\s*=\s*(\S+)", out)
    if not names:
        return {"kind": "none", "name": "", "layers": 0}

    name = names[0].strip()
    dtype = (types[0] if types else "").upper()

    if "VANGOGH" in name.upper() or "VAN GOGH" in name.upper():
        return {"kind": "igpu-deck", "name": name, "layers": IGPU_SAFE_LAYERS}
    if "DISCRETE" in dtype:
        return {"kind": "discrete", "name": name, "layers": DISCRETE_LAYERS}
    if "INTEGRATED" in dtype:
        return {"kind": "igpu", "name": name, "layers": IGPU_SAFE_LAYERS}
    return {"kind": "none", "name": name, "layers": 0}


def drop_breadcrumb():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BREADCRUMB_PATH, "w", encoding="utf-8") as f:
        f.write("attempting gpu load\n")


def clear_breadcrumb():
    try:
        os.remove(BREADCRUMB_PATH)
    except OSError:
        pass


def breadcrumb_stale():
    return os.path.exists(BREADCRUMB_PATH)


def mark_llm_alive():
    clear_breadcrumb()


def resolve_launch(settings=None):
    s = load_settings() if settings is None else settings
    if not s.get("gpu"):
        return {"use_gpu": False, "layers": 0, "notice": None}
    if breadcrumb_stale():
        s["gpu"] = False
        save_settings(s)
        clear_breadcrumb()
        return {"use_gpu": False, "layers": 0,
                "notice": "GPU didn't hold last time — she's back on CPU (steady and safe). "
                          "You can try GPU again from settings."}
    return {"use_gpu": True, "layers": int(s.get("gpu_layers", 0)) or 0, "notice": None}


def gpu_menu():
    s = load_settings()
    state = "ON (%s layers)" % s.get("gpu_layers") if s.get("gpu") else "OFF (CPU — the steady floor)"
    print("\nGPU acceleration is currently: " + state)
    print("CPU mode works everywhere and leaves your whole GPU free for games.")
    print("GPU mode makes her ~40%+ faster if your machine has a capable graphics card.\n")
    ans = input("Turn GPU acceleration [on/off/keep]? ").strip().lower()
    if ans == "on":
        g = probe_gpu()
        if g["kind"] == "none":
            print("No usable Vulkan graphics driver found — staying on CPU. "
                  "(Install your GPU's Vulkan driver and try again.)")
            return
        if g["kind"] == "discrete":
            print(f"Found: {g['name']} — full offload, the easy win.")
        elif g["kind"] == "igpu-deck":
            print(f"Found: {g['name']} — Steam Deck class chip; using the proven-safe partial "
                  f"offload ({g['layers']} layers, soak-tested).")
        else:
            print(f"Found: {g['name']} — integrated graphics; using a conservative partial "
                  f"offload ({g['layers']} layers).")
        s["gpu"], s["gpu_layers"] = True, g["layers"]
        save_settings(s)
        print("Saved. GPU takes effect the next time she starts. If it ever fails to hold, "
              "she comes back on CPU automatically — you can't get locked out.")
    elif ans == "off":
        s["gpu"] = False
        save_settings(s)
        print("Saved — CPU mode at next start.")


if __name__ == "__main__":
    print("cpu supported:", cpu_supported())
    print("gpu:", probe_gpu())
    print("launch resolve:", resolve_launch())
