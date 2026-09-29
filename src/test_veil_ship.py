#!/usr/bin/env python3

import http.server
import json
import os
import struct
import sys
import tempfile
import threading

SANDBOX = tempfile.mkdtemp(prefix="veil_ship_rig_")
os.environ["VEIL_DATA"] = os.path.join(SANDBOX, "data")
os.environ["VEIL_PEEPS"] = os.path.join(SANDBOX, "peeps")
os.environ["VEIL_UPDATE_APP_ROOT"] = os.path.join(SANDBOX, "app")
os.environ["VEIL_UPDATE_MODEL_ROOT"] = os.path.join(SANDBOX, "model")
os.environ.pop("VEIL_UPDATE_URL", None)
os.makedirs(os.environ["VEIL_UPDATE_APP_ROOT"], exist_ok=True)
os.makedirs(os.environ["VEIL_UPDATE_MODEL_ROOT"], exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import veil_probe
import veil_tile
import veil_update

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


print("veil_probe:")
check("settings roundtrip", (veil_probe.save_settings({"gpu": True, "gpu_layers": 16}) or
                             veil_probe.load_settings()) == {"gpu": True, "gpu_layers": 16})

veil_probe.save_settings({"gpu": False})
r = veil_probe.resolve_launch()
check("gpu off → cpu, no notice", r == {"use_gpu": False, "layers": 0, "notice": None})

veil_probe.save_settings({"gpu": True, "gpu_layers": 16})
veil_probe.clear_breadcrumb()
r = veil_probe.resolve_launch()
check("gpu on, no crumb → gpu 16", r["use_gpu"] is True and r["layers"] == 16)

veil_probe.drop_breadcrumb()
r = veil_probe.resolve_launch()
check("stale crumb → auto-revert to cpu", r["use_gpu"] is False and r["notice"] is not None)
check("auto-revert PERSISTED (no crash loop)", veil_probe.load_settings().get("gpu") is False)
check("crumb consumed", not veil_probe.breadcrumb_stale())
r2 = veil_probe.resolve_launch()
check("second launch quiet + still cpu", r2["use_gpu"] is False and r2["notice"] is None)

veil_probe.drop_breadcrumb()
veil_probe.mark_llm_alive()
check("mark_llm_alive clears crumb", not veil_probe.breadcrumb_stale())

if sys.platform.startswith("linux"):
    check("cpu_flags reads something on linux", len(veil_probe.cpu_flags()) > 0)
else:
    check("off linux: no cpuinfo, and the CPU guard still lets her start",
          veil_probe.cpu_flags() == set() and veil_probe.cpu_supported() is True)
os.environ["VEIL_FORCE_CPU"] = "1"
check("VEIL_FORCE_CPU hatch", veil_probe.cpu_supported() is True)
os.environ.pop("VEIL_FORCE_CPU")

print("veil_update:")
check("DORMANT by default (the §5 law)", veil_update.enabled() is False)
check("check() while dormant is a quiet None", veil_update.check("1.0") is None)

for bad in ("app/../../etc/cron.d/evil", "model/../peeps/her.db", "peeps/card.json",
            "app/her_memory.db", "app/peeps/x.json", "model/diary.txt", "somewhere/else.py"):
    try:
        veil_update._safe_dest(bad)
        check(f"path wall stops: {bad}", False)
    except ValueError:
        check(f"path wall stops: {bad}", True)

ok_dest = veil_update._safe_dest("app/veil_tick.py")
check("legit code path allowed", ok_dest.startswith(os.environ["VEIL_UPDATE_APP_ROOT"]))
ok_model = veil_update._safe_dest("model/brain-v2.gguf")
check("legit model path allowed (gguf name exempt from marks)",
      ok_model.startswith(os.environ["VEIL_UPDATE_MODEL_ROOT"]))

served = os.path.join(SANDBOX, "served")
os.makedirs(served, exist_ok=True)
open(os.path.join(served, "f.bin"), "wb").write(b"new brain bytes")
import hashlib
GOOD = hashlib.sha256(b"new brain bytes").hexdigest()


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        return os.path.join(served, os.path.basename(path))


srv = http.server.HTTPServer(("127.0.0.1", 0), Quiet)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}/f.bin"

dest = os.path.join(os.environ["VEIL_UPDATE_APP_ROOT"], "pulled.py")
try:
    veil_update._download_verified(URL, "0" * 64, dest)
    check("wrong hash refused", False)
except ValueError:
    check("wrong hash refused", not os.path.exists(dest) and not os.path.exists(dest + ".part"))

veil_update._download_verified(URL, GOOD, dest)
check("right hash lands atomically", open(dest, "rb").read() == b"new brain bytes")

check("no refire before model pull", veil_update.anchor_refire_pending() is False)
veil_update.apply({"version": "9.9", "files": [],
                   "model": {"name": "brain-v2.gguf", "sha256": GOOD, "url": URL}})
check("model pull stamps anchor refire (new brain law)", veil_update.anchor_refire_pending())
veil_update.clear_anchor_refire()
check("refire clearable", not veil_update.anchor_refire_pending())
srv.shutdown()

print("veil_tile:")
entry = veil_tile._make_entry("/tmp/Fake.AppImage")
blob = veil_tile._emit_map({"shortcuts": {"0": entry}})
parsed, _ = veil_tile._parse_map(blob, 0)
check("binary vdf roundtrip", parsed["shortcuts"]["0"]["AppName"] == veil_tile.TILE_NAME
      and parsed["shortcuts"]["0"]["appid"] == entry["appid"]
      and isinstance(parsed["shortcuts"]["0"]["tags"], dict))
check("non-steam appid high bit set", entry["appid"] & 0x80000000)
check("entry wears Steam's own field casing (the Pip-proven shape)",
      "AppName" in entry and "exe" in entry and "sortas" in entry
      and "appname" not in entry and "Exe" not in entry)

vdf = os.path.join(SANDBOX, "shortcuts.vdf")
veil_tile._save(vdf, {"shortcuts": {"0": entry}})
root = veil_tile._load(vdf)
check("vdf file load/save", root["shortcuts"]["0"]["exe"] == entry["exe"])

lsc = veil_tile._launcher_script("/tmp/Fake.AppImage")
check("launcher named the product", os.path.basename(lsc) == veil_tile.TILE_NAME)
check("launcher executable + targets the install",
      os.access(lsc, os.X_OK) and "/tmp/Fake.AppImage" in open(lsc).read())

check("uint32 encoding", struct.unpack("<I", veil_tile._emit_map({"x": 7})[3:7])[0] == 7)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
