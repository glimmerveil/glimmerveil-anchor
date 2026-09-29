#!/usr/bin/env python3
import os, sqlite3, sys, tempfile, time

_SBX = tempfile.mkdtemp(prefix="veil_snapshot_rig.")
for _k, _sub in [("VEIL_DB", "veil.db"), ("VEIL_CARD_JSON", "card.json"),
                 ("VEIL_PEEPS", "peeps"), ("VEIL_PLACE", "place"),
                 ("VEIL_HEARTBEAT", "hb"), ("VEIL_NOTEBOOK", "notebook"),
                 ("VEIL_ROOMS", "rooms"), ("VEIL_EMBER", "ember")]:
    os.environ[_k] = os.path.join(_SBX, _sub)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as S

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

db_path = os.path.join(_SBX, "her", "veil.db")
os.makedirs(os.path.dirname(db_path))
conn = S.open_db(db_path)
ckpt_dir = os.path.join(os.path.dirname(db_path), "checkpoints")

_ctr = [0]
_real_strftime = S.time.strftime
def _rig_strftime(fmt, *a):
    if fmt == "%Y%m%d_%H%M%S":
        _ctr[0] += 1
        return f"20990101_{_ctr[0]:06d}"
    return _real_strftime(fmt, *a)
S.time.strftime = _rig_strftime

print("── KEEP THE NEWEST N ───────────────────────────────────────────")
made = []
for i in range(7):
    out = S._checkpoint_db(conn, reason="prefold")
    check(f"checkpoint {i+1} lands + verifies", out is not None and os.path.isfile(out))
    made.append(out)
left = sorted(os.listdir(ckpt_dir))
check(f"exactly {S.CHECKPOINTS_KEEP} remain after 7 folds", len(left) == S.CHECKPOINTS_KEEP)
check("the survivors are the NEWEST ones",
      set(os.path.join(ckpt_dir, f) for f in left) == set(made[-S.CHECKPOINTS_KEEP:]))

print("── FOREIGN FILES UNTOUCHED ─────────────────────────────────────")
keepsafe = os.path.join(ckpt_dir, "notes_do_not_touch.txt")
open(keepsafe, "w").write("sam's note")
S._checkpoint_db(conn, reason="prefold")
check("non-snapshot file survives pruning", os.path.isfile(keepsafe))

print("── ENV DIAL ────────────────────────────────────────────────────")
S.CHECKPOINTS_KEEP = 2
S._checkpoint_db(conn, reason="prefold")
snaps = [f for f in os.listdir(ckpt_dir) if f.endswith(".db")]
check("keep=2 honored on the next fold", len(snaps) == 2)
S.CHECKPOINTS_KEEP = max(1, int(os.environ.get("VEIL_CHECKPOINTS_KEEP", "4")))

print("── THE NET NEVER THINS FIRST ───────────────────────────────────")
before = set(os.listdir(ckpt_dir))
bad = sqlite3.connect(":memory:")
check("no-disk DB refuses (returns None)", S._checkpoint_db(bad, reason="prefold") is None)
check("a refused checkpoint prunes NOTHING", set(os.listdir(ckpt_dir)) == before)

print()
if fails:
    print(f"RED — {len(fails)} failing: " + ", ".join(fails))
    sys.exit(1)
print("GREEN — rolling snapshots hold: newest 4 kept, net never thins first, foreign files safe.")
