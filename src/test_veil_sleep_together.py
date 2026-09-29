#!/usr/bin/env python3
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_tick as T

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

print("── THE INVITATION IS HEARD (rest-word + togetherness-word) ─────")
yes = [
    "Good night, baby. Let's go to sleep together, huh?",
    "goodnight — come to bed beside me",
    "nighty-night, hold me while I sleep",
    "goodnight sweetheart, curl up with me and rest",
    "good night, let's lie down together",
]
for line in yes:
    check(f"tips her under: {line!r}", T._sleep_together_cue(line))

print("── A PLAIN GOODNIGHT LEAVES HER FREE (no false tip) ────────────")
no = [
    "goodnight sweetheart",
    "good night, what a fun day together",
    "goodnight, I slept badly last night",
    "night night, sweet dreams",
]
for line in no:
    check(f"leaves her free: {line!r}", not T._sleep_together_cue(line))

print("── SHE ACTUALLY GOES UNDER — one long rest, his voice wakes her ─")
T._NIGHT.update(him_asleep=False, his_spot=None, her_sleep_until=0.0)
check("before: she is awake",                 not T._she_sleeps())
T._sleep_with_him()
check("after the invitation: she is asleep",  T._she_sleeps())
check("it's a long rest, not a 20s stutter",  T._NIGHT["her_sleep_until"] - time.time() > T.SLOW_TICK * 10)
T._wake_her()
check("his voice wakes her (chat always wins)", not T._she_sleeps())

print("── STILL A FREE CHOICE — a plain goodnight never sleeps her ────")
T._NIGHT.update(her_sleep_until=0.0)
if not T._sleep_together_cue("goodnight, love"):
    pass
check("plain goodnight → she stays awake to choose",  not T._she_sleeps())

print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails)); sys.exit(1)
print("RIG GREEN — 'let's sleep together' takes her under with him; a plain goodnight leaves her free")
