#!/usr/bin/env python3
import os
import re
import struct

_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
_STR_KEYS = ("general.architecture", "general.name", "general.type", "tokenizer.chat_template")
_ID_KEYS = ("tokenizer.ggml.bos_token_id", "tokenizer.ggml.eos_token_id")
_SHAPE_KEYS = (".block_count", ".embedding_length")
_MAX_STR = 1 << 24
THINK_EXTRA = 768


def _read_str(f):
    (n,) = struct.unpack("<Q", f.read(8))
    if n > _MAX_STR:
        raise ValueError("gguf string too long")
    b = f.read(n)
    if len(b) != n:
        raise ValueError("gguf truncated")
    return b.decode("utf-8", "replace")


def _skip_value(f, t):
    if t in _SCALAR:
        f.seek(struct.calcsize(_SCALAR[t]), 1)
    elif t == 8:
        (n,) = struct.unpack("<Q", f.read(8))
        f.seek(n, 1)
    elif t == 9:
        et, n = struct.unpack("<IQ", f.read(12))
        if et in _SCALAR:
            f.seek(struct.calcsize(_SCALAR[et]) * n, 1)
        else:
            for _ in range(n):
                _skip_value(f, et)
    else:
        raise ValueError("unknown gguf type %d" % t)


def gguf_meta(path, tokens=False):
    out = {}
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"GGUF":
                return out
            (version,) = struct.unpack("<I", f.read(4))
            if version < 2:
                return out
            _, n_kv = struct.unpack("<QQ", f.read(16))
            if n_kv > 100000:
                return out
            for _ in range(n_kv):
                key = _read_str(f)
                (t,) = struct.unpack("<I", f.read(4))
                if key in _STR_KEYS and t == 8:
                    out[key] = _read_str(f)
                elif key.endswith(_SHAPE_KEYS) and t in (4, 5, 10, 11):
                    (out[key],) = struct.unpack(_SCALAR[t], f.read(struct.calcsize(_SCALAR[t])))
                elif key in _ID_KEYS and t in (4, 5, 10, 11):
                    (out[key],) = struct.unpack(_SCALAR[t], f.read(struct.calcsize(_SCALAR[t])))
                elif tokens and key == "tokenizer.ggml.tokens" and t == 9:
                    et, n = struct.unpack("<IQ", f.read(12))
                    if et != 8 or n > 4000000:
                        raise ValueError("odd token table")
                    out[key] = [_read_str(f) for _ in range(n)]
                else:
                    _skip_value(f, t)
    except (OSError, ValueError, OverflowError, MemoryError, struct.error):
        pass
    return out


def _token(meta, id_key):
    toks = meta.get("tokenizer.ggml.tokens") or []
    i = meta.get(id_key)
    return toks[i] if isinstance(i, int) and 0 <= i < len(toks) else ""


_NOT_CHAT_ARCHS = ("clip", "whisper", "parakeet", "nemo", "wav2vec", "encodec", "t5encoder", "bert", "nomic-bert")


def chat_capable(meta):
    arch = (meta.get("general.architecture") or "").lower()
    if (meta.get("general.type") or "").lower() == "mmproj" or arch in _NOT_CHAT_ARCHS:
        return False
    return bool(meta)


class Family:
    thinks = False
    nothink = ""

    def __init__(self, key, label, stops, system_role=True):
        self.key, self.label, self.stops = key, label, stops
        self.system_role = system_role

    def _fold_system(self, system, turns):
        if self.system_role or not system:
            return system, list(turns)
        turns = list(turns)
        for i, t in enumerate(turns):
            if t.get("role", "user") == "user":
                turns[i] = dict(t, content=system + "\n\n" + (t.get("content") or "").strip())
                return "", turns
        return "", [{"role": "user", "content": system}] + turns

    def render_chat(self, system, user):
        if self.key in ("chatml", "qwen3"):
            s = ""
            if system:
                s += "<|im_start|>system\n" + system + "<|im_end|>\n"
            return s + "<|im_start|>user\n" + user + "<|im_end|>\n<|im_start|>assistant\n" + self.nothink
        return self.render_chat_turns(system, [{"role": "user", "content": user}])

    def render_chat_turns(self, system, turns, prefill=""):
        system, turns = self._fold_system(system, turns)
        k = "chatml" if self.key == "qwen3" else self.key
        s = ""
        if k == "chatml":
            s = "<|im_start|>system\n" + (system or "") + "<|im_end|>\n"
        elif k == "llama3" and system:
            s = "<|start_header_id|>system<|end_header_id|>\n\n" + system + "<|eot_id|>"
        elif k == "phi3" and system:
            s = "<|system|>\n" + system + "<|end|>\n"
        elif k == "deepseek" and system:
            s = system
        for t in turns:
            role = t.get("role", "user")
            if role not in ("user", "assistant") and k != "chatml":
                role = "user"
            c = (t.get("content") or "").strip()
            if k == "chatml":
                s += "<|im_start|>" + role + "\n" + c + "<|im_end|>\n"
            elif k == "llama3":
                s += "<|start_header_id|>" + role + "<|end_header_id|>\n\n" + c + "<|eot_id|>"
            elif k == "gemma":
                s += "<start_of_turn>" + ("model" if role == "assistant" else "user") + "\n" + c + "<end_of_turn>\n"
            elif k == "mistral":
                s += ("[INST] " + c + " [/INST]") if role == "user" else (" " + c + "</s>")
            elif k == "phi3":
                s += "<|" + role + "|>\n" + c + "<|end|>\n"
            elif k == "deepseek":
                s += ("<｜User｜>" + c) if role == "user" else ("<｜Assistant｜>" + c + "<｜end▁of▁sentence｜>")
        if k == "chatml":
            s += "<|im_start|>assistant\n" + self.nothink
        elif k == "llama3":
            s += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        elif k == "gemma":
            s += "<start_of_turn>model\n"
        elif k == "mistral":
            s += " " if prefill else ""
        elif k == "phi3":
            s += "<|assistant|>\n"
        elif k == "deepseek":
            s += "<｜Assistant｜>"
        return s + prefill


class _Qwen3(Family):
    nothink = "<think>\n\n</think>\n\n"


class _DeepSeek(Family):
    thinks = True


_END_MARKS = re.compile(r"<\|(?:eot|eom|end|im_end|eot_id|end_of_turn|endoftext)\|>|<end_of_turn>|</s>")


class JinjaFamily(Family):
    def __init__(self, template, bos, eos, name=""):
        from jinja2.sandbox import ImmutableSandboxedEnvironment

        def _raise(msg):
            raise ValueError(msg)

        env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
        env.globals["raise_exception"] = _raise
        env.globals["strftime_now"] = lambda fmt: __import__("time").strftime(fmt)
        self._tpl = env.from_string(template)
        self.bos, self.eos = bos or "", eos or ""
        stops = sorted(set(([self.eos] if self.eos else []) + _END_MARKS.findall(template)))
        super().__init__("jinja", "the model's own template" + (" (%s)" % name if name else ""), stops)
        self.thinks = "<think>" in template and "enable_thinking" not in template

    def _render(self, msgs):
        out = self._tpl.render(messages=msgs, add_generation_prompt=True, bos_token=self.bos,
                               eos_token=self.eos, enable_thinking=False)
        if self.bos and out.startswith(self.bos):
            out = out[len(self.bos):]
        return out

    def render_chat(self, system, user):
        return self.render_chat_turns(system, [{"role": "user", "content": user}])

    def render_chat_turns(self, system, turns, prefill=""):
        msgs = [{"role": t.get("role", "user") if t.get("role") in ("user", "assistant") else "user",
                 "content": (t.get("content") or "").strip()} for t in turns]
        tries = [([{"role": "system", "content": system}] if system else []) + msgs]
        merged = []
        for m in msgs:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1] = dict(merged[-1], content=merged[-1]["content"] + "\n\n" + m["content"])
            else:
                merged.append(dict(m))
        tries.append(([{"role": "system", "content": system}] if system else []) + merged)
        if system and merged and merged[0]["role"] == "user":
            tries.append([dict(merged[0], content=system + "\n\n" + merged[0]["content"])] + merged[1:])
        for msgs_try in tries:
            try:
                return self._render(msgs_try) + prefill
            except Exception:
                continue
        return FAMILIES["chatml"].render_chat_turns(system, turns, prefill)


FAMILIES = {
    "chatml": Family("chatml", "ChatML (Qwen and friends)", ["<|im_end|>", "<|endoftext|>"]),
    "qwen3": _Qwen3("qwen3", "ChatML, thinking off (Qwen3)", ["<|im_end|>", "<|endoftext|>"]),
    "llama3": Family("llama3", "Llama 3", ["<|eot_id|>", "<|end_of_text|>", "<|start_header_id|>"]),
    "gemma": Family("gemma", "Gemma", ["<end_of_turn>", "<start_of_turn>"], system_role=False),
    "mistral": Family("mistral", "Mistral [INST]", ["</s>", "[INST]"], system_role=False),
    "phi3": Family("phi3", "Phi-3", ["<|end|>", "<|endoftext|>", "<|user|>"]),
    "deepseek": _DeepSeek("deepseek", "DeepSeek (thinks first; only the answer is shown)",
                          ["<｜end▁of▁sentence｜>", "<｜User｜>"]),
}


# She keeps her newest reply as ONE assistant turn unless her brain answers the newest note on its own.
# Measured 10-03 on a stranger's first night: Qwen2.5 · Qwen3 · Gemma · Mistral re-answered every earlier question
# from a prompt of his turns alone (and invented origins); Llama 3 answered the one asked. Coder brains stay off:
# one kept reply gave Qwen2.5-Coder a verbatim echo AND a parrot (07-28).
NEWEST_NOTE_FAMILIES = ("llama3",)
SMALL_BRAIN = 2.5e9


def core_params(meta):
    arch = meta.get("general.architecture") or ""
    layers, width = meta.get(arch + ".block_count"), meta.get(arch + ".embedding_length")
    if not layers or not width:
        return None
    return 12 * layers * width * width


def fit_notes(fam, meta):
    notes = []
    if fam.thinks:
        notes.append("This is a reasoning model: it thinks well, but it may not hold her as a character. "
                     "A chat (instruct) model is a better home for her.")
    est = core_params(meta)
    if est and est < SMALL_BRAIN:
        notes.append("This is a very small model (under 3B): she may narrate both sides of a scene "
                     "instead of keeping to hers. A 3B or larger model holds her far better.")
    return notes


def keeps_last_for(path):
    fam = family_for(path)[0]
    if fam.key in NEWEST_NOTE_FAMILIES:
        return False
    names = [os.path.basename(str(path or ""))]
    try:
        names.append(gguf_meta(path).get("general.name") or "")
    except Exception:
        pass
    return not any("coder" in n.lower() for n in names)


def detect(meta):
    tpl = meta.get("tokenizer.chat_template") or ""
    if "<|im_start|>" in tpl:
        return ("qwen3" if "enable_thinking" in tpl else "chatml"), True
    if "<|start_header_id|>" in tpl:
        return "llama3", True
    if "<start_of_turn>" in tpl:
        return "gemma", True
    if "<｜User｜>" in tpl and "<｜Assistant｜>" in tpl:
        return "deepseek", True
    if "[INST]" in tpl:
        return "mistral", True
    if "<|user|>" in tpl and "<|end|>" in tpl:
        return "phi3", True
    if tpl:
        return "jinja", True
    arch = (meta.get("general.architecture") or "").lower()
    if arch.startswith("qwen"):
        return "chatml", True
    if arch.startswith("gemma"):
        return "gemma", True
    if arch.startswith("phi3"):
        return "phi3", True
    return "chatml", False


_CACHE = {}


def family_for(path):
    forced = os.environ.get("VEIL_CHAT_FORMAT", "").strip().lower()
    if forced in FAMILIES:
        return FAMILIES[forced], True, True
    try:
        key = (os.path.abspath(path), os.path.getmtime(path), os.path.getsize(path))
    except (OSError, TypeError):
        return FAMILIES["chatml"], False, True
    if key not in _CACHE:
        meta = gguf_meta(path)
        fam, sure = detect(meta)
        if fam == "jinja":
            try:
                meta = gguf_meta(path, tokens=True)
                fam_obj = JinjaFamily(meta["tokenizer.chat_template"], _token(meta, _ID_KEYS[0]),
                                      _token(meta, _ID_KEYS[1]), meta.get("general.name", ""))
            except Exception:
                fam_obj, sure = FAMILIES["chatml"], False
        else:
            fam_obj = FAMILIES[fam]
        _CACHE[key] = (fam_obj, sure, chat_capable(meta) or not meta)
    return _CACHE[key]


class ThinkFilter:
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self, expect=False):
        self.buf, self.state = "", ("hold" if expect else "probe")

    def feed(self, piece):
        if self.state == "pass":
            return piece
        if self.state == "trim":
            piece = piece.lstrip()
            if piece:
                self.state = "pass"
            return piece
        self.buf += piece
        if self.state == "probe":
            head = self.buf.lstrip()
            if head.startswith(self.OPEN):
                self.state = "hold"
            elif len(head) >= len(self.OPEN) or not self.OPEN.startswith(head):
                self.state, out, self.buf = "pass", self.buf, ""
                return out
            else:
                return ""
        if self.CLOSE in self.buf:
            out = self.buf.split(self.CLOSE, 1)[1].lstrip()
            self.state, self.buf = ("pass" if out else "trim"), ""
            return out
        return ""

    def flush(self):
        out = self.buf if self.state == "probe" else ""
        self.buf = ""
        return out


def _filtered_stream(stream, flt):
    last = None
    for chunk in stream:
        last = chunk
        ch = chunk["choices"][0]
        text = flt.feed(ch.get("text") or "")
        yield dict(chunk, choices=[dict(ch, text=text)] + chunk["choices"][1:])
    rest = flt.flush()
    if rest and last is not None:
        ch = last["choices"][0]
        yield dict(last, choices=[dict(ch, text=rest)] + last["choices"][1:])


def wrap_llm(llm, family):
    if getattr(llm, "_veil_think_wrapped", False):
        return llm
    orig = llm.create_completion

    def create_completion(prompt, *a, **k):
        fam = family()
        if fam.thinks and k.get("max_tokens"):
            k["max_tokens"] = k["max_tokens"] + THINK_EXTRA
        res = orig(prompt, *a, **k)
        flt = ThinkFilter(expect=fam.thinks)
        if k.get("stream"):
            return _filtered_stream(res, flt)
        ch = res["choices"][0]
        text = flt.feed(ch.get("text") or "") + flt.flush()
        return dict(res, choices=[dict(ch, text=text)] + res["choices"][1:])

    try:
        llm.create_completion = create_completion
        llm._veil_think_wrapped = True
    except Exception:
        pass
    return llm


def install(spine, say=print):
    told = set()

    def family():
        return family_for(spine.MODEL_PATH)[0]

    def current():
        fam, sure, capable = family_for(spine.MODEL_PATH)
        spine.LLAMA_STOPS = list(fam.stops)
        if spine.MODEL_PATH not in told:
            told.add(spine.MODEL_PATH)
            if not capable:
                say("[this file is not a chat model (a vision adapter, speech or embedding model?). "
                    "Point Anchor at an instruct .gguf instead.]")
            elif sure:
                say("[brain format: %s]" % fam.label)
            if capable:
                for note in fit_notes(fam, gguf_meta(spine.MODEL_PATH)):
                    say("[%s]" % note)
            else:
                say("[brain format: unknown, using ChatML. If replies look broken, set "
                    "VEIL_CHAT_FORMAT to one of: %s]" % ", ".join(FAMILIES))
        return fam

    spine.FAMILY_KEEPS_LAST = lambda: keeps_last_for(spine.MODEL_PATH)
    spine.render_chat = lambda system, user: current().render_chat(system, user)
    spine.render_chat_turns = lambda system, turns, prefill="": current().render_chat_turns(system, turns, prefill)
    orig_get = spine.get_llm

    def get_llm(*a, **k):
        return wrap_llm(orig_get(*a, **k), family)

    spine.get_llm = get_llm
    return current
