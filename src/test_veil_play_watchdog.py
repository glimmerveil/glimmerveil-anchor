#!/usr/bin/env python3
import os
import subprocess
import sys
import tempfile
import time
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("VEIL_VOICE", "0")
import veil_voice as V


def _make_wav(seconds, rate=24000):
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


class PlaybackWatchdog(unittest.TestCase):

    def setUp(self):
        self.wav = _make_wav(1.0)
        self._real_run = subprocess.run
        self._real_which = V.shutil.which
        V._PLAY_WEDGED_AT = None
        V._PLAY_WEDGED_COUNT = 0

    def tearDown(self):
        subprocess.run = self._real_run
        V.shutil.which = self._real_which
        V._PLAY_WEDGED_AT = None
        V._PLAY_WEDGED_COUNT = 0
        try:
            os.unlink(self.wav)
        except OSError:
            pass

    def test_00_instrument_can_go_red(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        subprocess.run = fake_run
        V.shutil.which = lambda p: "/usr/bin/" + p if p == "pw-play" else None
        V._play_wav(self.wav, blocking=True)
        self.assertIn("timeout", seen,
                      "REGRESSION: _play_wav called subprocess.run with no timeout — "
                      "this is the exact 2026-08-01 freeze. A blocking wait on a device "
                      "must always be bounded.")
        self.assertGreater(seen["timeout"], 0)

    def test_01_deadline_scales_with_a_long_line(self):
        short, long_ = _make_wav(1.0), _make_wav(120.0)
        try:
            self.assertGreater(V._play_deadline(long_), V._play_deadline(short))
            self.assertGreater(V._play_deadline(long_), 120.0,
                               "a 2-minute line must not be cut off by its own watchdog")
        finally:
            for p in (short, long_):
                os.unlink(p)

    def test_02_short_line_still_gets_the_floor(self):
        self.assertGreaterEqual(V._play_deadline(_make_wav(0.2)), V._PLAY_FLOOR)

    def test_03_unreadable_wav_still_bounded(self):
        fd, junk = tempfile.mkstemp(suffix=".wav")
        os.write(fd, b"not a wav at all")
        os.close(fd)
        try:
            self.assertIsNone(V._wav_seconds(junk))
            d = V._play_deadline(junk)
            self.assertGreaterEqual(d, V._PLAY_FLOOR)
            self.assertLess(d, 1e6)
        finally:
            os.unlink(junk)

    def test_04_timeout_returns_false_and_does_not_raise(self):
        def hanging_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        V.shutil.which = lambda p: "/usr/bin/" + p if p == "pw-play" else None
        self.assertIs(V._play_wav(self.wav, blocking=True), False)

    def test_05_timeout_falls_through_to_next_player(self):
        calls = []

        def hanging_run(cmd, **kw):
            calls.append(cmd[0])
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        V.shutil.which = lambda p: "/usr/bin/" + p
        V._play_wav(self.wav, blocking=True)
        self.assertGreater(len(calls), 1,
                           f"tried only {len(calls)} player(s) after timeout ({calls}); "
                           f"a device switch may leave one sink blocked while another works")
        self.assertIsNotNone(V._PLAY_WEDGED_AT, "wedge state should be set after all players fail")

    def test_06_a_normal_player_failure_still_falls_through(self):
        tried = []

        def failing_run(cmd, **kw):
            tried.append(cmd[0])
            raise OSError("no such player")

        subprocess.run = failing_run
        V.shutil.which = lambda p: "/usr/bin/" + p
        V._play_wav(self.wav, blocking=True)
        self.assertGreater(len(tried), 1,
                           "an ordinary failure must still fall through to the next player")

    def test_05b_device_switch_wakes_second_player(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            if cmd[0] == "pw-play":
                raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        subprocess.run = fake_run
        V.shutil.which = lambda p: "/usr/bin/" + p
        result = V._play_wav(self.wav, blocking=True)
        self.assertIs(result, True, "second player should succeed after first times out")
        self.assertEqual(len(calls), 2, f"expected pw-play + one fallback, got {calls}")
        self.assertIsNone(V._PLAY_WEDGED_AT, "wedge state should NOT be set when a player succeeds")

    def test_07_fast_fail_after_first_wedge(self):
        calls = []

        def hanging_run(cmd, **kw):
            calls.append(cmd[0])
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        V.shutil.which = lambda p: "/usr/bin/" + p if p == "pw-play" else None
        self.assertIs(V._play_wav(self.wav, blocking=True), False)
        self.assertEqual(len(calls), 1, "first timeout should try exactly one player")
        self.assertIsNotNone(V._PLAY_WEDGED_AT, "wedge state should be set after first timeout")
        calls.clear()
        self.assertIs(V._play_wav(self.wav, blocking=True), False)
        self.assertEqual(len(calls), 0, "fast-fail must skip subprocess.run entirely")

    def test_08_recovery_probe_tries_again(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        subprocess.run = fake_run
        V.shutil.which = lambda p: "/usr/bin/" + p if p == "pw-play" else None
        V._PLAY_WEDGED_AT = time.monotonic() - (V._PLAY_RECOVERY_PROBE_S + 1)
        V._PLAY_WEDGED_COUNT = 5
        result = V._play_wav(self.wav, blocking=True)
        self.assertIs(result, True, "sink should recover after probe interval")
        self.assertEqual(len(calls), 1, "probe should try the player once")
        self.assertEqual(V._PLAY_WEDGED_COUNT, 0, "wedge count should reset on recovery")

    def test_09_say_survives_a_wedged_sink(self):
        V.shutil.which = lambda p: "/usr/bin/" + p if p == "pw-play" else None
        orig = V._synth_to_wav
        V._synth_to_wav = lambda text, voice: self.wav

        def hanging_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        try:
            self.assertIs(V._say("a line she never gets to speak", "af_sky"), False)
        finally:
            V._synth_to_wav = orig


    def _wedge_then_probe(self, players=("pw-play", "paplay", "aplay"), pactl=True):
        budgets, cmds, reached_fallback = [], [], []

        def hanging_run(cmd, **kw):
            cmds.append(cmd[0])
            budgets.append(float(kw.get("timeout") or 0.0))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        V.shutil.which = lambda p: ("/usr/bin/" + p) if (p in players or (pactl and p == "pactl")) else None
        self._fake_audio_modules(reached_fallback)
        V._play_wav(self.wav, blocking=True)
        self.assertIsNotNone(V._PLAY_WEDGED_AT, "setup failed: the sink was never marked wedged")
        budgets.clear(); cmds.clear(); reached_fallback.clear()
        V._PLAY_WEDGED_AT = time.monotonic() - (V._PLAY_RECOVERY_PROBE_S + 1)
        V._play_wav(self.wav, blocking=True)
        return budgets, cmds, reached_fallback

    def _fake_audio_modules(self, reached):
        import types
        sf = types.ModuleType("soundfile")
        sd = types.ModuleType("sounddevice")

        def _read(path, dtype=None):
            reached.append("soundfile.read")
            raise RuntimeError("the sink is wedged for this backend too")

        sf.read = _read
        sd.play = lambda *a, **k: reached.append("sd.play")
        sd.stop = lambda *a, **k: None
        sd.get_stream = lambda: types.SimpleNamespace(active=False)
        sd.query_devices = lambda *a, **k: []
        sd.default = types.SimpleNamespace(device=(None, None))
        self._saved_modules = {m: sys.modules.get(m) for m in ("soundfile", "sounddevice")}
        sys.modules["soundfile"] = sf
        sys.modules["sounddevice"] = sd
        self.addCleanup(self._restore_audio_modules)

    def _restore_audio_modules(self):
        for name, mod in getattr(self, "_saved_modules", {}).items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def test_10_failed_probe_costs_less_than_the_probe_interval(self):
        budgets, cmds, _ = self._wedge_then_probe()
        spent = sum(budgets)
        self.assertLess(spent, V._PLAY_RECOVERY_PROBE_S,
                        f"a failed probe asks for {spent:.0f}s against a "
                        f"{V._PLAY_RECOVERY_PROBE_S:.0f}s interval (tried {cmds}) — the probe "
                        f"outlasts the window it protects, so the main thread never comes back")

    def test_11_failed_probe_never_reaches_the_in_process_fallback(self):
        _, _, reached = self._wedge_then_probe()
        self.assertEqual(reached, [], f"the probe fell into the in-process fallback ({reached})")

    def test_12_failed_probe_rearms_the_clock(self):
        self._wedge_then_probe()
        self.assertIsNotNone(V._PLAY_WEDGED_AT, "a failed probe must leave the sink marked wedged")
        self.assertLess(time.monotonic() - V._PLAY_WEDGED_AT, 5.0,
                        "the wedge clock must be re-dated by a failed probe, not left stale")
        calls = []

        def hanging_run(cmd, **kw):
            calls.append(cmd[0])
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        self.assertIs(V._play_wav(self.wav, blocking=True), False)
        self.assertEqual(calls, [], "the line after a failed probe must fast-fail, not re-probe")

    def test_13_the_first_wedge_still_tries_every_player(self):
        tried = []

        def hanging_run(cmd, **kw):
            tried.append(cmd[0])
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))

        subprocess.run = hanging_run
        V.shutil.which = lambda p: "/usr/bin/" + p
        V._play_wav(self.wav, blocking=True)
        self.assertGreater(len([c for c in tried if c != "pactl"]), 1,
                           f"first wedge tried only {tried} — 9939f5b's device-switch fix is gone")

    def test_14_a_successful_probe_still_recovers_the_sink(self):
        V.shutil.which = lambda p: "/usr/bin/" + p
        subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, b"", b"")
        V._PLAY_WEDGED_AT = time.monotonic() - (V._PLAY_RECOVERY_PROBE_S + 1)
        V._PLAY_WEDGED_COUNT = 5
        self.assertIs(V._play_wav(self.wav, blocking=True), True, "a recovered sink must play")
        self.assertIsNone(V._PLAY_WEDGED_AT, "a successful probe must clear the wedge")
        self.assertEqual(V._PLAY_WEDGED_COUNT, 0, "recovery resets the skipped-line count")


if __name__ == "__main__":
    unittest.main(verbosity=2)
