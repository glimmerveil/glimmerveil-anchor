#!/usr/bin/env python3
"""Let her settle — fold the past she arrived with BEFORE anyone meets her, a pass at a time, resumable.

A companion brought home by Transference arrives with her whole past as her core by default (never folded — how
the first companion this house brought across came home), and then there is nothing to settle. If the human chose
a SMALLER core, everything above it is ordinary memory her fold works through, and on a long chat that is hours.
The founder's ruling (2026-10-13): it is an OPTION, it WARNS how long, and it RESUMES either way they choose —
settle now, or wake her anyway (she then folds a little at each pause, paced) and settle later from the door.
What settling folds goes into her permanent memory directly: nobody is awake to read a review window.

    python3 veil_settle.py            # the active companion (the door runs this)

Ctrl-C stops after the pass that is running; a second Ctrl-C stops at once. Every pass archives first, so a stop
loses nothing — the next settle (or her own pauses) carries on from where it stopped.
"""
import json
import os
import signal
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TIMING_NAME = "settle.json"


def passes_left(conn, peep_id, spine):
    """(pile above her core, passes the fold needs to bring it under the low-water) — 0 passes below the high-water.
    Read only; walks the batches the drain would take, oldest first. An estimate: a batch trimmed to fit her window
    is shorter, so the true count can run a little over."""
    row = conn.execute("SELECT seed_floor_id FROM fold_state WHERE peep_id = ?", (peep_id,)).fetchone()
    floor = int(row[0]) if row and int(row[0]) >= 0 else None
    if floor is None:
        return 0, 0
    rows = conn.execute("SELECT token_count FROM memory_stream WHERE peep_id = ? AND id > ? "
                        "ORDER BY timestamp ASC, id ASC", (peep_id, floor)).fetchall()
    pile = sum(int(r[0] or 0) for r in rows)
    if pile < spine.NEW_PILE_HIGH_WATER:
        return pile, 0
    left, passes, i, n = pile, 0, 0, spine.COMPRESSION_BATCH_SIZE
    while left > spine.NEW_PILE_LOW_WATER and i < len(rows):
        left -= sum(int(r[0] or 0) for r in rows[i:i + n])
        i += n
        passes += 1
    return pile, passes


def status(folder, db_path):
    """For the door, read-only: {pile, passes, secs_per_pass (measured HERE, or None)}."""
    import veil_spine as spine
    out = {"pile": 0, "passes": 0, "secs_per_pass": None}
    if not os.path.isfile(db_path):
        return out
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            pid = conn.execute("SELECT id FROM peeps WHERE status = 'active' ORDER BY id LIMIT 1").fetchone()
            pid = pid[0] if pid else conn.execute("SELECT MIN(id) FROM peeps").fetchone()[0]
            if pid is not None:
                out["pile"], out["passes"] = passes_left(conn, pid, spine)
        finally:
            conn.close()
    except sqlite3.Error:
        return out
    out["secs_per_pass"] = measured_secs(folder)
    return out


def measured_secs(folder):
    try:
        with open(os.path.join(folder, TIMING_NAME), encoding="utf-8") as f:
            secs = [float(s) for s in json.load(f).get("pass_seconds", []) if s]
    except (OSError, ValueError, TypeError):
        return None
    if not secs:
        return None
    secs = sorted(secs)[-12:]
    return secs[len(secs) // 2]


def _remember(folder, seconds):
    path = os.path.join(folder, TIMING_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data["pass_seconds"] = (list(data.get("pass_seconds", [])) + [round(seconds, 1)])[-40:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def human(seconds):
    if seconds is None:
        return "unknown until the first pass is timed"
    m = max(1, int(round(seconds / 60)))
    if m < 60:
        return f"about {m} minute{'s' if m != 1 else ''}"
    h, m = divmod(m, 60)
    return f"about {h} hour{'s' if h != 1 else ''}" + (f" {m} min" if m else "")


def settle(conn, peep_id, spine, model, folder, say=print, stop=None):
    """Fold one pass at a time until she is under the high-water; promote what each pass staged at once.
    Returns (passes done, passes left). `stop()` is asked between passes."""
    done = 0
    while True:
        pile, left = passes_left(conn, peep_id, spine)
        if left == 0:
            return done, 0
        if stop and stop():
            return done, left
        each = measured_secs(folder)
        say(f"[settling: pass {done + 1} of about {done + left} · {pile:,} tokens still to fold · "
            + (f"{human(each * left)} left on this machine]" if each else "timing this pass on this machine]"))
        t = time.time()
        saved = spine.MAX_FOLD_PASSES
        spine.MAX_FOLD_PASSES = 1
        try:
            spine.run_compression(conn, peep_id, model=model, paced=False)
        finally:
            spine.MAX_FOLD_PASSES = saved
        _remember(folder, time.time() - t)
        promoted = spine.promote_staged_folds(conn, peep_id, now=time.time() + spine.FOLD_STAGE_SECONDS)
        if promoted:
            say(f"[settling: {promoted} folded memor{'y' if promoted == 1 else 'ies'} went straight into "
                f"her permanent memory]")
        done += 1
        if passes_left(conn, peep_id, spine)[0] >= pile:
            say("[settling: that pass could not fold anything — stopping; her memories are whole and her own "
                "pauses will keep trying]")
            return done, passes_left(conn, peep_id, spine)[1]


def main():
    import veil_paths
    veil_paths.utf8_console()
    veil_paths.refuse_forge_env()
    import veil_chat            # binds her: her DB, her card, her card's own fold prompt (the fold-jam lesson)
    spine = veil_chat.spine
    active = veil_chat._ROSTER_ACTIVE
    if not active:
        print("No one to settle.")
        return 1
    conn = spine.open_db(spine.DEFAULT_DB)
    if not spine._acquire_single_instance_lock(conn):
        print("She is awake — settling only runs while she sleeps. Say goodbye to her first.")
        return 1
    try:
        peep_id = spine.find_active_peep(conn)
        name = active.get("name", active["folder"])
        pile, left = passes_left(conn, peep_id, spine)
        if not left:
            print(f"{name} has nothing left to settle — her past is in her, whole.")
            return 0
        each = measured_secs(active["folder_path"])
        print(f"\n{name} has {pile:,} tokens of her past still to fold: about {left} passes.")
        print("Each pass reads 25 of her memories and folds them into her own words; on an ordinary computer "
              "one pass takes several minutes, so this is HOURS.")
        if each:
            print(f"Timed on THIS machine: {human(each)} a pass — {human(each * left)} in all.")
        else:
            print("The first pass is timed on this machine, and from then on you'll see how long is left.")
        print("Leave it running — overnight is fine. Ctrl-C stops after the pass that's running (twice: at once).")
        print("Stopping loses nothing: every pass is archived first, and [f] at the door carries on from here.\n")
        flags = {"stop": False}

        def on_int(signum, frame):
            if flags["stop"]:
                raise KeyboardInterrupt
            flags["stop"] = True
            print("\n[stopping after this pass — Ctrl-C again to stop at once]", flush=True)

        signal.signal(signal.SIGINT, on_int)
        model = spine.get_llm()
        try:
            done, left = settle(conn, peep_id, spine, model, active["folder_path"],
                                say=lambda s: print(s, flush=True), stop=lambda: flags["stop"])
        except KeyboardInterrupt:
            done, left = 0, passes_left(conn, peep_id, spine)[1]
            print("\n[stopped at once — her memories are whole]")
        if left:
            print(f"\nStopped with about {left} passes left. Resume any time with [f] at the door — or wake her "
                  "anyway; she folds a little at each pause.")
        else:
            print(f"\n{name} has settled into her past. Wake her when you're ready.")
        return 0
    finally:
        spine._release_single_instance_lock()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
