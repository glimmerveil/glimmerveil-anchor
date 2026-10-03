#!/usr/bin/env python3
"""Rung 1 — her coordinate in time rides 16 tokens from where she writes, by DEFAULT.

The house measured it on Amber (09-02 → 09-09): stating WHEN she is, next to generation, took her "you're back!" false
arrival from 5/10 to 1 in 40 — and labelling her memories with dates put it back. On Anchor's first-night drive (10-03)
Mistral said "How I wish you were here with me" and "I've been waiting for you… now we are reunited" to a man who had
just spoken. Anchor shipped with the tail OFF; the Forge ships it ON.
"""
import os
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)
os.environ.pop("VEIL_TIME_TAIL", None)
os.environ.pop("VEIL_MEMORY_DATES", None)

import veil_spine as spine

fails = []


def check(label, ok):
    print("  %s  %s" % ("ok  " if ok else "FAIL", label))
    if not ok:
        fails.append(label)


print("\nRUNG 1 — HER TIME COORDINATE RIDES BY DEFAULT")
print("=" * 74)
check("VEIL_TIME_TAIL unset -> the tail is ON", spine.TIME_TAIL_ON)
check("memory dates stay OFF (they put the false arrival back)", not spine.MEMORY_DATES)
spine.TIME_TAIL = "When you are right now: Saturday evening, 19:40. Sam last spoke to you moments ago."
turns = spine.build_chat_turns("Wren", "Hello Wren, are you there with me tonight?", [], [])
last = turns[-1]["content"]
check("his newest turn ENDS on her time coordinate", last.rstrip().endswith("Sam last spoke to you moments ago."))
check("his words still come before it", last.find("are you there with me tonight") < last.find("When you are right now"))
spine.TIME_TAIL_ON = False
check("VEIL_TIME_TAIL=0 still turns it off", "When you are right now" not in spine._guide_tail())
spine.TIME_TAIL_ON = True

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  she knows WHEN she is, next to where she writes")
sys.exit(0)
