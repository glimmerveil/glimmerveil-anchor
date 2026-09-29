#!/usr/bin/env python3
import ast
import glob
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
enc = sys.stdout.encoding or "ascii"
print("stdout encoding (no UTF-8 mode): %s | utf8_mode=%s | %s"
      % (enc, sys.flags.utf8_mode, sys.platform))

bad = {}
reconfig = []
for path in sorted(glob.glob(os.path.join(REPO, "src", "veil_*.py"))):
    name = os.path.basename(path)
    src = open(path, encoding="utf-8").read()
    if "reconfigure(" in src:
        reconfig.append(name)
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print"):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                for ch in set(sub.value):
                    try:
                        ch.encode(enc)
                    except UnicodeEncodeError:
                        bad.setdefault(ch, []).append((name, node.lineno))

print("modules that call stdout.reconfigure(): %s" % (", ".join(reconfig) or "none"))
if not bad:
    print("every literal in every print() encodes in %s" % enc)
else:
    sites = sum(len(v) for v in bad.values())
    print("%d character(s) across %d print site(s) cannot be written in %s:" % (len(bad), sites, enc))
    for ch, where in sorted(bad.items(), key=lambda kv: -len(kv[1])):
        print("  U+%04X %s  %3d site(s)  e.g. %s:%d" % (ord(ch), ascii(ch), len(where), *where[0]))
sys.exit(0)
