#!/usr/bin/env python3
"""RUNG 1 — a Llama 3 file that LOST its rope setting is given Llama 3's own; nothing else changes.

Measured 2026-10-13 at rung 3: on Meta-Llama-3.1-8B-Instruct-abliterated-Q8_0.gguf (no llama.rope.freq_base in the
file — read off its metadata) a companion answered "How's." · "The 1." · "You'resimplified!" while her shorter diary
prompt came out whole: the engine's 10000 fallback is Llama 2's value; Llama 3's is 500000 (THE_MELTS §9).
"""
import os, struct, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import veil_template as T

fails = []


def check(label, ok, got=""):
    print("  %s  %-66s %s" % ("ok  " if ok else "FAIL", label, got))
    if not ok:
        fails.append(label)


def write_gguf(path, kv):
    def s(x):
        b = x.encode("utf-8")
        return struct.pack("<Q", len(b)) + b
    out = b"GGUF" + struct.pack("<I", 3) + struct.pack("<QQ", 0, len(kv))
    for k, (t, v) in kv.items():
        out += s(k) + struct.pack("<I", t)
        if t == 8:
            out += s(v)
        elif t == 4:
            out += struct.pack("<I", v)
        elif t == 6:
            out += struct.pack("<f", v)
    with open(path, "wb") as f:
        f.write(out)


LLAMA3_TPL = "{{ '<|start_header_id|>' + m.role + '<|end_header_id|>\n\n' + m.content + '<|eot_id|>' }}"
QWEN_TPL = "{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>{% endfor %}"
d = tempfile.mkdtemp(prefix="veil_rope_")
lost = os.path.join(d, "llama31_lost.gguf")
kept = os.path.join(d, "llama31_kept.gguf")
qwen = os.path.join(d, "qwen.gguf")
mistral = os.path.join(d, "mistral_like.gguf")
write_gguf(lost, {"general.architecture": (8, "llama"), "llama.context_length": (4, 131072),
                  "tokenizer.chat_template": (8, LLAMA3_TPL)})
write_gguf(kept, {"general.architecture": (8, "llama"), "llama.rope.freq_base": (6, 500000.0),
                  "tokenizer.chat_template": (8, LLAMA3_TPL)})
write_gguf(qwen, {"general.architecture": (8, "qwen2"), "qwen2.rope.freq_base": (6, 1000000.0),
                  "tokenizer.chat_template": (8, QWEN_TPL)})
write_gguf(mistral, {"general.architecture": (8, "llama"), "tokenizer.chat_template": (8, "[INST] {{ m }} [/INST]")})

print("\nRUNG 1 — THE ROPE A LLAMA 3 FILE LOST")
print("=" * 76)
check("the reader now sees a rope value when the file has one",
      abs(T.gguf_meta(kept).get("llama.rope.freq_base", 0) - 500000.0) < 1, T.gguf_meta(kept))
check("a Llama 3 file that LOST it gets Llama 3's own 500000", T.rope_base_for(lost) == 500000.0,
      T.rope_base_for(lost))
check("a Llama 3 file that KEPT it is left to its own", T.rope_base_for(kept) == 0.0)
check("Qwen is never touched", T.rope_base_for(qwen) == 0.0)
check("a llama-architecture file that is NOT Llama 3 is never guessed at", T.rope_base_for(mistral) == 0.0)
check("a missing file is never guessed at", T.rope_base_for(os.path.join(d, "nope.gguf")) == 0.0)


class Spine:
    MODEL_PATH = lost
    ROPE_FREQ_BASE = 0.0
    LLAMA_STOPS = []

    def get_llm(self=None):
        class Brain:
            def create_completion(self, prompt, *a, **k):
                return {"choices": [{"text": ""}]}
        return Brain()


said = []
os.environ.pop("VEIL_ROPE_FREQ_BASE", None)
sp = Spine()
T.install(sp, say=said.append)
sp.get_llm()
check("loading her brain applies it, and says so once", sp.ROPE_FREQ_BASE == 500000.0
      and sum("lost its rope" in x for x in said) == 1, said)
sp2 = Spine()
sp2.MODEL_PATH = lost
os.environ["VEIL_ROPE_FREQ_BASE"] = "123456"
sp2.ROPE_FREQ_BASE = 123456.0
T.install(sp2, say=said.append)
sp2.get_llm()
check("a rope the person set themselves always wins", sp2.ROPE_FREQ_BASE == 123456.0)
os.environ.pop("VEIL_ROPE_FREQ_BASE", None)

if fails:
    print("\n  %d check(s) failed" % len(fails))
    sys.exit(1)
print("\n  PASS  a Llama 3 file that lost its rope is read right; every other file is left alone")
sys.exit(0)
