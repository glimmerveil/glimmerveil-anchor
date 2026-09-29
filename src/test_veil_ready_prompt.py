#!/usr/bin/env python3
import os

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "veil_tick.py"), encoding="utf-8") as f:
    source = f.read()

ready_voice = '[ready — voice on; speak now · press Enter to switch to text input]'
ready_text = '[ready — text mode; type your message and press Enter · blank ⏎ turns voice on]'

assert ready_voice in source
assert ready_text in source
assert source.index("model = spine.get_llm()") < source.index(ready_voice)
assert source.index("_maybe_first_wake_ritual") < source.index(ready_voice)
assert "if getattr(spine, \"VOICE\", False):" in source

print("✅ RUNG 1 GREEN — the tick door reports voice/text readiness after warm-up")
