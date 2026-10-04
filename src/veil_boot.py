#!/usr/bin/env python3

import hashlib
import json
import os
import sys

APPDIR = os.environ.get("APPDIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VEIL_OPT = os.path.join(APPDIR, "opt", "veil")

import veil_paths
DATA_DIR = veil_paths.data_dir()


def _physical_cores():
    try:
        cores = set()
        phys = core = None
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("physical id"):
                    phys = line.split(":", 1)[1].strip()
                elif line.startswith("core id"):
                    core = line.split(":", 1)[1].strip()
                elif not line.strip() and core is not None:
                    cores.add((phys, core))
                    phys = core = None
        if core is not None:
            cores.add((phys, core))
        if cores:
            return len(cores)
    except OSError:
        pass
    return max((os.cpu_count() or 2) // 2, 1)


def _export_world():
    os.makedirs(DATA_DIR, exist_ok=True)
    env = os.environ
    env.setdefault("VEIL_DATA", DATA_DIR)
    env.setdefault("VEIL_N_THREADS", str(_physical_cores()))

    model_dir = os.path.join(VEIL_OPT, "model")
    ggufs = [f for f in sorted(os.listdir(model_dir)) if f.endswith(".gguf")] \
        if os.path.isdir(model_dir) else []
    if ggufs:
        env.setdefault("VEIL_MODEL", os.path.join(model_dir, ggufs[0]))

    voice = os.path.join(VEIL_OPT, "voice")
    if os.path.isdir(voice):
        env.setdefault("VEIL_VOICE_DIR", voice)
        env.setdefault("VEIL_KOKORO_MODEL", os.path.join(voice, "kokoro-v1.0.onnx"))
        env.setdefault("VEIL_KOKORO_VOICES", os.path.join(voice, "voices-v1.0.bin"))
        wm = os.path.join(voice, "ggml-base.en.bin")
        if os.path.isfile(wm):
            env.setdefault("VEIL_WHISPER_MODEL", wm)
    return ggufs


def _verify_model_once():
    manifest_path = os.path.join(VEIL_OPT, "model", "MODEL_SHA256")
    model_path = os.environ.get("VEIL_MODEL")
    if not model_path or not os.path.isfile(manifest_path):
        return
    if os.path.dirname(os.path.abspath(model_path)) != os.path.join(VEIL_OPT, "model"):
        return
    want = open(manifest_path, encoding="utf-8").read().split()[0].strip()

    stamp_path = os.path.join(DATA_DIR, "model_verified.json")
    try:
        stamp = json.load(open(stamp_path, encoding="utf-8"))
        if stamp.get("sha256") == want and stamp.get("size") == os.path.getsize(model_path):
            return
    except (OSError, ValueError):
        pass

    print("First run: checking her brain arrived whole (one-time, ~a minute on an 8GB file)…")
    h = hashlib.sha256()
    with open(model_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got != want:
        print("\nThe AI model file inside this install is damaged (checksum mismatch —\n"
              "usually a corrupted download). Please re-download the install; nothing\n"
              "on your machine caused this and nothing of yours is affected.")
        sys.exit(1)
    with open(stamp_path, "w", encoding="utf-8") as f:
        json.dump({"sha256": got, "size": os.path.getsize(model_path)}, f)
    print("Verified. She's whole.\n")


def _select_engine():
    import veil_probe
    r = veil_probe.resolve_launch()
    if r["notice"]:
        print("\n[" + r["notice"] + "]\n")
    flavor = "lib-llama-vulkan" if r["use_gpu"] else "lib-llama-cpu"
    engine = os.path.join(VEIL_OPT, flavor)
    sys.path.insert(0, engine)
    prior = os.environ.get("PYTHONPATH", "")
    parts = [engine, os.path.join(VEIL_OPT, "app"), os.path.join(VEIL_OPT, "lib")]
    os.environ["PYTHONPATH"] = os.pathsep.join(parts + ([prior] if prior else []))
    if r["use_gpu"]:
        os.environ["VEIL_GPU_LAYERS"] = str(r["layers"])
        veil_probe.drop_breadcrumb()
    else:
        os.environ.setdefault("VEIL_GPU_LAYERS", "0")


def main():
    app = os.path.join(VEIL_OPT, "app")
    lib = os.path.join(VEIL_OPT, "lib")
    for p in (app, lib):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)

    _export_world()

    import veil_probe
    if not veil_probe.cpu_supported():
        print(veil_probe.CPU_SORRY)
        sys.exit(1)

    _verify_model_once()

    target = os.environ.get("APPIMAGE")
    if target:
        import veil_tile
        if os.environ.get("VEIL_TILE") == "1":
            print(veil_tile.add_tile(target))
        else:
            veil_tile.offer_tile_once(target)
        veil_tile.heal_tile_art(target)

    if not os.path.exists(veil_probe.SETTINGS_PATH):
        print("(She starts in CPU mode — steady on any machine, and your GPU stays free for "
              "games. Have a gaming GPU? Press [g] at the door to go faster.)")

    _select_engine()

    import veil_game
    veil_game.main()


if __name__ == "__main__":
    main()
