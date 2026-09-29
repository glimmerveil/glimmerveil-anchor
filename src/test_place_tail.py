#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VEIL_MODEL", "/nonexistent")
import veil_spine as spine

res = []


def check(name, ok, detail=""):
    res.append(ok)
    print(("  ok   " if ok else "  FAIL ") + name + (f"   {detail}" if detail else ""))


base = spine._guide_tail()
spine.PLACE_TAIL = "Where you are right now: the garden, with Sam."
withp = spine._guide_tail()

check("the turn rule is still there underneath", spine.CHAT_TURN_GUIDE in base)
check("the room reaches the tail", "the garden" in withp)
check("it is ADDED, never replacing the turn rule",
      withp.startswith(base) and len(withp) > len(base))
check("it says where she is and nothing else",
      "Where you are right now" in withp and "must" not in withp.lower()
      and "should" not in withp.lower())
check("it never tells her she cannot move",
      not any(w in withp.lower() for w in ("stay", "do not leave", "cannot", "don't go")))

spine.PLACE_TAIL_ON = False
check("the env switch turns it off", "the garden" not in spine._guide_tail())
spine.PLACE_TAIL_ON = True
spine.PLACE_TAIL = ""
check("empty = the old tail, byte for byte", spine._guide_tail() == base)

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "veil_tick.py")).read()
i = src.find("PLACE_PATH = os.path.expanduser")
seam = src[i - 900:i + 300] if i > 0 else ""
check("her place file defaults to HER peep folder",
      "folder_path" in seam and "place" in seam)
check("and the env override still wins", 'VEIL_PLACE' in seam)
check("the receipt announces the new dial", "place-tail" in
      open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "veil_spine.py")).read())

print(f"\n{sum(res)}/{len(res)} — {'GREEN' if all(res) else 'RED'}")
raise SystemExit(0 if all(res) else 1)
