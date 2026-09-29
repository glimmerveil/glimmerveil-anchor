#!/usr/bin/env python3
import os, sys, inspect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_spine as S

calls = []
class FakeLLM:
    def create_completion(self, prompt, **kw):
        calls.append(kw)
        def gen():
            yield {"choices": [{"text": "ok"}]}
        return gen()
S._LLM = FakeLLM()
S.get_llm = lambda: S._LLM

fails = []
def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

S.ask_llm(S.render_chat("sys", "read a page"), num_predict=16)
check("ask_llm passes seed=-1 (autonomous life reseeds per call)", calls[-1].get("seed") == -1)

S._ask_blocking("summarize the past as JSON")
check("_ask_blocking (fold) passes seed=-1", calls[-1].get("seed") == -1)
check("fold still uses LOW fold temperature", calls[-1].get("temperature") == S.FOLD_TEMPERATURE)
check("fold still uses LOW fold top_p", calls[-1].get("top_p") == S.FOLD_TOP_P)

check("generate_guarded still seeds -1 (unchanged reference)", "seed=-1" in inspect.getsource(S.generate_guarded))

print()
if fails:
    print(f"RIG RED — {len(fails)} failure(s): " + ", ".join(fails))
    sys.exit(1)
print("RIG GREEN — seed now flows on every autonomous + fold call")
