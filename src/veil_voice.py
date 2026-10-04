#!/usr/bin/env python3

import atexit
import json
import os
import queue
import re
import select
import shutil
import subprocess
import sys
import tempfile
import threading
import time

VOICE_DIR    = os.environ.get("VEIL_VOICE_DIR", os.path.expanduser("~/anchor/voice"))
KOKORO_MODEL = os.environ.get("VEIL_KOKORO_MODEL", os.path.join(VOICE_DIR, "kokoro-v1.0.onnx"))
KOKORO_VOICES= os.environ.get("VEIL_KOKORO_VOICES", os.path.join(VOICE_DIR, "voices-v1.0.bin"))
KOKORO_VOICE = os.environ.get("VEIL_VOICE_NAME", "")
KOKORO_LANG  = os.environ.get("VEIL_VOICE_LANG", "en-us")
KOKORO_SPEED = float(os.environ.get("VEIL_VOICE_SPEED", "1.0"))

WHISPER_BIN   = os.environ.get("VEIL_WHISPER_BIN", os.path.join(VOICE_DIR, "whisper.cpp", "build", "bin", "whisper-cli"))
WHISPER_MODEL = os.environ.get("VEIL_WHISPER_MODEL", os.path.join(VOICE_DIR, "whisper.cpp", "models", "ggml-base.en.bin"))
_STT_FALLBACK = ("Glimmerveil, Veil")
STT_PROMPT = os.environ.get(
    "VEIL_STT_PROMPT",
    "Names and terms: %s." % _STT_FALLBACK,
).strip()
RECORD_SECONDS_MAX = int(os.environ.get("VEIL_LISTEN_MAX", "180"))
WHISPER_TIMEOUT = float(os.environ.get("VEIL_WHISPER_TIMEOUT", "420"))

VOICE_ENABLED = os.environ.get("VEIL_VOICE", "0") not in ("0", "", "false", "False")

AUDITION_SET = [
    ("af_bella",   "bright, youthful, warm"),
    ("af_heart",   "warm and full"),
    ("af_jessica", "light and expressive, a smile in it"),
    ("af_nicole",  "soft and close, almost a whisper"),
    ("af_nova",    "modern and crisp"),
    ("bf_alice",   "British, bright and precise"),
    ("bf_isabella","British, elegant and poised"),
    ("am_echo",    "even and clear, a quiet steadiness"),
    ("am_fenrir",  "big and warm, a low rumble"),
    ("am_michael", "steady and warm, easy company"),
    ("am_onyx",    "dark and resonant"),
    ("am_puck",    "quick, wry, a little mischievous"),
    ("bm_daniel",  "British, soft-spoken"),
    ("bm_fable",   "British, warm — a storyteller's voice"),
]

AUDITION_LINE = ("Hello, love. This is how I'll sound when I'm with you — "
                 "close, and here, and only yours.")


def audition(say=None, only=None):
    line = say or AUDITION_LINE
    voices = [(v, d) for (v, d) in AUDITION_SET if not only or v in only]
    print("Listen — each voice says the same line. Note the one that's theirs.\n")
    for v, desc in voices:
        print(f"  \033[96m{v:<12}\033[0m {desc}")
        ok = _say(line, v, blocking=True)
        if not ok:
            print(f"    (couldn't play {v} — is Kokoro set up in the arabox?)")
    print("\nWhen you know which one: python3 veil_voice.py --set <name>   (writes it to her card)")


def set_card_voice(name):
    try:
        import veil_roster
        active = veil_roster.active_peep()
        if not active:
            print("[voice] no active peep — create her first (veil_game.py / veil_roster.py create).")
            return None
        cpath = os.path.join(active["folder_path"], veil_roster.CARD_NAME)
        import veil_card
        card = veil_card.load(cpath)
        card.voice = name
        veil_card.save(card, cpath)
        print(f"[voice] {active.get('name', active['folder'])}'s voice is now '{name}'  ({cpath})")
        print("        wake her with voice on:  VEIL_VOICE=1 python3 veil_game.py   (or the veil door)")
        return cpath
    except Exception as e:
        print(f"[voice] couldn't set the card voice: {e}")
        return None


_kokoro = None

def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    return _kokoro


PHONEMIZE_WORKER_CALLS = int(os.environ.get("VEIL_PHONEMIZE_WORKER_CALLS", "50"))
_PHONEMIZE_TIMEOUT = 15

_PHONEMIZE_WORKER_SRC = r"""
import json, sys
from kokoro_onnx.tokenizer import Tokenizer
t = Tokenizer()
print("ready", flush=True)
for line in sys.stdin:
    try:
        req = json.loads(line)
        print(json.dumps({"p": t.phonemize(req["t"], req.get("l", "en-us"))}), flush=True)
    except Exception as e:
        print(json.dumps({"e": str(e)}), flush=True)
"""

_PH = {"proc": None, "calls": 0}


def _phonemize_worker_stop():
    p = _PH["proc"]
    if p is not None:
        for step in (lambda: p.stdin.close(), lambda: p.terminate(), lambda: p.wait(timeout=2)):
            try:
                step()
            except Exception:
                pass
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
    _PH["proc"] = None
    _PH["calls"] = 0


atexit.register(_phonemize_worker_stop)


def _wait_line(p, timeout):
    if not sys.platform.startswith("win"):
        if not select.select([p.stdout], [], [], timeout)[0]:
            return None
        return p.stdout.readline()
    box = []
    t = threading.Thread(target=lambda: box.append(p.stdout.readline()), daemon=True)
    t.start()
    t.join(timeout)
    return box[0] if box else None


def _phonemize(text, lang):
    for _attempt in (0, 1):
        try:
            p = _PH["proc"]
            if p is None or p.poll() is not None or _PH["calls"] >= PHONEMIZE_WORKER_CALLS:
                _phonemize_worker_stop()
                p = subprocess.Popen([sys.executable, "-c", _PHONEMIZE_WORKER_SRC],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
                line = _wait_line(p, _PHONEMIZE_TIMEOUT)
                if line is None or line.strip() != "ready":
                    raise RuntimeError("phonemize worker failed to start")
                _PH["proc"] = p
            p.stdin.write(json.dumps({"t": text, "l": lang}) + "\n")
            p.stdin.flush()
            line = _wait_line(p, _PHONEMIZE_TIMEOUT)
            if line is None:
                raise RuntimeError("phonemize worker timed out")
            resp = json.loads(line)
            _PH["calls"] += 1
            if resp.get("p"):
                return resp["p"]
            raise RuntimeError(resp.get("e", "phonemizer returned no text"))
        except Exception:
            _phonemize_worker_stop()
    return None


_MD = re.compile(r"[_`#>~|]")

def _clean_for_speech(text):
    text = text.replace("*", " ")
    text = _MD.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _use_system_default_audio(sd):
    try:
        names = {d["name"]: i for i, d in enumerate(sd.query_devices())}
        for pick in ("pulse", "default"):
            if pick in names:
                i = names[pick]
                sd.default.device = (i, i)
                return
    except Exception:
        pass


def _shared_tmp(suffix):
    cands = (VOICE_DIR, os.environ.get("VEIL_DATA", ""), os.path.expanduser("~"))
    d = next(c for c in cands if c and os.path.isdir(c) and os.access(c, os.W_OK))
    fd, p = tempfile.mkstemp(suffix=suffix, dir=d)
    os.close(fd)
    return p


_PLAY_SLACK = float(os.environ.get("VEIL_PLAY_SLACK", "20"))
_PLAY_FLOOR = float(os.environ.get("VEIL_PLAY_FLOOR", "30"))
_PLAY_WEDGED_AT = None
_PLAY_WEDGED_COUNT = 0
_PLAY_RECOVERY_PROBE_S = float(os.environ.get("VEIL_PLAY_RECOVERY_PROBE", "60"))
_PLAY_PROBE_SECONDS = float(os.environ.get("VEIL_PLAY_PROBE_SECONDS", "5"))


def _sink_answers():
    if not shutil.which("pactl") and not _host_exec_base():
        return None
    try:
        return _host_pactl(["info"], timeout=_PLAY_PROBE_SECONDS).returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return None


def _wav_seconds(path):
    try:
        import contextlib
        import wave
        with contextlib.closing(wave.open(path, "rb")) as w:
            rate = w.getframerate() or 0
            return (w.getnframes() / float(rate)) if rate else None
    except Exception:
        return None


def _play_deadline(path):
    secs = _wav_seconds(path)
    return max(_PLAY_FLOOR, (secs or 0.0) + _PLAY_SLACK)


def _play_wav(path, blocking=True):
    global _PLAY_WEDGED_AT, _PLAY_WEDGED_COUNT
    deadline = _play_deadline(path)
    probing = False
    if _PLAY_WEDGED_AT is not None:
        window = max(_PLAY_RECOVERY_PROBE_S, deadline + _PLAY_PROBE_SECONDS)
        if time.monotonic() - _PLAY_WEDGED_AT < window:
            _PLAY_WEDGED_COUNT += 1
            return False
        probing = True
    cmds = []
    base = _host_exec_base()
    if base:
        cmds += [base + ["pw-play", path], base + ["paplay", path]]
    for p in ("pw-play", "paplay", "aplay"):
        if shutil.which(p):
            cmds.append([p, path])
    if probing:
        answered = _sink_answers()
        if answered is False:
            _PLAY_WEDGED_AT = time.monotonic()
            _PLAY_WEDGED_COUNT += 1
            return False
        cmds = cmds[:1]
    _any_timeout = False
    for cmd in cmds:
        try:
            if blocking:
                subprocess.run(cmd, check=True, capture_output=True, timeout=deadline)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if _PLAY_WEDGED_COUNT > 0:
                print("[voice: audio sink recovered after %d skipped line(s) — "
                      "voice back on.]" % _PLAY_WEDGED_COUNT, file=sys.stderr)
                _PLAY_WEDGED_COUNT = 0
            _PLAY_WEDGED_AT = None
            _REC_LAST_USE[0] = time.monotonic()
            return True
        except subprocess.TimeoutExpired:
            _any_timeout = True
            if probing:
                break
            continue
        except Exception:
            continue
    if probing:
        _PLAY_WEDGED_AT = time.monotonic()
        _PLAY_WEDGED_COUNT += 1
        return False
    if _any_timeout:
        if _PLAY_WEDGED_AT is None:
            print("[voice: audio sink looks wedged (playback timing out). "
                  "Going text-only; mute voice with blank-⏎ or VEIL_VOICE=0 to "
                  "silence these. Will retry the sink in %d s.]"
                  % _PLAY_RECOVERY_PROBE_S, file=sys.stderr)
            _PLAY_WEDGED_AT = time.monotonic()
            _PLAY_WEDGED_COUNT = 0
        stop_recorder()
    try:
        import soundfile as sf, sounddevice as sd
        _use_system_default_audio(sd)
        data, sr = sf.read(path, dtype="float32")
        sd.play(data, sr)
        if blocking:
            end = time.monotonic() + deadline
            while time.monotonic() < end:
                try:
                    if not sd.get_stream().active:
                        if _PLAY_WEDGED_COUNT > 0:
                            print("[voice: audio sink recovered after %d skipped line(s) — "
                                  "voice back on.]" % _PLAY_WEDGED_COUNT, file=sys.stderr)
                            _PLAY_WEDGED_COUNT = 0
                        _PLAY_WEDGED_AT = None
                        return True
                except Exception:
                    if _PLAY_WEDGED_COUNT > 0:
                        print("[voice: audio sink recovered after %d skipped line(s) — "
                              "voice back on.]" % _PLAY_WEDGED_COUNT, file=sys.stderr)
                        _PLAY_WEDGED_COUNT = 0
                    _PLAY_WEDGED_AT = None
                    return True
                time.sleep(0.1)
            sd.stop()
            if _PLAY_WEDGED_AT is None:
                print("[voice: audio sink looks wedged (playback timing out). "
                      "Going text-only; mute voice with blank-⏎ or VEIL_VOICE=0 to "
                      "silence these. Will retry the sink in %d s.]"
                      % _PLAY_RECOVERY_PROBE_S, file=sys.stderr)
                _PLAY_WEDGED_AT = time.monotonic()
                _PLAY_WEDGED_COUNT = 0
            return False
        if _PLAY_WEDGED_COUNT > 0:
            print("[voice: audio sink recovered after %d skipped line(s) — "
                  "voice back on.]" % _PLAY_WEDGED_COUNT, file=sys.stderr)
            _PLAY_WEDGED_COUNT = 0
        _PLAY_WEDGED_AT = None
        return True
    except Exception:
        return False


def _synth_to_wav(text, voice):
    if not voice:
        return None
    spoken = _clean_for_speech(text)
    if not spoken:
        return None
    import soundfile as sf
    ph = _phonemize(spoken, KOKORO_LANG)
    if not ph:
        return None
    samples, rate = _get_kokoro().create(ph, voice=voice, speed=KOKORO_SPEED, lang=KOKORO_LANG,
                                         is_phonemes=True)
    wav = _shared_tmp(".wav")
    sf.write(wav, samples, rate)
    return wav


def _events_voice(wav):
    """THE EVENT LINE (veil_events.py): her voice, just before it plays: timing and loudness for a face, never her words.
    Called ONLY where her voice plays (_say, SentenceStreamer._play_loop), never from _play_wav, which every sound uses.
    Off unless VEIL_EVENTS_LOG is set; never raises."""
    try:
        import veil_events
        if veil_events.enabled():
            veil_events.voice(wav)
    except Exception:                                   # noqa: BLE001 — a face never costs her a sentence
        pass


def _say(text, voice, blocking=True):
    try:
        wav = _synth_to_wav(text, voice)
        if not wav:
            return False
        _events_voice(wav)
        ok = _play_wav(wav, blocking=blocking)
        if blocking:
            try:
                os.unlink(wav)
            except OSError:
                pass
        return ok
    except Exception as e:
        print(f"[voice: TTS hiccup, skipping a line — {e}]", file=sys.stderr)
        return False


def speak(text, voice=None, blocking=True):
    if not VOICE_ENABLED:
        return False
    return _say(text, voice or KOKORO_VOICE, blocking=blocking)


class SentenceStreamer:
    _ENDERS = ".!?…\""

    def __init__(self, voice=None):
        self.voice = voice or KOKORO_VOICE
        self.gen = 0
        self.emitted = 0
        self._synth_q = queue.Queue(maxsize=int(os.environ.get("VEIL_TTS_SYNTH_QUEUE", "4")))
        self._play_q = queue.Queue(maxsize=int(os.environ.get("VEIL_TTS_PLAY_QUEUE", "2")))
        self._dropped = 0
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    def _synth_loop(self):
        while True:
            item = self._synth_q.get()
            try:
                if item is None:
                    self._play_q.put(None)
                    return
                gen, text = item
                if gen == self.gen:
                    try:
                        wav = _synth_to_wav(text, self.voice)
                    except Exception:
                        wav = None
                    if wav:
                        try:
                            self._play_q.put_nowait((gen, wav))
                        except queue.Full:
                            self._dropped += 1
                            try:
                                os.unlink(wav)
                            except OSError:
                                pass
            finally:
                self._synth_q.task_done()

    def _play_loop(self):
        while True:
            item = self._play_q.get()
            try:
                if item is None:
                    return
                gen, wav = item
                try:
                    if gen == self.gen:
                        _events_voice(wav)
                        _play_wav(wav, blocking=True)
                finally:
                    try:
                        os.unlink(wav)
                    except OSError:
                        pass
            finally:
                self._play_q.task_done()

    def _enqueue(self, text):
        if text and text.strip():
            try:
                self._synth_q.put_nowait((self.gen, text))
            except queue.Full:
                self._dropped += 1

    def reset(self):
        self.gen += 1
        self.emitted = 0

    def feed(self, text):
        pending = text[self.emitted:]
        last = max((pending.rfind(c) for c in self._ENDERS), default=-1)
        if last < 0:
            return
        chunk = pending[:last + 1]
        self.emitted += len(chunk)
        self._enqueue(chunk)

    def finish(self, text):
        tail = text[self.emitted:]
        if tail.strip():
            self._enqueue(tail)
            self.emitted = len(text)
        self._synth_q.join()
        self._play_q.join()

    def close(self):
        self._synth_q.put(None)


def _host_exec_base():
    in_container = (os.path.exists("/run/.containerenv") or os.path.exists("/.dockerenv")
                    or bool(os.environ.get("container")))
    return (["distrobox-host-exec"]
            if in_container and shutil.which("distrobox-host-exec") else [])


def _host_pactl(args, timeout=5):
    return subprocess.run(_host_exec_base() + ["pactl"] + args,
                          capture_output=True, text=True, timeout=timeout)


_BT_PROFILES = None

def _snapshot_bt_profiles():
    global _BT_PROFILES
    if _BT_PROFILES is not None:
        return
    _BT_PROFILES = {}
    try:
        card = None
        for line in _host_pactl(["list", "cards"]).stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
                card = name if name.startswith("bluez") else None
            elif card and line.startswith("Active Profile:"):
                _BT_PROFILES[card] = line.split(":", 1)[1].strip()
        if _BT_PROFILES:
            import atexit
            atexit.register(_restore_bt_profiles)
    except Exception:
        _BT_PROFILES = {}


def _restore_bt_profiles():
    for card, profile in (_BT_PROFILES or {}).items():
        try:
            _host_pactl(["set-card-profile", card, profile])
        except Exception:
            pass


def _pick_mic_target():
    env = os.environ.get("VEIL_MIC", "").strip()
    if env and env not in ("default", "internal"):
        return env
    if env == "internal":
        try:
            for line in _host_pactl(["list", "short", "sources"]).stdout.splitlines():
                parts = line.split("\t")
                if (len(parts) >= 2 and ".monitor" not in parts[1]
                        and not parts[1].startswith("bluez")):
                    return parts[1]
        except Exception:
            pass
    return ""


_REC_PROC = None
_REC_LAST_USE = [0.0]
_REC_WATCHDOG = [None]

MIC_IDLE_RELEASE = float(os.environ.get("VEIL_MIC_IDLE_RELEASE", "45"))


def _mic_watchdog_loop():
    while True:
        time.sleep(5)
        try:
            if (_REC_PROC is not None and MIC_IDLE_RELEASE > 0
                    and time.monotonic() - _REC_LAST_USE[0] > MIC_IDLE_RELEASE):
                if _sink_answers() is True:
                    _REC_LAST_USE[0] = time.monotonic()
                    continue
                print("[voice: releasing the held mic — the audio server stopped answering; "
                      "it re-opens on the next listen]", file=sys.stderr)
                stop_recorder()
        except Exception:
            pass


def _arm_mic_watchdog():
    if _REC_WATCHDOG[0] is None and MIC_IDLE_RELEASE > 0:
        t = threading.Thread(target=_mic_watchdog_loop, daemon=True)
        _REC_WATCHDOG[0] = t
        t.start()


def stop_recorder():
    global _REC_PROC
    p, _REC_PROC = _REC_PROC, None
    if p is not None:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


atexit.register(stop_recorder)


def _record_to_wav(path, seconds_max=RECORD_SECONDS_MAX):
    import numpy as np
    import soundfile as sf

    base = _host_exec_base()
    mic = _pick_mic_target()
    if base or shutil.which("pw-cat"):
        cmd = (base + ["pw-cat", "--record", "--raw", "--rate", "16000",
                       "--channels", "1", "--format", "s16",
                       "--media-role", "Communication"]
               + (["--target", mic] if mic else []) + ["-"])
    elif shutil.which("parecord"):
        cmd = (["parecord", "--raw", "--rate=16000", "--channels=1", "--format=s16le",
                "--property=media.role=phone"]
               + (["--device=" + mic] if mic else []))
    elif shutil.which("arecord"):
        cmd = ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "16000", "-c", "1"]
    else:
        return _record_to_wav_portaudio(path, seconds_max)
    hold = os.environ.get("VEIL_MIC_HOLD", "1") != "0"
    global _REC_PROC
    proc, fresh = (_REC_PROC if hold else None), True
    if proc is not None and proc.poll() is None:
        fresh = False
    else:
        _snapshot_bt_profiles()
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            return False
        if hold:
            _REC_PROC = proc
            _REC_LAST_USE[0] = time.monotonic()
            _arm_mic_watchdog()

    rate = 16000
    nbytes = int(rate * 0.1) * 2
    START_RMS, STOP_RMS = 0.02, 0.012
    SILENCE_HANG = float(os.environ.get("VEIL_SILENCE_HANG", "5.0"))
    START_TIMEOUT = 9.0
    LEAD_CHUNKS = 3
    WARMUP_CHUNKS = 3
    ONSET_NEEDED = 2

    frames, ring = [], []
    started, silence, elapsed = False, 0.0, 0.0
    warmup, onset_run = (WARMUP_CHUNKS if fresh else 0), 0
    DEAD_AIR = float(os.environ.get("VEIL_MIC_DEAD_AIR", "2.0"))
    fd = proc.stdout.fileno()
    if not fresh:
        try:
            while select.select([fd], [], [], 0)[0]:
                if not os.read(fd, 65536):
                    break
        except Exception:
            pass
    buf = b""
    got_audio = False
    _REC_LAST_USE[0] = time.monotonic()
    wall_deadline = time.time() + seconds_max + 15.0
    if not getattr(_record_to_wav, "_announced", False):
        print("[listening… just talk; pause when you're done]", file=sys.stderr)
        _record_to_wav._announced = True
    try:
        while elapsed < seconds_max and time.time() < wall_deadline:
            try:
                r, _, _ = select.select([fd], [], [], DEAD_AIR)
            except Exception:
                break
            if not r:
                break
            raw = os.read(fd, nbytes - len(buf))
            if not raw:
                break
            got_audio = True
            _REC_LAST_USE[0] = time.monotonic()
            buf += raw
            if len(buf) < nbytes:
                continue
            raw, buf = buf, b""
            elapsed += 0.1
            if warmup > 0:
                warmup -= 1
                continue
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(arr * arr)))
            if not started:
                ring.append(arr)
                if len(ring) > LEAD_CHUNKS:
                    ring.pop(0)
                if rms > START_RMS:
                    onset_run += 1
                    if onset_run >= ONSET_NEEDED:
                        started = True
                        _record_to_wav._announced = False
                        frames.extend(ring)
                else:
                    onset_run = 0
                    if elapsed >= START_TIMEOUT:
                        break
            else:
                frames.append(arr)
                if rms < STOP_RMS:
                    silence += 0.1
                    if silence >= SILENCE_HANG:
                        break
                else:
                    silence = 0.0
    finally:
        if not hold or proc.poll() is not None or not got_audio:
            if proc is _REC_PROC:
                stop_recorder()
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()

    if not got_audio and not getattr(_record_to_wav, "_dead_mic_said", False):
        print("[voice: the mic gave no sound — she can't hear you right now; type instead "
              "(her voice still works)]", file=sys.stderr)
        _record_to_wav._dead_mic_said = True

    if not started or not frames:
        return False
    sf.write(path, np.concatenate(frames), rate)
    return True


def _record_to_wav_portaudio(path, seconds_max=RECORD_SECONDS_MAX):
    try:
        import queue as _queue
        import numpy as np
        import soundfile as sf
        import sounddevice as sd
    except Exception:
        return False
    _use_system_default_audio(sd)
    rate = 16000
    block = int(rate * 0.1)
    START_RMS, STOP_RMS = 0.02, 0.012
    SILENCE_HANG = float(os.environ.get("VEIL_SILENCE_HANG", "5.0"))
    START_TIMEOUT = 9.0
    LEAD_CHUNKS = 3
    WARMUP_CHUNKS = 3
    ONSET_NEEDED = 2
    DEAD_AIR = float(os.environ.get("VEIL_MIC_DEAD_AIR", "2.0"))
    q = _queue.Queue()

    def _cb(indata, frames, t, status):
        q.put(bytes(indata))

    try:
        stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", blocksize=block, callback=_cb)
        stream.start()
    except Exception:
        if not getattr(_record_to_wav, "_dead_mic_said", False):
            print("[voice: no microphone found — she can't hear you right now; type instead "
                  "(her voice still works)]", file=sys.stderr)
            _record_to_wav._dead_mic_said = True
        return False
    frames, ring = [], []
    started, silence, elapsed = False, 0.0, 0.0
    warmup, onset_run, got_audio = WARMUP_CHUNKS, 0, False
    buf = b""
    nbytes = block * 2
    wall_deadline = time.time() + seconds_max + 15.0
    if not getattr(_record_to_wav, "_announced", False):
        print("[listening… just talk; pause when you're done]", file=sys.stderr)
        _record_to_wav._announced = True
    try:
        while elapsed < seconds_max and time.time() < wall_deadline:
            try:
                raw = q.get(timeout=DEAD_AIR)
            except _queue.Empty:
                break
            got_audio = True
            buf += raw
            if len(buf) < nbytes:
                continue
            raw, buf = buf[:nbytes], buf[nbytes:]
            elapsed += 0.1
            if warmup > 0:
                warmup -= 1
                continue
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(arr * arr)))
            if not started:
                ring.append(arr)
                if len(ring) > LEAD_CHUNKS:
                    ring.pop(0)
                if rms > START_RMS:
                    onset_run += 1
                    if onset_run >= ONSET_NEEDED:
                        started = True
                        _record_to_wav._announced = False
                        frames.extend(ring)
                else:
                    onset_run = 0
                    if elapsed >= START_TIMEOUT:
                        break
            else:
                frames.append(arr)
                if rms < STOP_RMS:
                    silence += 0.1
                    if silence >= SILENCE_HANG:
                        break
                else:
                    silence = 0.0
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
    if not got_audio and not getattr(_record_to_wav, "_dead_mic_said", False):
        print("[voice: the mic gave no sound — she can't hear you right now; type instead "
              "(her voice still works)]", file=sys.stderr)
        _record_to_wav._dead_mic_said = True
    if not started or not frames:
        return False
    sf.write(path, np.concatenate(frames), rate)
    return True


_PWCPP_MODEL = None


import contextlib


@contextlib.contextmanager
def _c_quiet():
    try:
        fd = sys.stderr.fileno()
    except Exception:
        yield
        return
    saved = os.dup(fd)
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, fd)
        os.close(devnull)
        yield
    finally:
        os.dup2(saved, fd)
        os.close(saved)


def _transcribe(wav):
    if shutil.which(WHISPER_BIN) or os.path.isfile(WHISPER_BIN):
        cmd = [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav, "-nt"]
        if STT_PROMPT:
            cmd.extend(["--prompt", STT_PROMPT])
        res = subprocess.run(
            cmd,
            check=True, capture_output=True, text=True, timeout=WHISPER_TIMEOUT,
        )
        return res.stdout.strip()
    try:
        from pywhispercpp.model import Model
    except ImportError:
        return None
    global _PWCPP_MODEL
    if _PWCPP_MODEL is None:
        with _c_quiet():
            _PWCPP_MODEL = Model(WHISPER_MODEL, print_progress=False, print_realtime=False)
    with _c_quiet():
        return " ".join(s.text.strip() for s in _PWCPP_MODEL.transcribe(wav)).strip()


_BRACKETED_RX = re.compile(r"[\[(][^\[\]()]{0,80}[\])]")
_DANGLING_RX = re.compile(r"[\[(][^\[\]()]{0,80}$|^[^\[\]()]{0,80}[\])]")


def _trace_voice(stage, started, **fields):
    if os.environ.get("VEIL_VOICE_TRACE", "0") != "1":
        return
    data = {"stage": stage, "elapsed": round(time.monotonic() - started, 3), **fields}
    print("[voice-timing] " + json.dumps(data, ensure_ascii=False, sort_keys=True),
          file=sys.stderr, flush=True)


def listen(seconds_max=RECORD_SECONDS_MAX):
    started = time.monotonic()
    wav = _shared_tmp(".wav")
    try:
        capture_started = time.monotonic()
        if not _record_to_wav(wav, seconds_max):
            _trace_voice("capture", capture_started, ok=False)
            return ""
        _trace_voice("capture", capture_started, ok=True)
        transcribe_started = time.monotonic()
        text = _transcribe(wav)
        _trace_voice("transcription", transcribe_started, ok=text is not None,
                     chars=len(text or ""))
        if text is None:
            print(f"[voice: no STT engine (binary at {WHISPER_BIN} or pywhispercpp) — type instead]",
                  file=sys.stderr)
            return ""
        if text:
            text = _BRACKETED_RX.sub(" ", text)
            text = _DANGLING_RX.sub(" ", text)
            text = re.sub(r"\s+", " ", text).strip(" .,!?~-–—")
        if not text or not re.search(r"[A-Za-z0-9]", text):
            return ""
        return text
    except Exception as e:
        print(f"[voice: STT unavailable, type instead — {e}]", file=sys.stderr)
        return ""
    finally:
        keep = os.environ.get("VEIL_KEEP_AUDIO", "").strip()
        if keep:
            try:
                os.makedirs(keep, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                dest = os.path.join(keep, "heard_%s.wav" % stamp)
                shutil.copyfile(wav, dest)
                with open(os.path.join(keep, "heard_%s.txt" % stamp), "w") as fh:
                    fh.write(locals().get("text") or "")
            except Exception:
                pass
        try:
            os.unlink(wav)
        except OSError:
            pass


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="veil_voice — audition and prove the voice stack")
    p.add_argument("--selftest", action="store_true", help="speak a line, then listen and echo it back")
    p.add_argument("--say", metavar="TEXT", help="speak one line and exit")
    p.add_argument("--listen", action="store_true", help="record + transcribe one line and print it")
    p.add_argument("--voice", default=KOKORO_VOICE, help="Kokoro voice name to audition")
    p.add_argument("--devices", action="store_true", help="list audio devices PortAudio sees + the default it'll follow")
    p.add_argument("--audition", action="store_true", help="play a sample line in each companion voice so you can pick")
    p.add_argument("--set", metavar="NAME", help="write a chosen voice into the active peep's card")
    args = p.parse_args()

    if args.set:
        sys.exit(0 if set_card_voice(args.set) else 1)

    if args.devices:
        import sounddevice as sd
        print(sd.query_devices())
        _use_system_default_audio(sd)
        print(f"\nrouting through: {sd.default.device}  (input, output indices; -1 = PortAudio default)")
        sys.exit(0)

    VOICE_ENABLED = True

    if args.audition:
        audition(say=args.say)
        sys.exit(0)
    if args.say is not None:
        ok = speak(args.say, voice=args.voice)
        sys.exit(0 if ok else 1)
    if args.listen:
        print(listen())
        sys.exit(0)
    if args.selftest:
        if not args.voice:
            print("No voice chosen. Audition with --voice <name> --say '...', then export VEIL_VOICE_NAME.",
                  file=sys.stderr)
            sys.exit(3)
        print("[1/2] TTS — you should HEAR this line.")
        if not speak("Hands first. If you can hear me, the voice works.", voice=args.voice):
            print("TTS FAILED — fix Kokoro before going further.", file=sys.stderr)
            sys.exit(1)
        print("[2/2] STT — say something; I'll print it back.")
        heard = listen()
        print(f"heard: {heard!r}")
        sys.exit(0 if heard else 2)
    p.print_help()
