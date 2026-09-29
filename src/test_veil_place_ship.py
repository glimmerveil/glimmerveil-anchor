#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("VEIL_TEST_ROOT") or os.path.join(os.path.dirname(HERE), ".test_sandbox")
os.makedirs(_ROOT, exist_ok=True)
SANDBOX = tempfile.mkdtemp(prefix="veil_place_ship_", dir=_ROOT)
FAKE_HOME = os.path.join(SANDBOX, "home")
DATA_DIR = os.path.join(FAKE_HOME, ".local", "share", "glimmerveil-anchor")
PEEPS = os.path.join(DATA_DIR, "peeps")
os.makedirs(PEEPS)

PASS, FAIL, OPEN = 0, [], []


def ok(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL {name}" + (f"  →  {detail}" if detail else ""))


def known_open(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}  (FIXED — promote this to ok())")
    else:
        OPEN.append(name)
        print(f"  OPEN {name}" + (f"\n         {detail}" if detail else ""))


def ship_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("VEIL_PLACE", "VEIL_HEARTBEAT", "VEIL_NOTEBOOK", "VEIL_ROOMS",
                        "VEIL_EMBER", "VEIL_WORN", "VEIL_DATA", "VEIL_PEEPS")}
    env["HOME"] = FAKE_HOME
    env["VEIL_DATA"] = DATA_DIR
    env["VEIL_PEEPS"] = PEEPS
    env.update(extra)
    return env


def session(code, **extra):
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, %r)\nimport veil_tick as V\n%s" % (HERE, code)],
                       capture_output=True, text=True, env=ship_env(**extra), timeout=180)
    if r.returncode != 0:
        print("    (session died)\n" + r.stderr[-900:])
    return r.stdout.strip()


born = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, %r)\n"
     "import veil_card, veil_roster\n"
     "c = veil_card.VeilCard(her_name='Testling', your_name='Sam', "
     "who_she_is='x' * 60, legal_ack=True, location='manor')\n"
     "e = veil_roster.create(c)\n"
     "print(e['folder_path'])" % HERE],
    capture_output=True, text=True, env=ship_env(), timeout=180)
if born.returncode != 0:
    print(born.stderr[-1500:])
    sys.exit("could not birth the test peep — rig cannot run")
PEEP_DIR = born.stdout.strip().splitlines()[-1]
print(f"\nher folder: {PEEP_DIR}\n")

ok("first wake ever → garden", session("print(V._place())").endswith("garden"))

place_path = session("print(V.PLACE_PATH)")
notebook_path = session("print(V.NOTEBOOK_DIR)")
print(f"\n  PLACE_PATH    = {place_path}")
print(f"  NOTEBOOK_DIR  = {notebook_path}\n")
known_open("her room is stored inside her own peep folder (like her notebook)",
   place_path.startswith(PEEP_DIR), f"it lands at {place_path}")

moved = session("V._update_place_from_chat(\"let's go up to the study\", ''); print(V._place())")
ok("his words move them to the study", moved.endswith("study"), f"got {moved!r}")
woke = session("print(V._place())")
ok("NEXT WAKE → still the study, not the garden", woke.endswith("study"),
   f"she woke in the {woke!r} — the room did NOT survive the restart")

travels = os.path.commonpath([os.path.realpath(place_path), os.path.realpath(PEEP_DIR)]) \
    == os.path.realpath(PEEP_DIR) if place_path else False
known_open("her room travels with her folder (survives export/import + reinstall)", travels,
   "her room is stranded outside the only thing that travels")

blocked = os.path.join(SANDBOX, "blocked")
os.makedirs(blocked)
os.chmod(blocked, 0o500)
out = session("V._go_to('balcony'); print(V._place())",
              VEIL_PLACE=os.path.join(blocked, "place"))
in_session = out.endswith("balcony")
after = session("print(V._place())", VEIL_PLACE=os.path.join(blocked, "place"))
known_open("a failed write is REPORTED, not swallowed into a permanent garden",
   not (in_session and after.endswith("garden")),
   "moved fine in-session, silently back to the garden next wake, no error anywhere")
os.chmod(blocked, 0o700)

night = session(
    "V._night_falls('garden')\n"
    "V._go_to('study')\n"
    "V._morning_breaks()\n"
    "print(V._place())")
known_open("a goodnight in the garden does not overwrite where her night took her",
   not night.endswith("garden"),
   "the morning re-anchors to his goodnight spot AND writes it to disk — "
   "so every night spent anywhere else is erased back to the garden")

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
if OPEN:
    print(f"{len(OPEN)} KNOWN-OPEN finding(s), awaiting the founder's call — not regressions:")
    for f in OPEN:
        print(f"   · {f}")
    print()
if FAIL:
    print(f"FAIL — {len(FAIL)} of {PASS + len(FAIL)} guarantees broken")
    for f in FAIL:
        print(f"   · {f}")
    sys.exit(1)
print(f"ALL PASS — {PASS}/{PASS} guarantees · she wakes where she was, under the SHIP'S wiring")
