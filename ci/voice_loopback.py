#!/usr/bin/env python3
import os
import re
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("ANCHOR_SRC") or os.path.join(REPO, "src")
sys.path.insert(0, SRC)
LINE = "Hello there. Can you hear me tonight? The rain is soft on the window."
WANT = {"hello", "hear", "tonight", "rain", "window"}


def _as_mic_wav(path, rate=16000):
    import numpy as np
    import soundfile as sf
    data, src = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if src != rate:
        n = int(round(len(mono) * rate / src))
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono)
    out = os.path.splitext(path)[0] + "_16k.wav"
    sf.write(out, mono, rate, subtype="PCM_16")
    print("as the mic hands it over: %d Hz -> %d Hz mono" % (src, rate))
    return out


def main():
    import veil_voice as V
    print("voice dir: %s" % V.VOICE_DIR)
    for p in (V.KOKORO_MODEL, V.KOKORO_VOICES, V.WHISPER_MODEL):
        print("  %s  %s" % ("ok  " if os.path.isfile(p) else "MISSING", p))
    try:
        import sounddevice as sd
        try:
            print("audio devices seen: %d (none is normal on a CI runner)" % len(sd.query_devices()))
        except Exception as e:
            print("audio devices: none (%s) — normal on a CI runner" % type(e).__name__)
    except Exception as e:
        print("FAIL sounddevice will not import: %s" % e)
        return 1
    t0 = time.time()
    wav = V._synth_to_wav(LINE, "af_heart")
    if not wav or not os.path.isfile(wav) or os.path.getsize(wav) < 10000:
        print("FAIL her voice made no audio")
        return 1
    print("spoke %r -> %d bytes of audio in %.1fs" % (LINE, os.path.getsize(wav), time.time() - t0))
    # her mouth speaks at 24 kHz; every recorder hands the ear 16 kHz mono, so give it what a mic would
    wav = _as_mic_wav(wav)
    t0 = time.time()
    heard = V._transcribe(wav) or ""
    print("heard back: %r  (%.1fs)" % (heard, time.time() - t0))
    words = set(re.findall(r"[a-z]+", heard.lower()))
    got = WANT & words
    if len(got) < 4:
        print("FAIL the ear heard %d of %d key words: %s" % (len(got), len(WANT), sorted(got)))
        return 1
    print("PASS her voice and her ear work on this machine: %d of %d key words came back" % (len(got), len(WANT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
