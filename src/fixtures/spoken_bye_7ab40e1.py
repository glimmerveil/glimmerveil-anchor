import re


def _spoken_bye(cmd):
    words = re.findall(r"[a-z]+", cmd)
    core = {"bye", "goodbye", "byebye", "buhbye"}
    filler = {"good", "buh"}
    return any(w in core for w in words) and set(words) <= (core | filler)
