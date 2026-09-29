#!/usr/bin/env python3
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_legal as L

fails = []


def ck(name, ok):
    print(("  [ok ] " if ok else "  [FAIL] ") + name)
    if not ok:
        fails.append(name)


def run():
    d = L._legal_dir()
    ck("the legal folder is found", bool(d))
    for label, fn in L._DOCS:
        ck(f"the menu's '{label}' exists", bool(d) and os.path.isfile(os.path.join(d, fn)))

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "veil_game.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == "veil_legal"}
    ck("no gate at the door: the game calls only the legal menu", called == {"show_legal_menu"})

    print()
    if fails:
        print(f"  {len(fails)} FAILED: " + "; ".join(fails))
        sys.exit(1)
    print("  ALL-GREEN — the legal docs ship and are readable from the menu; nothing blocks the door")


if __name__ == "__main__":
    run()
