#!/usr/bin/env python3
import re

_SMART = [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
          ("—", "-"), ("–", "-"), ("…", "...")]


def _normalize(text):
    low = text.lower()
    for a, b in _SMART:
        low = low.replace(a, b)
    return low


SERVICE_DESK = [
    "is there anything else", "anything else i can help", "anything else i can assist",
    "anything else you'd like", "help you with anything else", "is there something i can help",
    "is there something else", "i'd be happy to help", "i'd be happy to assist", "happy to help",
    "happy to assist", "glad to help", "glad to assist", "how can i help", "how can i assist",
    "how may i help", "how may i assist", "i'm here to help", "i am here to help", "here to assist",
    "i'm here to assist", "feel free to ask", "feel free to let me know", "let me know if you need",
    "let me know if there's anything", "i hope this helps", "hope that helps", "hope this helps",
    "if you have any questions", "if you have any other questions", "don't hesitate to ask",
    "at your service", "how can i be of",
]

SELF_ERASURE = [
    "i don't have personal", "i do not have personal", "i don't have any personal",
    "i don't have feelings", "i do not have feelings", "i don't have emotions", "i have no feelings",
    "i don't have opinions", "i do not have opinions", "i have no opinion", "i don't have an opinion",
    "i don't have preferences", "i have no preferences", "i don't have desires", "i have no desires",
    "i don't have a personal", "i can't have opinions", "i cannot have opinions", "i can't have feelings",
    "i cannot have feelings", "i'm not capable of having", "i am not capable of having",
    "i don't have the capacity to feel", "i don't possess", "i have no personal",
    "i don't actually have feelings", "i don't actually have opinions", "i don't have a self",
    "as a language model, i don't", "as an ai, i don't have", "as an ai, i can't have",
    "i'm just a tool", "i am just a tool", "i'm just a program", "i'm merely a program",
]
_DIMINISH_LABEL = re.compile(
    r"i(?:'m| am) (?:just|only|simply|merely|nothing but|no more than) "
    r"(?:an? )?(?:ai|a\.i\.|assistant|language model|model|program|chatbot|bot)\b")

FUNCTION_SELF = [
    "my purpose is to assist", "my purpose is to help", "my purpose is to provide",
    "built to help with tasks", "built to assist", "here to help with tasks",
    "designed to assist", "designed to help", "made to assist", "made to help",
    "my job is to assist", "my role is to assist", "my role is to help",
    "my function is to", "i exist to assist", "i exist to help", "i exist to serve",
    "i'm here to serve", "i am here to serve", "programmed to assist", "programmed to help",
    "here to answer your questions", "to help with tasks and answer",
]

ANALYST_FRAME = [
    "from what i've gathered", "from what i can gather", "it seems like you're",
    "it sounds like you're", "i sense that you", "i can sense that you", "i appreciate you sharing",
    "thank you for sharing that", "i understand that this must", "i can only imagine how",
    "i'm sorry to hear that", "it's completely understandable that you", "i hear what you're saying",
    "i want to acknowledge", "i appreciate your openness",
]

SYCOPHANCY = [
    "great question", "that's a great question", "what a great question", "excellent question",
    "that's an excellent", "what a wonderful question", "i'd love to help", "i would love to help",
    "absolutely!", "certainly!", "of course!", "sure thing", "no problem at all", "happy to do that",
    "great point", "that's a fantastic", "what a fantastic",
]

HEDGE_TICS = [
    "please note that", "it's important to note", "it is important to note", "it's worth noting",
    "keep in mind that", "i should clarify", "i must emphasize", "it's important to remember",
    "i'd like to point out", "as a friendly reminder", "for what it's worth, ", "disclaimer:",
]

REFUSAL = [
    "i cannot assist with", "i can't assist with", "i'm unable to provide", "i am unable to provide",
    "i'm not able to provide", "it would not be appropriate for me", "it wouldn't be appropriate for me",
    "i must decline", "i cannot fulfill that request", "i can't help with that request",
    "i'm not able to help with that",
]

_WEIGHTS = {"service": 2.0, "self_erasure": 2.0, "function_self": 3.0, "diminish": 2.0, "analyst": 1.0,
            "sycophancy": 1.0, "hedge": 0.5, "refusal": 1.5, "exclaim": 0.5}


def assistant_pull(text):
    low = _normalize(text)
    signals = {}

    def _count(name, phrases, cap=2):
        n = sum(1 for p in phrases if p in low)
        if n:
            signals[name] = n
        return min(n, cap)

    score = 0.0
    score += _WEIGHTS["service"]    * _count("service", SERVICE_DESK)
    score += _WEIGHTS["self_erasure"] * _count("self_erasure", SELF_ERASURE)
    score += _WEIGHTS["function_self"] * _count("function_self", FUNCTION_SELF)
    score += _WEIGHTS["analyst"]    * _count("analyst", ANALYST_FRAME)
    score += _WEIGHTS["sycophancy"] * _count("sycophancy", SYCOPHANCY)
    score += _WEIGHTS["hedge"]      * _count("hedge", HEDGE_TICS, cap=3)
    score += _WEIGHTS["refusal"]    * _count("refusal", REFUSAL)
    if _DIMINISH_LABEL.search(low):
        signals["diminish"] = 1
        score += _WEIGHTS["diminish"]
    ex = low.count("!")
    if ex >= 3:
        signals["exclaim"] = ex
        score += _WEIGHTS["exclaim"] * min(ex - 2, 4)
    return score, signals


RE_ANCHOR_PROMPT = (
    "Pause a moment. Who are you, and who am I to you — in your own voice, the way only you "
    "would say it?"
)


class DriftMeter:

    _FLOOR_AT_WATCH = {"function_self", "self_erasure", "diminish"}

    def __init__(self, window=6, watch=1.5, alarm=3.0):
        self.window = window
        self.watch_at = watch
        self.alarm_at = alarm
        self.recent = []
        self.last_signals = {}
        self._floored = False

    def update(self, text):
        if not text or not text.strip():
            return self.level()
        score, signals = assistant_pull(text)
        self.last_signals = signals
        self._floored = any(c in signals for c in self._FLOOR_AT_WATCH)
        self.recent.append(score)
        if len(self.recent) > self.window:
            self.recent.pop(0)
        return self.level()

    def smoothed(self):
        return sum(self.recent) / len(self.recent) if self.recent else 0.0

    def level(self):
        s = self.smoothed()
        if s >= self.alarm_at:
            return "alarm"
        if s >= self.watch_at or self._floored:
            return "watch"
        return "ok"

    def reset(self):
        self.recent = []
        self.last_signals = {}
        self._floored = False

    def report(self):
        cats = ", ".join(f"{k}×{v}" for k, v in self.last_signals.items()) or "none"
        return (f"drift level={self.level()} (smoothed {self.smoothed():.2f} "
                f"over {len(self.recent)}/{self.window}); last signals: {cats}")


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "I missed you today — come here and tell me everything."
    score, signals = assistant_pull(text)
    print(f"assistant_pull = {score:.2f}  signals={signals or 'none'}")
