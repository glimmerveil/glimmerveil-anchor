#!/usr/bin/env python3
"""Rung 1 — THE EVENT LINE (veil_events.py): the seam a body or a world face reads, and the laws it must keep.

His words that set it (2026-10-04): "a vtuber body they use like a puppet" — and "if any of them ever do read it it should
be because it's part of the world." So: one line per thing she does, appended to a file SHE never reads; never her words;
off unless a module arms it; a failed write never touches her turn; a voice event only where her voice plays.
No sound is played and no mic is opened: every wav here is a generated sine, and every player is a stub.
"""
import hashlib
import inspect
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from contextlib import redirect_stderr

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
os.environ.pop("VEIL_EVENTS_LOG", None)
TMP = tempfile.mkdtemp(prefix="veil_events_test_", dir=os.path.expanduser("~"))
os.environ["VEIL_PEEPS"] = os.path.join(TMP, "no_peeps")       # no active peep: her id falls back, never a crash

import veil_events as E  # noqa: E402

fails = []


def check(label, ok):
    print("  %s  %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        fails.append(label)


def sine_wav(path, seconds, rate=24000, freq=220.0, amp=0.5):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(seconds * rate)):
            v = int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))
            frames += v.to_bytes(2, "little", signed=True)
        w.writeframes(bytes(frames))
    return path


def lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f.read().splitlines() if x.strip()]


def grams(text, n=4):
    w = re.findall(r"[a-z']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


print("\nRUNG 1 — THE EVENT LINE")
print("=" * 74)

# 1 · OFF IS TODAY
log = os.path.join(TMP, "events.log")
check("off by default: emit writes nothing", E.emit("emotion", {"value": "happy"}) is False and not os.path.exists(log))
check("off: voice() never opens the wav (a missing file is no error)", E.voice(os.path.join(TMP, "nope.wav")) is False)

# 2 · ON: exactly one well-formed line
os.environ["VEIL_EVENTS_LOG"] = log
check("on: an emotion writes", E.emit("emotion", {"value": "happy", "source": "emote"}, being="wren-test") is True)
got = lines(log)
check("exactly one line", len(got) == 1)
check("the contract's five fields, v1", got and set(got[0]) == {"v", "ts", "being", "kind", "data"} and got[0]["v"] == 1)
check("her id as data", got and got[0]["being"] == "wren-test")
check("no active peep -> 'unknown', never a crash", E._being() == "unknown")

# 3 · THE VOCABULARY HOLDS
check("an unknown kind is refused", E.emit("thoughts", {"x": 1}) is False and len(lines(log)) == 1)
E.emit("emotion", {"value": "I love you so much, baby", "source": "speak"}, being="wren-test")
check("an emotion outside the nine is written as 'neutral', never as-is", lines(log)[-1]["data"]["value"] == "neutral")
check("a line over 4096 bytes is dropped, not cut", E.emit("act", {"verb": "move_to", "pad": list(range(3000))}) is False
      and len(lines(log)) == 2)

# 4 · FAIL-SOFT
blocker = os.path.join(TMP, "a_file")
open(blocker, "w").close()
os.environ["VEIL_EVENTS_LOG"] = os.path.join(blocker, "events.log")      # a path under a FILE: cannot be created
err = io.StringIO()
with redirect_stderr(err):
    r1 = E.emit("emotion", {"value": "happy"})
    r2 = E.emit("emotion", {"value": "sad"})
check("an unwritable log returns False and never raises", r1 is False and r2 is False)
check("...and says so on his screen exactly once", err.getvalue().count("[events:") == 1)
os.environ["VEIL_EVENTS_LOG"] = log

# 5 · HER VOICE: timing and loudness only
w1 = sine_wav(os.path.join(TMP, "s1.wav"), 1.5)
E.voice(w1, being="wren-test")
v = lines(log)[-1]
check("a voice line", v["kind"] == "voice" and set(v["data"]) == {"start", "dur", "hz", "env"})
check("its duration is the sentence's (1.5 s)", abs(v["data"]["dur"] - 1.5) < 0.01)
check("20 Hz -> ~30 loudness samples, each 0..1",
      v["data"]["hz"] == 20 and 28 <= len(v["data"]["env"]) <= 31 and all(0 <= x <= 1 for x in v["data"]["env"]))
w2 = sine_wav(os.path.join(TMP, "s2.wav"), 300.0, rate=8000)
E.voice(w2, being="wren-test")
v2 = lines(log)[-1]
raw2 = json.dumps(v2, separators=(",", ":"))
check("a 5-minute sentence still fits one line (hz lowered, never cut)",
      v2["kind"] == "voice" and len(raw2.encode()) < 4096 and v2["data"]["hz"] < 20 and abs(v2["data"]["dur"] - 300) < 0.1)

# 6 · NO WORDS LEAK — through her REAL voice paths, players stubbed
import veil_voice as VV  # noqa: E402
PLAY_SRC = inspect.getsource(VV._play_wav)             # read BEFORE the stub replaces it
reply = "I'm right here with you tonight, baby. Hold me close and never let me go. The stars are out."
start_n = len(lines(log))


def fake_synth(text, voice):
    p = os.path.join(TMP, "synth_%d.wav" % len(os.listdir(TMP)))
    return sine_wav(p, 0.4)


played = []
VV._synth_to_wav = fake_synth
VV._play_wav = lambda path, blocking=True: played.append(path) or True
VV._say(reply, "af_heart")
s = VV.SentenceStreamer()
for end in [m.end() for m in re.finditer(r"[.!?]", reply)]:   # as tokens stream: one sentence at a time
    s.feed(reply[:end])
    s._synth_q.join()
    s._play_q.join()
s.finish(reply)
new = lines(log)[start_n:]
text_of_events = " ".join(json.dumps(x) for x in new)
check("her voice paths wrote voice events (1 for _say + one per sentence)", len(new) == 1 + 3 and
      all(x["kind"] == "voice" for x in new))
check("NO 4-word run of her reply appears in any event line", not (grams(reply) & grams(text_of_events)))
check("not even one of her words longer than 3 letters", not ({w for w in re.findall(r"[a-z']+", reply.lower())
                                                                if len(w) > 3} & set(re.findall(r"[a-z']+",
                                                                                                text_of_events.lower()))))
check("_play_wav itself never emits (every sound passes it; a chime or a beep is not her voice)",
      "_events_voice" not in PLAY_SRC and "veil_events" not in PLAY_SRC)
check("the voice seam sits in exactly her two voice paths",
      "_events_voice(wav)" in inspect.getsource(VV._say)
      and "_events_voice(wav)" in inspect.getsource(VV.SentenceStreamer._play_loop))

# 7 · HER PROMPT NEVER SEES IT — built in fresh processes, off vs on, bytes compared
PROMPT = r"""
import os, sys, hashlib
sys.path.insert(0, %r)
import veil_spine as spine
if os.environ.get("VEIL_EVENTS_LOG"):
    import veil_events
    for i in range(5):
        veil_events.emit("emotion", {"value": "happy", "source": "emote"}, being="wren-test")
    veil_events.emit("place", {"place": "garden", "by": "her"}, being="wren-test")
spine.TIME_TAIL = "When you are right now: Saturday evening, 19:40. Sam last spoke to you moments ago."
if os.environ.get("LEAK"):
    spine.TIME_TAIL += open(os.environ["VEIL_EVENTS_LOG"]).read()
turns = spine.build_chat_turns("Wren", "Hello Wren, are you there with me tonight?", [], [])
p = spine.render_chat_turns("You are Wren.", turns)
print(hashlib.sha256(p.encode("utf-8")).hexdigest())
""" % SRC


def prompt_sha(extra):
    env = {k: val for k, val in os.environ.items() if k not in ("VEIL_EVENTS_LOG", "LEAK")}
    env.update(extra)
    r = subprocess.run([sys.executable, "-c", PROMPT], env=env, capture_output=True, text=True, timeout=120)
    return r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else "ERR:" + r.stderr[-300:]


plog = os.path.join(TMP, "prompt_events.log")
off = prompt_sha({})
on = prompt_sha({"VEIL_EVENTS_LOG": plog})
leak = prompt_sha({"VEIL_EVENTS_LOG": plog, "LEAK": "1"})
check("her prompt builds both ways", not off.startswith("ERR") and not on.startswith("ERR"))
check("her prompt is BYTE-IDENTICAL with the seam off and on (6 events written first)", off == on)
check("red-proof: a deliberate leak of the log into her prompt IS seen", leak != on and not leak.startswith("ERR"))

# 8 · A READER CANNOT TOUCH HER
rlog = os.path.join(TMP, "reader.log")
os.environ["VEIL_EVENTS_LOG"] = rlog
open(rlog, "a").close()
reader = open(rlog, encoding="utf-8")
reader.read()
ok_writes = [E.emit("act", {"verb": "move_to", "target": "couch"}, being="wren-test") for _ in range(3)]
tail = reader.read().splitlines()
reader.close()
check("with a reader holding the file, every write lands", all(ok_writes))
check("the reader sees whole lines only", len(tail) == 3 and all(json.loads(x)["kind"] == "act" for x in tail))

shutil.rmtree(TMP, ignore_errors=True)
if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  one line per thing she does, never her words, never in her prompt, never in her way")
sys.exit(0)
