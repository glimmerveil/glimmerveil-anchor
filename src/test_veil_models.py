#!/usr/bin/env python3
import builtins
import contextlib
import io
import json
import os
import struct
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="veil_models_rig_")
os.environ["VEIL_DATA"] = os.path.join(_TMP, "data")
os.environ["VEIL_PEEPS"] = os.path.join(_TMP, "peeps")
os.environ["VEIL_MODELS_DIR"] = os.path.join(_TMP, "models")
os.environ["OLLAMA_MODELS"] = os.path.join(_TMP, "ollama")
os.environ.pop("VEIL_MODEL", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_models as M
import veil_paths

_fails = []
def check(name, cond, got=None):
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond or got is None else "   got: %r" % (got,)))
    if not cond:
        _fails.append(name)


def gguf(path, arch, name="", gtype=None, tpl=None):
    def s(x):
        b = x.encode("utf-8")
        return struct.pack("<Q", len(b)) + b
    kv = [("general.architecture", arch)] + ([("general.name", name)] if name else []) \
        + ([("general.type", gtype)] if gtype else []) + ([("tokenizer.chat_template", tpl)] if tpl else [])
    out = b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv))
    for k, v in kv:
        out += s(k) + struct.pack("<I", 8) + s(v)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out + b"\0" * 64)
    return path


def ollama(name, tag, arch, host="registry.ollama.ai", ns="library", gtype=None, with_blob=True):
    root = os.environ["OLLAMA_MODELS"]
    digest = "sha256:" + ("%064x" % abs(hash((name, tag))))
    blob = os.path.join(root, "blobs", digest.replace(":", "-"))
    if with_blob:
        gguf(blob, arch, name=name, gtype=gtype)
    man = os.path.join(root, "manifests", host, ns, name, tag) if ns else os.path.join(root, "manifests", host, name, tag)
    os.makedirs(os.path.dirname(man), exist_ok=True)
    with open(man, "w") as f:
        json.dump({"layers": [{"mediaType": "application/vnd.ollama.image.license", "digest": "sha256:" + "0" * 64},
                              {"mediaType": "application/vnd.ollama.image.model", "digest": digest}]}, f)
    return blob


check("nothing anywhere: resolve falls back to the default path", M.resolve("/nope/default.gguf") == "/nope/default.gguf")

local = gguf(os.path.join(os.environ["VEIL_MODELS_DIR"], "my-qwen.gguf"), "qwen2", name="My Qwen 7B")
gguf(os.path.join(os.environ["VEIL_MODELS_DIR"], "mmproj-my-qwen.gguf"), "clip", gtype="mmproj")
with open(os.path.join(os.environ["VEIL_MODELS_DIR"], "notes.txt"), "w") as f:
    f.write("not a model")
lm = M.local_models()
check("the models folder lists the chat model and skips the vision adapter and other files",
      [m["label"] for m in lm] == ["My Qwen 7B"], [m["label"] for m in lm])

b_llama = ollama("llama3.1", "8b", "llama")
b_hf = ollama("bartowski/Some-GGUF", "Q4_K_M", "gemma3", host="hf.co", ns=None)
ollama("llava", "7b-proj", "clip", gtype="mmproj")
ollama("ghost", "latest", "llama", with_blob=False)
with open(os.path.join(os.environ["OLLAMA_MODELS"], "manifests", "registry.ollama.ai", "library", "llama3.1", "broken"), "w") as f:
    f.write("{not json")
om = M.ollama_models()
labels = sorted(m["label"] for m in om)
check("Ollama: pulled models are found by name:tag, straight to their GGUF blob",
      labels == ["hf.co/bartowski/Some-GGUF:Q4_K_M", "llama3.1:8b"], labels)
check("…the blob path is the real file Ollama keeps", any(m["path"] == b_llama for m in om))
check("…a vision adapter, a manifest with no blob, and a broken manifest are all skipped", len(om) == 2)
check("Ollama entries are marked as such", all(m["source"] == "Ollama" for m in om))

check("no choice saved: resolve takes the models folder first", M.resolve("/nope/default.gguf") == local)
M.save_choice(b_llama)
check("a saved choice wins over the models folder", M.resolve("/nope/default.gguf") == b_llama)
check("veil_paths.model_path() follows the saved choice", veil_paths.model_path() == b_llama)
os.environ["VEIL_MODEL"] = local
check("an explicit VEIL_MODEL still wins over everything", M.resolve("/nope/default.gguf") == local)
os.environ.pop("VEIL_MODEL")
os.remove(b_llama)
check("a saved choice whose file is gone is ignored, never a crash", M.resolve("/nope/default.gguf") == local)

import veil_game
answers = iter(["2"])
real_input = builtins.input
builtins.input = lambda *a, **k: next(answers, "")
veil_game.time.sleep = lambda *a, **k: None
out = io.StringIO()
with contextlib.redirect_stdout(out):
    veil_game._pick_model()
builtins.input = real_input
check("the [m] picker lists the folder model and the Ollama model, and saves the pick",
      M.saved_choice() == b_hf and "hf.co/bartowski/Some-GGUF:Q4_K_M" in out.getvalue(), out.getvalue()[-300:])
check("…and names the brain's format", "Gemma" in out.getvalue())
answers = iter(['"%s"' % local])
builtins.input = lambda *a, **k: next(answers, "")
with contextlib.redirect_stdout(io.StringIO()):
    veil_game._pick_model()
builtins.input = real_input
check("a dragged-in quoted path works too", M.saved_choice() == os.path.abspath(local))
answers = iter([os.path.join(os.environ["VEIL_MODELS_DIR"], "mmproj-my-qwen.gguf")])
builtins.input = lambda *a, **k: next(answers, "")
with contextlib.redirect_stdout(io.StringIO()):
    veil_game._pick_model()
builtins.input = real_input
check("picking a vision adapter by path is refused; the old choice stays", M.saved_choice() == os.path.abspath(local))

print(f"\n{'ALL PASS' if not _fails else str(len(_fails)) + ' FAILED'}")
sys.exit(1 if _fails else 0)
