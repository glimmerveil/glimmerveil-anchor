#!/usr/bin/env python3
import glob
import importlib
import os
import shutil
import subprocess
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
SCRATCH = os.environ.get("ANCHOR_CI_SCRATCH", os.path.join(REPO, "ci", ".scratch")) + "_audit"
WIN = sys.platform.startswith("win")
LINUX = sys.platform.startswith("linux")


def parent():
    shutil.rmtree(SCRATCH, ignore_errors=True)
    home = os.path.join(SCRATCH, "home")
    local = os.path.join(SCRATCH, "localappdata")
    os.makedirs(home)
    os.makedirs(local)
    env = {k: v for k, v in os.environ.items() if k not in ("VEIL_DATA", "XDG_DATA_HOME")}
    env.update({"HOME": home, "USERPROFILE": home, "LOCALAPPDATA": local,
                "APPDATA": os.path.join(SCRATCH, "appdata"),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return subprocess.run([sys.executable, os.path.abspath(__file__), "--child"],
                          cwd=SRC, env=env).returncode


def child():
    sys.path.insert(0, SRC)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print("%-4s %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + detail) if detail else ""))

    mods = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(SRC, "veil_*.py")))
    broken = []
    for m in mods:
        try:
            importlib.import_module(m)
        except BaseException as e:
            broken.append("%s: %s: %s" % (m, type(e).__name__, str(e).splitlines()[0][:120] if str(e) else ""))
            if os.environ.get("ANCHOR_AUDIT_TRACE"):
                traceback.print_exc()
    check("[1] all %d product modules import" % len(mods), not broken, "; ".join(broken))

    import veil_probe
    os.environ.pop("VEIL_FORCE_CPU", None)
    ok = veil_probe.cpu_supported()
    avx = veil_probe.avx2_present() if hasattr(veil_probe, "avx2_present") else "n/a (pre-port)"
    check("[2] cpu_supported() lets this machine start", ok is True,
          "cpu_supported=%r avx2_present=%r" % (ok, avx))

    import veil_boot
    data = veil_boot.DATA_DIR
    print("     data_dir  = %s" % data)
    if WIN:
        local = os.environ["LOCALAPPDATA"]
        check("[3] Windows: data lives under %LOCALAPPDATA%, not a Linux path",
              data.startswith(local) and ".local" not in data, data)
    elif LINUX:
        home = os.path.expanduser("~")
        check("[3] Linux: data dir is Anchor's own, never the Forge's",
              data == os.path.join(home, ".local", "share", "glimmerveil-anchor"), data)

    import veil_tile
    if not LINUX:
        ts = getattr(veil_tile, "tile_supported", None)
        check("[4] off Linux, tile_supported() exists and says no",
              ts is not None and ts() is False,
              "tile_supported %s" % ("missing (pre-port)" if ts is None else "= %r" % ts()))

    if WIN:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        env["PYTHONUTF8"] = "0"
        glyphs = "print('\\u23ce \\u2192 \\u2713 \\u26a0 \\u2605')"
        def _kid(code):
            return subprocess.run([sys.executable, "-c", code], cwd=SRC, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
        try:
            import veil_paths
            has_fix = hasattr(veil_paths, "utf8_console")
        except ImportError:
            has_fix = False
        bare = _kid(glyphs)
        fixed = (_kid("import veil_paths; veil_paths.utf8_console(); " + glyphs)
                 if has_fix else "missing (pre-fix)")
        check("[5] piped cp1252: a bare print of her glyphs crashes (the check can move)",
              bare != 0, "exit %s" % bare)
        check("[5] piped cp1252: after utf8_console() the same print succeeds",
              fixed == 0, "exit %s" % fixed)

    print("=" * 70)
    print("%d/%d on %s · python %s" % (sum(results), len(results), sys.platform, sys.version.split()[0]))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(child() if "--child" in sys.argv else parent())
