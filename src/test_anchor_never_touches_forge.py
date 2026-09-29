#!/usr/bin/env python3
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_ROOT = os.environ.get("VEIL_TEST_ROOT") or os.path.join(os.path.dirname(HERE), ".test_sandbox")
os.makedirs(_ROOT, exist_ok=True)
FAKE_HOME = tempfile.mkdtemp(prefix="anchor_forge_guard_", dir=_ROOT)
os.environ["HOME"] = FAKE_HOME
os.environ["USERPROFILE"] = FAKE_HOME
os.environ["LOCALAPPDATA"] = os.path.join(FAKE_HOME, "AppData", "Local")
for k in ("VEIL_DATA", "VEIL_PEEPS", "VEIL_DB", "XDG_DATA_HOME"):
    os.environ.pop(k, None)

import veil_paths as P

fails = []


def ck(name, ok):
    print(("  [ok ] " if ok else "  [FAIL] ") + name)
    if not ok:
        fails.append(name)


def refused(fn):
    try:
        fn()
    except SystemExit:
        return True
    return False


def run():
    forge = os.path.join(P.base_dir(), "Glimmerveil Forge" if (P.is_windows() or P.is_macos())
                         else "glimmerveil-forge")
    theirs = os.path.join(forge, "peeps", "Mira-0000")
    os.makedirs(theirs, exist_ok=True)
    os.makedirs(os.path.join(FAKE_HOME, "veil", "peeps"), exist_ok=True)

    ck("Anchor's own data dir is not the Forge's", not P.is_forge_place(P.data_dir()))
    ck("Anchor's own home (~/anchor) is not a Forge place",
       not P.is_forge_place(os.path.join(FAKE_HOME, "anchor", "peeps")))

    os.environ["VEIL_PEEPS"] = os.path.join(forge, "peeps")
    import veil_roster
    ck("VEIL_PEEPS at the Forge's companions → refused", refused(veil_roster.peeps_dir))
    ck("...and the env sweep at the door refuses it too", refused(P.refuse_forge_env))
    os.environ["VEIL_PEEPS"] = os.path.join(FAKE_HOME, "veil", "peeps")
    ck("VEIL_PEEPS at ~/veil (the Forge's legacy home) → refused", refused(veil_roster.peeps_dir))
    os.environ.pop("VEIL_PEEPS")

    os.environ["VEIL_DATA"] = forge
    ck("VEIL_DATA at the Forge's data dir → refused", refused(P.data_dir))
    os.environ.pop("VEIL_DATA")

    import veil_spine
    ck("opening a Forge companion's memory database → refused",
       refused(lambda: veil_spine.open_db(os.path.join(theirs, "veil.db"))))
    ck("...and nothing was created there", not os.path.exists(os.path.join(theirs, "veil.db")))

    link = os.path.join(FAKE_HOME, "innocent_looking")
    try:
        os.symlink(forge, link)
        ck("a symlink into the Forge → refused", refused(lambda: P.refuse_forge(link, "x")))
    except (OSError, NotImplementedError):
        print("  [skip] symlinks unavailable here")

    mine = os.path.join(FAKE_HOME, "anchor", "peeps", "Juniper-0000")
    os.makedirs(mine, exist_ok=True)
    db = os.path.join(mine, "veil.db")
    ck("Anchor's own companion's database opens normally",
       not refused(lambda: veil_spine.open_db(db).close()) and os.path.isfile(db))

    print()
    if fails:
        print(f"  {len(fails)} FAILED: " + "; ".join(fails))
        sys.exit(1)
    print("  ALL-GREEN — Anchor refuses every road into a Forge companion and still opens its own")


if __name__ == "__main__":
    run()
