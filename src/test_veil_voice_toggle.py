#!/usr/bin/env python3
import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix="veil_toggle_rig_")
os.environ["VEIL_DATA"] = _TMP
os.environ.pop("VEIL_VOICE", None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_probe
importlib.reload(veil_probe)
import veil_spine as s


def _settings():
    try:
        with open(os.path.join(_TMP, "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return None


def _flip():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        flipped = s.voice_toggle()
    return flipped, out.getvalue()


def run():
    fails = 0

    def check(label, ok):
        nonlocal fails
        print(("  PASS  " if ok else "  FAIL  ") + label)
        if not ok:
            fails += 1

    real_ara_voice = s.ara_voice

    s.ara_voice, s.VOICE = None, False
    flipped, said = _flip()
    check("no voice layer: no flip", flipped is False and s.VOICE is False)
    check("no voice layer: says so", "isn't available" in said)

    s.ara_voice = types.SimpleNamespace(KOKORO_VOICE="", VOICE_ENABLED=False)
    flipped, said = _flip()
    check("no timbre: no flip", flipped is False and s.VOICE is False)
    check("no timbre: points at audition", "audition" in said)

    s.ara_voice = types.SimpleNamespace(KOKORO_VOICE="af_heart", VOICE_ENABLED=False)
    flipped, said = _flip()
    check("flip ON", flipped and s.VOICE is True and s.ara_voice.VOICE_ENABLED is True)
    check("flip ON printed", "voice ON" in said)
    check("flip ON persisted (ship)", (_settings() or {}).get("voice") is True)
    flipped, said = _flip()
    check("flip OFF", flipped and s.VOICE is False and s.ara_voice.VOICE_ENABLED is False)
    check("flip OFF printed", "voice OFF" in said)
    check("flip OFF persisted (ship)", (_settings() or {}).get("voice") is False)

    os.environ["VEIL_VOICE"] = "1"
    try:
        os.remove(os.path.join(_TMP, "settings.json"))
    except OSError:
        pass
    flipped, _ = _flip()
    check("dev flip works", flipped and s.VOICE is True)
    check("dev flip did NOT persist", _settings() is None)
    os.environ.pop("VEIL_VOICE", None)

    s.ara_voice = real_ara_voice
    print(f"\n{'ALL GREEN' if fails == 0 else str(fails) + ' FAILURES'}")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
