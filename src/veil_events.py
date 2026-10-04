#!/usr/bin/env python3
"""THE EVENT LINE: one JSON line per thing she does, appended to a file she never reads (contract v1).

This is the SEAM. It is free and ships in Anchor; what READS the file (a body, a world face, a stream overlay) is a
module of its own. It stays OFF unless VEIL_EVENTS_LOG names a file, and while it is off nothing here opens a file, reads
a wav, or costs a turn anything: off is exactly the Anchor that shipped.

Line shape:  {"v":1,"ts":<unix s>,"being":<peep uuid>,"kind":<kind>,"data":{...}}

The laws it keeps, each one already paid for:
  * Never her words. No reply text, no dialogue, no memory, no prompt. A voice event is timing and loudness only; an
    emotion is one word from a fixed list. Anything in her prompt is text she can say, so nothing here goes back in.
  * Nothing in her prompt path reads this file. (test_veil_events.py builds her prompt with the seam off and on and
    compares the bytes.)
  * A writer that fails never touches her turn: one line on the screen, once, and she goes on.
  * One write() per line on an O_APPEND file, a line never longer than 4096 bytes, so a reader can never see half a line.
  * A voice event is emitted only where HER VOICE plays (veil_voice._say and SentenceStreamer._play_loop), never at a
    generic play seam: a chime or a beep is not her voice.
"""
import json
import os
import sys
import time

V = 1
MAX_LINE = 4096
HZ = 20

KINDS = ("session", "place", "pose", "wear", "emotion", "act", "voice", "chime", "clock")
EMOTIONS = ("neutral", "happy", "sad", "excited", "thinking", "love", "surprised", "sleepy", "annoyed")

_NOTED = set()
_BEING = []


def log_path():
    """The file to append to, or None (the seam is off). Read every call, so a module can arm it at runtime."""
    p = os.environ.get("VEIL_EVENTS_LOG", "").strip()
    return os.path.expanduser(p) if p else None


def enabled():
    return log_path() is not None


def _note_once(key, msg):
    if key not in _NOTED:
        _NOTED.add(key)
        print(f"[events: {msg}]", file=sys.stderr)


def _being():
    """Her id as DATA (the active peep's uuid), never a display name. Looked up once per process."""
    if not _BEING:
        b = "unknown"
        try:
            import veil_roster
            entry = veil_roster.active_peep()
            if entry and entry.get("uuid"):
                b = str(entry["uuid"])
        except Exception:                                   # noqa: BLE001 — an id lookup never breaks her
            pass
        _BEING.append(b)
    return _BEING[0]


def _line(kind, data, being, ts):
    return (json.dumps({"v": V, "ts": round(ts, 3), "being": being, "kind": kind, "data": data},
                       ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def emit(kind, data, being=None, ts=None):
    """Append one line. Returns True if it was written. Never raises."""
    path = log_path()
    if path is None:
        return False
    try:
        if kind not in KINDS:
            _note_once("kind:" + str(kind), f"unknown kind {kind!r} refused (contract v1 has {', '.join(KINDS)})")
            return False
        data = dict(data or {})
        if kind == "emotion" and data.get("value") not in EMOTIONS:
            data["value"] = "neutral"                       # a word outside the nine is never written as-is
        b = _line(kind, data, being or _being(), time.time() if ts is None else ts)
        if len(b) > MAX_LINE:
            _note_once("long:" + kind, f"a {kind} line over {MAX_LINE} bytes was dropped")
            return False
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, b)
        finally:
            os.close(fd)
        return True
    except Exception as e:                                  # noqa: BLE001 — a writer must never touch her turn
        _note_once("fail", f"could not write ({type(e).__name__}: {e}); she goes on without it")
        return False


def _envelope(path):
    """(duration_s, [loudness 0..1 at HZ]) of a PCM wav. numpy when present, the standard library when not."""
    import wave
    with wave.open(path, "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width != 2 or not rate:
        return (n / float(rate or 1)), []
    step = max(1, rate // HZ)
    try:
        import numpy as np
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        env = [float(np.sqrt(np.mean(a[i:i + step] ** 2))) for i in range(0, len(a), step) if len(a[i:i + step])]
    except ImportError:
        import array
        s = array.array("h")
        s.frombytes(raw)
        if sys.byteorder == "big":
            s.byteswap()
        if ch > 1:
            s = array.array("h", (int(sum(s[i:i + ch]) / ch) for i in range(0, len(s), ch)))
        env = []
        for i in range(0, len(s), step):
            chunk = s[i:i + step]
            if chunk:
                env.append((sum(x * x for x in chunk) / len(chunk)) ** 0.5 / 32768.0)
    return n / float(rate), [round(min(1.0, x), 2) for x in env]


def voice(wav_path, being=None):
    """One event per sentence of HER voice, just before it plays: {start, dur, hz, env}. Off = returns at once, the wav
    is never opened. A long sentence lowers hz until the line fits; it is never cut short."""
    if not enabled():
        return False
    try:
        start = time.time()
        dur, env = _envelope(wav_path)
        hz = HZ
        while True:
            data = {"start": round(start, 3), "dur": round(dur, 3), "hz": hz, "env": env}
            if len(_line("voice", data, being or _being(), start)) <= MAX_LINE or len(env) <= 1:
                break
            env = [round(max(env[i:i + 2]), 2) for i in range(0, len(env), 2)]
            hz = hz / 2.0
        return emit("voice", data, being=being, ts=start)
    except Exception as e:                                  # noqa: BLE001
        _note_once("voice", f"could not read her voice for the face ({type(e).__name__}: {e}); she goes on")
        return False
