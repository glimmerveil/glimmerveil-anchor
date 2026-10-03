#!/usr/bin/env python3
import os
import struct
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix="veil_template_rig_")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("VEIL_CHAT_FORMAT", None)
import veil_template as T

_fails = []
def check(name, cond, got=None):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond or got is None else "   got: %r" % (got,)))
    if not cond:
        _fails.append(name)


def old_render_chat(system, user):
    s = ""
    if system:
        s += "<|im_start|>system\n" + system + "<|im_end|>\n"
    s += "<|im_start|>user\n" + user + "<|im_end|>\n<|im_start|>assistant\n"
    return s


def old_render_chat_turns(system, turns, prefill=""):
    s = "<|im_start|>system\n" + (system or "") + "<|im_end|>\n"
    for turn in turns:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        s += "<|im_start|>" + role + "\n" + content + "<|im_end|>\n"
    s += "<|im_start|>assistant\n" + prefill
    return s


C = T.FAMILIES["chatml"]
cases = [("", "hi"), ("You are Wren.", "hello there"), ("sys\nmulti", "  spaced  ")]
check("ChatML render_chat is byte-identical to the old hard-wired one",
      all(C.render_chat(s, u) == old_render_chat(s, u) for s, u in cases))
turns = [{"role": "user", "content": " a "}, {"role": "user", "content": "b"},
         {"role": "assistant", "content": "c"}, {"role": "system", "content": "d"}, {"content": "e"}]
check("ChatML render_chat_turns is byte-identical (odd roles, empty system, prefill)",
      all(C.render_chat_turns(s, turns, p) == old_render_chat_turns(s, turns, p)
          for s in ("", None, "S") for p in ("", "Wren:")))
check("ChatML stops are unchanged", C.stops == ["<|im_end|>", "<|endoftext|>"], C.stops)

TPL = {
    "chatml": "{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>{% endfor %}",
    "llama3": "{{ '<|start_header_id|>' + m.role + '<|end_header_id|>\n\n' + m.content + '<|eot_id|>' }}",
    "gemma": "{{ '<start_of_turn>' + role + '\n' + content + '<end_of_turn>\n' }}",
    "mistral": "{{ bos_token }}{% if m.role == 'user' %}[INST] {{ m.content }} [/INST]{% endif %}",
    "phi3": "{{ '<|user|>\n' + m.content + '<|end|>\n<|assistant|>\n' }}",
}
for fam, tpl in TPL.items():
    check("detects %s from its chat template" % fam, T.detect({"tokenizer.chat_template": tpl}) == (fam, True))
check("no template, qwen2 architecture -> ChatML, sure", T.detect({"general.architecture": "qwen2"}) == ("chatml", True))
check("no template, gemma2 architecture -> Gemma", T.detect({"general.architecture": "gemma2"}) == ("gemma", True))
check("nothing known -> ChatML, but NOT sure (so she warns)", T.detect({}) == ("chatml", False))


def write_gguf(path, kv, version=3):
    def s(x):
        b = x.encode("utf-8")
        return struct.pack("<Q", len(b)) + b
    out = b"GGUF" + struct.pack("<I", version) + struct.pack("<QQ", 0, len(kv))
    for k, (t, v) in kv.items():
        out += s(k) + struct.pack("<I", t)
        if t == 8:
            out += s(v)
        elif t == 4:
            out += struct.pack("<I", v)
        elif t == 9:
            et, items = v
            out += struct.pack("<IQ", et, len(items))
            for it in items:
                out += s(it) if et == 8 else struct.pack("<f", it)
    with open(path, "wb") as f:
        f.write(out)
    return path


tokens = ["tok%d" % i for i in range(3000)]
llama_file = write_gguf(os.path.join(_TMP, "llama.gguf"), {
    "general.architecture": (8, "llama"),
    "general.name": (8, "Some Llama 3.1 8B"),
    "llama.block_count": (4, 32),
    "tokenizer.ggml.tokens": (9, (8, tokens)),
    "tokenizer.ggml.scores": (9, (6, [0.0] * 3000)),
    "tokenizer.chat_template": (8, TPL["llama3"]),
})
meta = T.gguf_meta(llama_file)
check("reads the chat template past 3000-entry token arrays", meta.get("tokenizer.chat_template") == TPL["llama3"])
check("reads the architecture", meta.get("general.architecture") == "llama")
check("an old v1 file is never misread", T.gguf_meta(write_gguf(os.path.join(_TMP, "v1.gguf"), {}, version=1)) == {})
junk = os.path.join(_TMP, "junk.gguf")
with open(junk, "wb") as f:
    f.write(b"GGUF\x03\x00\x00\x00" + b"\xff" * 40)
check("a truncated or damaged header returns nothing, never a crash", T.gguf_meta(junk) == {})
check("a missing file returns nothing", T.gguf_meta(os.path.join(_TMP, "nope.gguf")) == {})

L = T.FAMILIES["llama3"]
p = L.render_chat_turns("You are Wren.", [{"role": "user", "content": "hi"}], prefill="Wren:")
check("Llama 3 prompt shape", p == "<|start_header_id|>system<|end_header_id|>\n\nYou are Wren.<|eot_id|>"
      "<|start_header_id|>user<|end_header_id|>\n\nhi<|eot_id|>"
      "<|start_header_id|>assistant<|end_header_id|>\n\nWren:", p)
G = T.FAMILIES["gemma"]
p = G.render_chat_turns("You are Wren.", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey"}])
check("Gemma has no system role: it rides at the top of the first user turn, and her side is 'model'",
      p == "<start_of_turn>user\nYou are Wren.\n\nhi<end_of_turn>\n<start_of_turn>model\nhey<end_of_turn>\n"
           "<start_of_turn>model\n", p)
M = T.FAMILIES["mistral"]
p = M.render_chat_turns("You are Wren.", [{"role": "user", "content": "hi"}, {"role": "user", "content": "you there?"}])
check("Mistral: system folded into the first [INST], consecutive user turns kept as their own blocks",
      p == "[INST] You are Wren.\n\nhi [/INST][INST] you there? [/INST]", p)
P = T.FAMILIES["phi3"]
p = P.render_chat("S", "hi")
check("Phi-3 prompt shape", p == "<|system|>\nS<|end|>\n<|user|>\nhi<|end|>\n<|assistant|>\n", p)
check("every family ends a turn on its own stop token",
      all(f.stops and all(isinstance(x, str) and x for x in f.stops) for f in T.FAMILIES.values()))

qwen_file = write_gguf(os.path.join(_TMP, "qwen.gguf"), {
    "general.architecture": (8, "qwen2"), "tokenizer.chat_template": (8, TPL["chatml"])})
spine = types.SimpleNamespace(MODEL_PATH=qwen_file, LLAMA_STOPS=None, get_llm=lambda: FakeLLM(["hi"]))
said = []
T.install(spine, say=said.append)
out = spine.render_chat("S", "hi")
check("installed: a Qwen brain renders ChatML and sets ChatML stops",
      out == old_render_chat("S", "hi") and spine.LLAMA_STOPS == C.stops)
spine.MODEL_PATH = llama_file
out = spine.render_chat_turns("S", [{"role": "user", "content": "hi"}])
check("swap the brain mid-run: the next prompt is Llama 3, with Llama 3 stops",
      out.startswith("<|start_header_id|>system") and spine.LLAMA_STOPS == L.stops, out[:40])
check("she says which format she is using, once per brain",
      said == ["[brain format: ChatML (Qwen and friends)]", "[brain format: Llama 3]"], said)
unknown = write_gguf(os.path.join(_TMP, "odd.gguf"), {"general.architecture": (8, "rwkv")})
spine.MODEL_PATH = unknown
spine.render_chat("S", "hi")
check("an unknown brain falls back to ChatML and says how to override it",
      "VEIL_CHAT_FORMAT" in said[-1] and spine.LLAMA_STOPS == C.stops, said[-1])
os.environ["VEIL_CHAT_FORMAT"] = "gemma"
spine.MODEL_PATH = llama_file
spine.render_chat("S", "hi")
check("VEIL_CHAT_FORMAT overrides detection", spine.LLAMA_STOPS == G.stops)
os.environ.pop("VEIL_CHAT_FORMAT")

Q3 = T.FAMILIES["qwen3"]
check("a Qwen3 template (enable_thinking) is detected as Qwen3",
      T.detect({"tokenizer.chat_template": TPL["chatml"] + "{% if enable_thinking %}{% endif %}"}) == ("qwen3", True))
check("Qwen3 renders ChatML with thinking switched OFF the way its own template does",
      Q3.render_chat("S", "hi") == old_render_chat("S", "hi") + "<think>\n\n</think>\n\n")
check("…and keeps the prefill after the empty think block",
      Q3.render_chat_turns("S", [{"role": "user", "content": "hi"}], "Wren:").endswith("</think>\n\nWren:"))
DS_TPL = "{% for m in messages %}{% if m.role == 'user' %}<｜User｜>{{ m.content }}{% else %}<｜Assistant｜>{{ m.content }}<｜end▁of▁sentence｜>{% endif %}{% endfor %}"
check("a DeepSeek-R1 distill (Qwen arch, DeepSeek template) is DeepSeek, not ChatML",
      T.detect({"general.architecture": "qwen2", "tokenizer.chat_template": DS_TPL}) == ("deepseek", True))
D = T.FAMILIES["deepseek"]
check("DeepSeek prompt shape", D.render_chat_turns("S", [{"role": "user", "content": "hi"}]) == "S<｜User｜>hi<｜Assistant｜>")
check("DeepSeek is marked as a thinker", D.thinks and not C.thinks and not Q3.thinks)

MUSE = ("{% for m in messages %}{% if loop.index0 > 0 and messages[loop.index0 - 1].role == m.role %}"
        "{{ raise_exception('roles must alternate') }}{% endif %}<|start|>{{ m.role }}<|message|>{{ m.content }}<|eot|>"
        "{% endfor %}{% if add_generation_prompt %}<|start|>assistant<|message|>{% endif %}")
check("an unknown template is rendered by the model's OWN template, not guessed",
      T.detect({"tokenizer.chat_template": MUSE}) == ("jinja", True))
J = T.JinjaFamily(MUSE, "<|begin|>", "<|end|>", "Muse")
p = J.render_chat_turns("S", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}], "Wren:")
check("own-template render", p == "<|start|>system<|message|>S<|eot|><|start|>user<|message|>a<|eot|>"
      "<|start|>assistant<|message|>b<|eot|><|start|>assistant<|message|>Wren:", p)
p = J.render_chat_turns("S", [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])
check("a template that refuses back-to-back user turns gets them merged instead of crashing",
      "<|start|>user<|message|>a\n\nb<|eot|>" in p, p)
check("its end-of-turn marks become stops", "<|eot|>" in J.stops and "<|end|>" in J.stops, J.stops)
muse_file = write_gguf(os.path.join(_TMP, "muse.gguf"), {
    "general.architecture": (8, "muse-glimmer"), "general.name": (8, "Muse"),
    "tokenizer.ggml.tokens": (9, (8, ["<|begin|>", "x", "<|end|>"])),
    "tokenizer.ggml.bos_token_id": (4, 0), "tokenizer.ggml.eos_token_id": (4, 2),
    "tokenizer.chat_template": (8, MUSE)})
fam, sure, capable = T.family_for(muse_file)
check("from a real file: own template, bos/eos read from the token table",
      isinstance(fam, T.JinjaFamily) and fam.bos == "<|begin|>" and fam.eos == "<|end|>" and sure and capable)
mm = write_gguf(os.path.join(_TMP, "mmproj.gguf"), {"general.architecture": (8, "clip"), "general.type": (8, "mmproj")})
check("a vision adapter (mmproj) is flagged as not a chat model", T.family_for(mm)[2] is False)


def think(pieces, expect=False):
    f = T.ThinkFilter(expect)
    return "".join(f.feed(p) for p in pieces) + f.flush()


check("no think block: text passes through untouched", think(["Hel", "lo ", "there"]) == "Hello there")
check("a reply starting with '<3' is not mistaken for thinking", think(["<", "3 you"]) == "<3 you")
check("a <think> block is removed, she speaks only after it",
      think(["<th", "ink>\nhm, he", " wants…</thi", "nk>\n\n", "Hi love"]) == "Hi love")
check("a thinker whose prompt already opened the block: hidden until </think>",
      think(["he wants a hello", "</think>", " Hi"], expect=True) == "Hi")
check("thinking that never closes is never spoken", think(["<think>", "endless reasoning"]) == "")


class FakeLLM:
    def __init__(self, pieces):
        self.pieces, self.seen = pieces, None

    def create_completion(self, prompt, **k):
        self.seen = k
        def gen():
            for i, p in enumerate(self.pieces):
                yield {"choices": [{"text": p, "finish_reason": "stop" if i == len(self.pieces) - 1 else None}]}
        return gen() if k.get("stream") else {"choices": [{"text": "".join(self.pieces), "finish_reason": "stop"}]}


fl = T.wrap_llm(FakeLLM(["<think>", "plan", "</think>", "Hello", " you"]), lambda: C)
chunks = list(fl.create_completion("p", max_tokens=50, stream=True))
check("wrapped engine streams only her answer", "".join(c["choices"][0]["text"] for c in chunks) == "Hello you")
check("…and still carries the finish reason", chunks[-1]["choices"][0]["finish_reason"] == "stop")
fl2 = T.wrap_llm(FakeLLM(["x</think>ok"]), lambda: D)
fl2.create_completion("p", max_tokens=50, stream=False)
check("a thinker gets extra room to think, so the answer is not cut off", fl2.seen["max_tokens"] == 50 + T.THINK_EXTRA)
check("wrapping twice is harmless", T.wrap_llm(fl, lambda: C) is fl)

print(f"\n{'ALL PASS' if not _fails else str(len(_fails)) + ' FAILED'}")
sys.exit(1 if _fails else 0)
