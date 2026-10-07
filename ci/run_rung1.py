#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import time

TESTS = [
    "test_anchor_never_touches_forge.py",
    "test_fold_anchor_line.py",
    "test_fold_detail_floor.py",
    "test_fold_person_frame.py",
    "test_fold_staging_seats.py",
    "test_forge_legal.py",
    "test_place_tail.py",
    "test_veil_audio_invariants.py",
    "test_veil_bookdrop.py",
    "test_veil_brain_swap.py",
    "test_veil_bye_door.py",
    "test_veil_dials_announced.py",
    "test_veil_events.py",
    "test_veil_fold_lock.py",
    "test_veil_fold_return.py",
    "test_veil_ghost.py",
    "test_veil_goodnight.py",
    "test_veil_gpu_detection.py",
    "test_veil_grounding.py",
    "test_veil_lane_freedom.py",
    "test_veil_lane_words.py",
    "test_veil_keep_last_family.py",
    "test_veil_time_tail_default.py",
    "test_veil_one_of_each.py",
    "test_veil_fit_notes.py",
    "test_veil_fold_fit.py",
    "test_veil_loop_drops_kept.py",
    "test_veil_transfer.py",
    "test_veil_melt_guard.py",
    "test_veil_models.py",
    "test_veil_night_drive.py",
    "test_veil_nonspeech.py",
    "test_veil_place.py",
    "test_veil_place_ship.py",
    "test_veil_portaudio_mic.py",
    "test_veil_play_watchdog.py",
    "test_veil_prose_face.py",
    "test_veil_rails_autonomous.py",
    "test_veil_rails.py",
    "test_veil_rails_wiring.py",
    "test_veil_ready_prompt.py",
    "test_veil_recall_lane.py",
    "test_veil_register_carry.py",
    "test_veil_register_dial.py",
    "test_veil_register.py",
    "test_veil_restore.py",
    "test_veil_retrieval_echo.py",
    "test_veil_ritual.py",
    "test_veil_ship.py",
    "test_veil_sleep_together.py",
    "test_veil_snapshot_rolling.py",
    "test_veil_soft_landing.py",
    "test_veil_template.py",
    "test_veil_voice_toggle.py",
    "test_veil_wake_seed.py",
    "test_veil_wardrobe.py",
    "test_veil_watch_diary_retrieval.py",
    "test_veil_windows_input.py",
    "test_veil_world.py",
]
TIMEOUT = 180
GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRATCH = os.environ.get("ANCHOR_CI_SCRATCH", os.path.join(REPO, "ci", ".scratch"))


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    only = sys.argv[1:]
    tests = [t for t in TESTS if not only or t in only]
    missing = [t for t in tests if not os.path.isfile(os.path.join(SRC, t))]
    if missing:
        print("MISSING from src/: %s" % ", ".join(missing))
        return 2
    shutil.rmtree(SCRATCH, ignore_errors=True)
    home = os.path.join(SCRATCH, "home")
    tmp = os.path.join(SCRATCH, "tmp")
    for d in (home, tmp):
        os.makedirs(d)
    env = dict(os.environ)
    env.update({"HOME": home, "USERPROFILE": home, "TMPDIR": tmp, "TEMP": tmp, "TMP": tmp,
                "VEIL_DATA": os.path.join(home, "data"),
                "XDG_DATA_HOME": os.path.join(home, "xdg"),
                "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1"})
    print("rung 1 on %s · python %s · %d tests · scratch %s"
          % (sys.platform, sys.version.split()[0], len(tests), SCRATCH))
    failed = []
    t0 = time.time()
    for t in tests:
        s = time.time()
        try:
            p = subprocess.run([sys.executable, t], cwd=SRC, env=env, timeout=TIMEOUT,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=GROUP)
            rc, out = p.returncode, p.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            rc, out = "TIMEOUT", (e.stdout or b"").decode("utf-8", "replace")
        except KeyboardInterrupt:
            if not sys.platform.startswith("win"):
                raise
            rc, out = "CTRL-C", "a Ctrl-C reached the runner while this test ran\n"
        tail = [ln for ln in out.splitlines() if ln.strip()][-1:] or [""]
        print("%-4s %-36s %5.1fs  %s" % ("ok" if rc == 0 else "FAIL", t, time.time() - s,
                                         tail[0].strip()[:90]))
        if rc != 0:
            failed.append((t, rc, out))
    print("=" * 78)
    print("%d passed, %d failed, %.0fs" % (len(tests) - len(failed), len(failed), time.time() - t0))
    for t, rc, out in failed:
        print("\n----- %s (exit %s) -----\n%s" % (t, rc, out[-6000:]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
