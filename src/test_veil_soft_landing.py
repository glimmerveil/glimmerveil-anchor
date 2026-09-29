#!/usr/bin/env python3
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as s


class FakeLLM:

    def __init__(self, text, finish="stop"):
        self.text = text
        self.finish = finish

    def create_completion(self, prompt, **kw):
        for word in self.text.split(" "):
            yield {"choices": [{"text": word + " ", "finish_reason": None}]}
        yield {"choices": [{"text": "", "finish_reason": self.finish}]}


class FakeVoice:

    def __init__(self):
        self.finished_with = None

    def reset(self):
        pass

    def feed(self, text):
        pass

    def finish(self, text):
        self.finished_with = text


def _run(text, finish, voice=None):
    s._LLM = FakeLLM(text, finish=finish)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        reply = s.generate_guarded(None, -1, "prompt", 64, "Wren",
                                   recent_replies=[], voice=voice)
    return reply, out.getvalue()


def run():
    fails = 0
    whole = "I missed you all day. Come sit with me a while."
    cut = whole + " And when the moon fi"

    def check(label, ok):
        nonlocal fails
        print(("  PASS  " if ok else "  FAIL  ") + label)
        if not ok:
            fails += 1

    reply, screen = _run(cut, "length")
    check("cap-hit return = whole sentence", reply == whole)
    check("cap-hit screen: tail erased (ANSI wipe fired)", "\033[2K" in screen)
    check("cap-hit screen: whole sentence reprinted", whole in screen)
    check("cap-hit screen: fragment gone from final line",
          "moon fi" not in screen.split("\033[2K")[-1])

    reply, screen = _run(whole, "stop")
    check("natural stop untouched", reply == whole)
    check("natural stop: no erase fired", "\033[2K" not in screen)

    enderless = "and she kept walking through the long grass toward the"
    reply, _ = _run(enderless, "length")
    check("enderless cap-hit kept whole", reply == enderless.strip())

    v = FakeVoice()
    reply, _ = _run(cut, "length", voice=v)
    check("voice finish() got the trimmed text", v.finished_with == whole)
    check("voice never saw the fragment", "moon fi" not in (v.finished_with or ""))

    v = FakeVoice()
    reply, _ = _run(whole, "stop", voice=v)
    check("voice finish() untouched on natural stop",
          (v.finished_with or "").strip() == whole)

    print(f"\n{'ALL GREEN' if fails == 0 else str(fails) + ' FAILURES'}")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
