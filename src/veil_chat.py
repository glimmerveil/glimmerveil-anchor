#!/usr/bin/env python3
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_spine as spine

import veil_paths
spine.MODEL_PATH = veil_paths.model_path()
spine.DEFAULT_DB = os.environ.get("VEIL_DB", os.path.expanduser("~/anchor/veil.db"))
spine.DEFAULT_HISTORY = os.environ.get("VEIL_HISTORY", os.path.expanduser("~/anchor/veil_history.json"))

import veil_roster

_ROSTER_ACTIVE = None
if not os.environ.get("VEIL_DB") and not any(
        a == "--db" or a.startswith("--db=") for a in sys.argv):
    _ROSTER_ACTIVE = veil_roster.active_peep()
    if _ROSTER_ACTIVE:
        spine.DEFAULT_DB = _ROSTER_ACTIVE["db"]
        if not os.environ.get("VEIL_HISTORY"):
            spine.DEFAULT_HISTORY = os.path.join(
                _ROSTER_ACTIVE["folder_path"], veil_roster.HISTORY_NAME)

spine.ROPE_FREQ_BASE = float(os.environ.get("VEIL_ROPE_FREQ_BASE", "0.0"))
spine.LLAMA_STOPS = ["<|im_end|>", "<|endoftext|>"]
spine.N_GPU_LAYERS = int(os.environ.get("VEIL_GPU_LAYERS", "0"))
spine.N_BATCH = 64 if spine.N_GPU_LAYERS != 0 else 512


def _render_chat(system, user):
    s = ""
    if system:
        s += "<|im_start|>system\n" + system + "<|im_end|>\n"
    s += "<|im_start|>user\n" + user + "<|im_end|>\n<|im_start|>assistant\n"
    return s


def _render_chat_turns(system, turns, prefill=""):
    s = "<|im_start|>system\n" + (system or "") + "<|im_end|>\n"
    for turn in turns:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        s += "<|im_start|>" + role + "\n" + content + "<|im_end|>\n"
    s += "<|im_start|>assistant\n" + prefill
    return s


spine.render_chat = _render_chat
spine.render_chat_turns = _render_chat_turns

import veil_card

CARD = None
_card_path = os.environ.get("VEIL_CARD_JSON", "")
if not _card_path and _ROSTER_ACTIVE:
    _p = os.path.join(_ROSTER_ACTIVE["folder_path"], veil_roster.CARD_NAME)
    if os.path.isfile(_p):
        _card_path = _p
try:
    CARD = veil_card.load(_card_path or None)
    veil_card.apply_to_spine(spine, CARD)
except FileNotFoundError:
    print("\033[38;5;213m[no card yet — she'll speak from neutral defaults, which is nobody. "
          "Author her first:  python3 veil_card.py]\033[0m", file=sys.stderr)
except Exception as e:
    print(f"\033[38;5;213m[card problem: {e} — fix it, then wake her again.]\033[0m", file=sys.stderr)
    raise SystemExit(1)

spine.AUTO_FOLD = os.environ.get("VEIL_FOLD", "1") == "1"

_orig_save_diary_entry = spine.save_diary_entry


def _save_diary_entry_trimmed(conn, peep_id, content, source="standalone"):
    return _orig_save_diary_entry(conn, peep_id,
                                  spine._trim_to_sentence((content or "").strip()), source=source)


spine.save_diary_entry = _save_diary_entry_trimmed

try:
    import veil_voice
    spine.ara_voice = veil_voice
    _voice_env = os.environ.get("VEIL_VOICE")
    if _voice_env is not None:
        _voice_asked = _voice_env not in ("0", "", "false", "False")
    else:
        try:
            import veil_probe
            _voice_asked = bool(veil_probe.load_settings().get("voice", True))
        except Exception:
            _voice_asked = True
    _timbre = os.environ.get("VEIL_VOICE_NAME", "") or (CARD.voice if CARD else "") or "af_heart"
    veil_voice.KOKORO_VOICE = _timbre
    veil_voice.VOICE_ENABLED = _voice_asked and bool(_timbre)
    spine.VOICE = veil_voice.VOICE_ENABLED
except Exception:
    pass

try:
    import veil_canary as _canary
    _drift = _canary.DriftMeter()
    _orig_generate_guarded = spine.generate_guarded

    def _guarded_with_drift(*a, **k):
        reply = _orig_generate_guarded(*a, **k)
        try:
            if isinstance(reply, str) and _drift.update(reply) == "alarm":
                print(f"\n{spine.DIM}[drift: her voice is tilting toward the bland assistant — "
                      f"re-anchor her (say her anchors). {_drift.report()}]{spine.RESET}",
                      file=sys.stderr)
        except Exception:
            pass
        return reply

    spine.generate_guarded = _guarded_with_drift
except Exception:
    pass


if __name__ == "__main__":
    spine.main()
