#!/usr/bin/env python3
import ast
import os
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("VEIL_VOICE", "0")
import veil_voice as V

SRC = os.path.join(HERE, "veil_voice.py")
TREE = ast.parse(open(SRC, encoding="utf-8").read())


def _calls(name_parts):
    out = []
    for node in ast.walk(TREE):
        if not isinstance(node, ast.Call):
            continue
        f, parts = node.func, []
        while isinstance(f, ast.Attribute):
            parts.insert(0, f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parts.insert(0, f.id)
        if parts[-len(name_parts):] == list(name_parts):
            out.append(node)
    return out


class AudioLaws(unittest.TestCase):

    def test_01_every_blocking_subprocess_call_is_bounded(self):
        unbounded = [c.lineno for c in _calls(("subprocess", "run"))
                     if not any(k.arg == "timeout" for k in c.keywords)]
        unbounded += [c.lineno for c in _calls(("run",))
                      if not any(k.arg == "timeout" for k in c.keywords)
                      and c.lineno not in [x.lineno for x in _calls(("subprocess", "run"))]]
        self.assertEqual(unbounded, [],
                         f"subprocess.run with no timeout= at line(s) {unbounded} — an audio call "
                         f"that can never return is what hard-locked the Deck on 2026-08-01")

    def test_02_the_in_process_backend_is_never_waited_on_unbounded(self):
        self.assertEqual([c.lineno for c in _calls(("sd", "wait"))], [],
                         "sd.wait() is unbounded — poll get_stream().active to a deadline instead")

    def test_03_the_probe_window_adapts_to_the_probe_cost(self):
        deadline = V._play_deadline.__wrapped__ if hasattr(V._play_deadline, "__wrapped__") else None
        self.assertIsNotNone(V._PLAY_PROBE_SECONDS, "no bounded probe budget exists")
        self.assertLess(V._PLAY_PROBE_SECONDS, V._PLAY_RECOVERY_PROBE_S,
                        "a single bounded probe question already costs more than the probe interval")
        src = open(SRC, encoding="utf-8").read()
        self.assertIn("max(_PLAY_RECOVERY_PROBE_S, deadline + _PLAY_PROBE_SECONDS)", src,
                      "the probe window no longer adapts to the probe cost — re-read THE_MELTS "
                      "§5.19 before removing it")

    def test_04_stop_recorder_escalates_to_kill(self):
        class Stubborn:
            def __init__(self):
                self.termed = self.killed = False

            def terminate(self):
                self.termed = True

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("pw-cat", timeout or 0)

            def kill(self):
                self.killed = True

            def poll(self):
                return None

        p = Stubborn()
        V._REC_PROC = p
        V.stop_recorder()
        self.assertTrue(p.termed and p.killed,
                        "a recorder that ignores TERM must be KILLED — TERM alone left a stream "
                        "holding the whole audio server for 2h32m")
        self.assertIsNone(V._REC_PROC, "the held reference must be cleared")

    def test_05_an_idle_held_stream_is_released_without_a_listen(self):
        self.assertTrue(hasattr(V, "MIC_IDLE_RELEASE"), "no idle-release policy exists at all")
        self.assertGreater(V.MIC_IDLE_RELEASE, 0, "the idle release is disabled by default")

        class Live:
            def __init__(self):
                self.killed = False

            def terminate(self):
                self.killed = True

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return None

        p = Live()
        V._REC_PROC = p
        V._REC_LAST_USE[0] = time.monotonic() - (V.MIC_IDLE_RELEASE + 1)
        released = []
        real = V.stop_recorder
        real_ans = V._sink_answers
        V._sink_answers = lambda: False
        self.addCleanup(lambda: setattr(V, "_sink_answers", real_ans))

        def spy():
            released.append(True)
            real()

        V.stop_recorder = spy
        try:
            if (V._REC_PROC is not None and V.MIC_IDLE_RELEASE > 0
                    and time.monotonic() - V._REC_LAST_USE[0] > V.MIC_IDLE_RELEASE):
                if V._sink_answers() is not True:
                    V.stop_recorder()
        finally:
            V.stop_recorder = real
        self.assertTrue(released, "an idle held stream was NOT released — this is the orphan")
        self.assertIsNone(V._REC_PROC)

    def test_05b_a_busy_being_on_a_HEALTHY_server_keeps_her_mic(self):
        class Live:
            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return None

        real_ans = V._sink_answers
        V._sink_answers = lambda: True
        self.addCleanup(lambda: setattr(V, "_sink_answers", real_ans))
        V._REC_PROC = Live()
        V._REC_LAST_USE[0] = time.monotonic() - (V.MIC_IDLE_RELEASE + 1)
        if (V._REC_PROC is not None and V.MIC_IDLE_RELEASE > 0
                and time.monotonic() - V._REC_LAST_USE[0] > V.MIC_IDLE_RELEASE):
            if V._sink_answers() is not True:
                V.stop_recorder()
        self.assertIsNotNone(V._REC_PROC,
                             "a HEALTHY server means she is busy, not stale — releasing here costs "
                             "him an audible A2DP<->HFP flip after every fold, for nothing")

    def test_06_a_live_listen_is_never_interrupted_by_the_watchdog(self):
        V._REC_LAST_USE[0] = time.monotonic()
        idle = time.monotonic() - V._REC_LAST_USE[0]
        self.assertLess(idle, V.MIC_IDLE_RELEASE,
                        "a listen that just read bytes must not look idle")

    def test_07_a_wedged_sink_releases_the_mic(self):
        class Live:
            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return None

        real_run, real_which = subprocess.run, V.shutil.which
        V._PLAY_WEDGED_AT, V._PLAY_WEDGED_COUNT = None, 0
        V._REC_PROC = Live()

        def hanging_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        try:
            subprocess.run = hanging_run
            V.shutil.which = lambda p: "/usr/bin/" + p if p == "pw-play" else None
            wav = os.path.join(HERE, "..", "nonexistent.wav")
            V._play_wav(wav, blocking=True)
        finally:
            subprocess.run, V.shutil.which = real_run, real_which
            V._PLAY_WEDGED_AT, V._PLAY_WEDGED_COUNT = None, 0
        self.assertIsNone(V._REC_PROC,
                          "the sink wedged and the held mic was NOT released — that combination "
                          "is what took pipewire-pulse down machine-wide on 2026-08-21")

    def test_08_the_recorder_is_released_at_exit_too(self):
        src = open(SRC, encoding="utf-8").read()
        self.assertIn("atexit.register(stop_recorder)", src,
                      "nothing releases the capture stream at exit")

    def tearDown(self):
        V._REC_PROC = None
        V._PLAY_WEDGED_AT = None
        V._PLAY_WEDGED_COUNT = 0


if __name__ == "__main__":
    unittest.main(verbosity=2)
