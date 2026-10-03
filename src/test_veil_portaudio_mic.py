#!/usr/bin/env python3
import contextlib
import io
import os
import sys
import tempfile
import threading
import time
import types

import numpy as np

_TMP = tempfile.mkdtemp(prefix="veil_mic_rig_")
os.environ["VEIL_DATA"] = _TMP
os.environ["VEIL_VOICE_DIR"] = _TMP
os.environ["VEIL_MIC_DEAD_AIR"] = "0.3"
os.environ["VEIL_SILENCE_HANG"] = "1.0"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_fails = []
def check(name, cond, got=None):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond or got is None else "   got: %r" % (got,)))
    if not cond:
        _fails.append(name)


BLOCK = 1600
LOUD = (np.sin(np.arange(BLOCK) * 0.3) * 0.1 * 32767).astype(np.int16).tobytes()
QUIET = np.zeros(BLOCK, dtype=np.int16).tobytes()
script = {"chunks": [], "fail_open": False, "opened": 0}
written = {}


class RawInputStream:
    def __init__(self, samplerate, channels, dtype, blocksize, callback):
        if script["fail_open"]:
            raise RuntimeError("no input device")
        assert (samplerate, channels, dtype, blocksize) == (16000, 1, "int16", BLOCK)
        self.cb, self.alive = callback, True
        script["opened"] += 1

    def start(self):
        def feed():
            for c in script["chunks"]:
                if not self.alive:
                    return
                self.cb(c, BLOCK, None, None)
                time.sleep(0.001)
        threading.Thread(target=feed, daemon=True).start()

    def stop(self):
        self.alive = False

    def close(self):
        pass


sd = types.ModuleType("sounddevice")
sd.RawInputStream = RawInputStream
sd.query_devices = lambda: []
sd.default = types.SimpleNamespace(device=None)
sf = types.ModuleType("soundfile")
sf.write = lambda path, data, rate: written.update(path=path, n=len(data), rate=rate)
sys.modules["sounddevice"] = sd
sys.modules["soundfile"] = sf

import veil_voice as V


def record():
    written.clear()
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        ok = V._record_to_wav_portaudio(os.path.join(_TMP, "heard.wav"), seconds_max=60)
    return ok, err.getvalue()


script["chunks"] = [QUIET] * 3 + [QUIET] * 4 + [LOUD] * 10 + [QUIET] * 30
ok, _ = record()
check("speech after quiet is captured and saved at 16 kHz", ok and written.get("rate") == 16000, (ok, written))
check("the take = lead-in ring at onset (1 quiet + the first 2 loud) + 8 more loud + the 1.0 s hang (11 quiet: 0.1 summed falls short of 1.0 at 10) = 22",
      written.get("n") == 22 * BLOCK, written.get("n", 0) // BLOCK)
script["chunks"] = [QUIET] * 120
ok, _ = record()
check("no speech before the start timeout: nothing is saved", ok is False and not written)
script["chunks"] = [LOUD] * 3 + [QUIET] * 30
ok, _ = record()
check("the first 3 chunks are warm-up (a click on open never starts a take)", ok is False)
script["chunks"] = [QUIET] * 5 + [LOUD, QUIET, LOUD, QUIET] + [QUIET] * 120
ok, _ = record()
check("one loud chunk at a time is a bump, not speech (two in a row are needed)", ok is False)
script["chunks"] = []
ok, err = record()
check("a mic that gives no sound fails soft and says so once", ok is False and "gave no sound" in err, err)
script["fail_open"] = True
V._record_to_wav._dead_mic_said = False
ok, err = record()
check("no microphone at all fails soft, voice out still works", ok is False and "no microphone" in err, err)
script["fail_open"] = False

opened = script["opened"]
real_which, real_base, real_popen = V.shutil.which, V._host_exec_base, V.subprocess.Popen
V.shutil.which = lambda name: None
V._host_exec_base = lambda: []
script["chunks"] = [QUIET] * 4 + [LOUD] * 6 + [QUIET] * 20
with contextlib.redirect_stderr(io.StringIO()):
    ok = V._record_to_wav(os.path.join(_TMP, "heard2.wav"), seconds_max=60)
check("with no Linux recorder (Windows), listen() records through PortAudio", ok and script["opened"] == opened + 1)
V.shutil.which = lambda name: "/usr/bin/arecord" if name == "arecord" else None
V.subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(OSError("not on this rig"))
opened = script["opened"]
with contextlib.redirect_stderr(io.StringIO()):
    V._record_to_wav(os.path.join(_TMP, "heard3.wav"), seconds_max=60)
check("where arecord exists (Linux), the old recorder path is still the one used", script["opened"] == opened)
V.shutil.which, V._host_exec_base, V.subprocess.Popen = real_which, real_base, real_popen

print(f"\n{'ALL PASS' if not _fails else str(len(_fails)) + ' FAILED'}")
sys.exit(1 if _fails else 0)
