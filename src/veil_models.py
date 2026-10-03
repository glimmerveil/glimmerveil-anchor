#!/usr/bin/env python3
import json
import os

import veil_paths
import veil_template

CHOICE_FILE = "model_choice.json"
_OLLAMA_MODEL = "application/vnd.ollama.image.model"


def models_dir():
    return os.environ.get("VEIL_MODELS_DIR") or os.path.expanduser(
        os.path.join("~", veil_paths.HOME_DIRNAME, "models"))


def _choice_path():
    return os.path.join(veil_paths.data_dir(), CHOICE_FILE)


def ollama_dirs():
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        return [env]
    dirs = [os.path.expanduser(os.path.join("~", ".ollama", "models"))]
    if not veil_paths.is_windows():
        dirs += ["/usr/share/ollama/.ollama/models", "/var/lib/ollama/.ollama/models"]
    return dirs


def _usable(path):
    meta = veil_template.gguf_meta(path)
    return bool(meta) and veil_template.chat_capable(meta), meta


def local_models(folder=None):
    folder = folder or models_dir()
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for n in names:
        p = os.path.join(folder, n)
        if n.lower().endswith(".gguf") and os.path.isfile(p):
            ok, meta = _usable(p)
            if ok:
                out.append({"label": meta.get("general.name") or n[:-5], "path": p,
                            "size": os.path.getsize(p), "source": "models folder"})
    return out


def ollama_models():
    out, seen = [], set()
    for root in ollama_dirs():
        man_root = os.path.join(root, "manifests")
        if not os.path.isdir(man_root):
            continue
        for d, _, files in os.walk(man_root):
            for tag in sorted(files):
                rel = os.path.relpath(os.path.join(d, tag), man_root).replace(os.sep, "/")
                parts = rel.split("/")
                if len(parts) < 3:
                    continue
                host, name = parts[0], "/".join(parts[1:-1])
                if host == "registry.ollama.ai" and name.startswith("library/"):
                    name = name[len("library/"):]
                elif host != "registry.ollama.ai":
                    name = host + "/" + name
                try:
                    with open(os.path.join(d, tag), encoding="utf-8") as f:
                        layers = json.load(f).get("layers") or []
                except (OSError, ValueError, AttributeError):
                    continue
                digest = next((l.get("digest") for l in layers
                               if isinstance(l, dict) and l.get("mediaType") == _OLLAMA_MODEL), None)
                if not digest or ":" not in digest:
                    continue
                blob = os.path.join(root, "blobs", digest.replace(":", "-"))
                if blob in seen or not os.path.isfile(blob):
                    continue
                ok, _ = _usable(blob)
                if not ok:
                    continue
                seen.add(blob)
                out.append({"label": "%s:%s" % (name, parts[-1]), "path": blob,
                            "size": os.path.getsize(blob), "source": "Ollama"})
    return out


def all_models():
    return local_models() + ollama_models()


def saved_choice():
    try:
        with open(_choice_path(), encoding="utf-8") as f:
            p = json.load(f).get("path") or ""
    except (OSError, ValueError, AttributeError):
        return ""
    return p if os.path.isfile(p) else ""


def save_choice(path):
    os.makedirs(veil_paths.data_dir(), exist_ok=True)
    tmp = _choice_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"path": os.path.abspath(path)}, f)
    os.replace(tmp, _choice_path())


def resolve(default):
    env = os.environ.get("VEIL_MODEL")
    if env:
        return env
    chosen = saved_choice()
    if chosen:
        return chosen
    if os.path.isfile(default):
        return default
    local = local_models()
    if local:
        return local[0]["path"]
    ollama = ollama_models()
    if ollama:
        return ollama[0]["path"]
    return default


def human_size(n):
    return "%.1f GB" % (n / 1e9) if n >= 1e9 else "%d MB" % max(1, n // 1000000)
