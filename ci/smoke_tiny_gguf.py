#!/usr/bin/env python3
import hashlib
import os
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
DIR = os.path.join(REPO, "ci", ".scratch_model")
COMMIT = "499bc8821c6b12b4e53c5bffcb21ec206f212d81"
URL = ("https://huggingface.co/ggml-org/models/resolve/%s/tinyllamas/stories15M-q8_0.gguf" % COMMIT)
SHA256 = "2eda49203f2f044f3dddf29a7dd7cc861ef5a0340f518a19613d73ba6d9c06b6"
SIZE = 26671328
PATH = os.path.join(DIR, "stories15M-q8_0.gguf")


def fetch():
    os.makedirs(DIR, exist_ok=True)
    if not (os.path.isfile(PATH) and os.path.getsize(PATH) == SIZE):
        with urllib.request.urlopen(URL, timeout=120) as r, open(PATH + ".part", "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        os.replace(PATH + ".part", PATH)
    h = hashlib.sha256()
    with open(PATH, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != SHA256:
        print("FAIL toy model sha256 mismatch: %s" % h.hexdigest())
        sys.exit(1)
    print("toy model ok  %s  %d bytes  sha256 %s…" % (os.path.basename(PATH), SIZE, SHA256[:12]))


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    fetch()
    os.environ["VEIL_MODEL"] = PATH
    os.environ["VEIL_GPU_LAYERS"] = "0"
    sys.path.insert(0, SRC)
    import veil_spine as spine
    if os.path.abspath(spine.MODEL_PATH) != os.path.abspath(PATH):
        print("FAIL VEIL_MODEL did not reach the spine: MODEL_PATH=%s" % spine.MODEL_PATH)
        return 1
    import llama_cpp
    t = time.time()
    llm = spine.get_llm()
    print("loaded through veil_spine.get_llm()  llama_cpp %s  %.1fs"
          % (getattr(llama_cpp, "__version__", "?"), time.time() - t))
    t = time.time()
    out = llm.create_completion("Once upon a time", max_tokens=12, temperature=0.0)
    text = out["choices"][0]["text"]
    n = out.get("usage", {}).get("completion_tokens", 0)
    print("generated %d token(s) in %.1fs: %r" % (n, time.time() - t, text))
    if n < 1 or not text.strip():
        print("FAIL the engine loaded but generated nothing")
        return 1
    print("PASS the engine loads and speaks through her loader on %s" % sys.platform)
    return 0


if __name__ == "__main__":
    sys.exit(main())
