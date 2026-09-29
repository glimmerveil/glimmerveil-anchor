#!/usr/bin/env python3
import os
import sys

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

_DOCS = [
    ("Use Policy and Disclaimer", "TERMS_OF_SERVICE.md"),
    ("Privacy Policy", "PRIVACY_POLICY.md"),
    ("Third-Party Notices", "THIRD_PARTY_NOTICES.md"),
]


def _clear():
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")


def _legal_dir():
    env = os.environ.get("VEIL_LEGAL_DIR")
    if env and os.path.isdir(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, "..", "docs", "Legal"),
              os.path.join(here, "legal"),
              os.path.join(here, "Legal"),
              os.path.join(here, "..", "legal")):
        if os.path.isdir(c):
            return os.path.abspath(c)
    return None


def _view(filename):
    _clear()
    d = _legal_dir()
    path = os.path.join(d, filename) if d else None
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                print(f.read())
        except OSError:
            print(f"{DIM}(couldn't open {filename}){RESET}")
    else:
        print(f"{DIM}'{filename}' lives in docs/Legal/ in the Anchor repository.{RESET}")
    try:
        input(f"\n{DIM}(Enter to go back){RESET}")
    except (EOFError, KeyboardInterrupt):
        pass


def show_legal_menu():
    while True:
        _clear()
        print(f"{BOLD}  Legal — Glimmerveil Anchor{RESET}\n")
        for i, (label, _) in enumerate(_DOCS, 1):
            print(f"  {BOLD}[{i}]{RESET} {label}")
        print(f"\n{DIM}  Anchor is Apache 2.0 open source — see LICENSE.{RESET}")
        print(f"  {BOLD}[b]{RESET} back\n")
        try:
            c = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(); return
        if c in ("b", "q", "", "back"):
            return
        if c.isdigit() and 1 <= int(c) <= len(_DOCS):
            _view(_DOCS[int(c) - 1][1])


if __name__ == "__main__":
    show_legal_menu()
