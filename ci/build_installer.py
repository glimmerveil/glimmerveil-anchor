#!/usr/bin/env python3
# AnchorSetup.exe from the folder the zip is built from: run ci/package_windows.py [--voice] first.
# Signs the installer and its uninstaller only when ANCHOR_SIGN_COMMAND is set (an Inno sign-tool
# command line, $f = the file); without it this is an unsigned build and says so.
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, "dist")
SOURCE = os.path.join(DIST, "GlimmerveilAnchor")
ISS = os.path.join(REPO, "packaging", "windows", "anchor.iss")
VOICE = "--voice" in sys.argv
SETUP = os.path.join(DIST, "AnchorSetup%s.exe" % ("-voice" if VOICE else ""))


def iscc():
    for p in (shutil.which("iscc"),
              os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
              os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")):
        if p and os.path.isfile(p):
            return p
    raise SystemExit("FAIL no ISCC.exe — install Inno Setup 6")


def version():
    ref = os.environ.get("GITHUB_REF_NAME", "")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and ref.startswith("v"):
        v = ref[1:]
        nums = (v.split("-")[0].split(".") + ["0"] * 4)[:4]
        if all(n.isdigit() for n in nums):
            return v, ".".join(nums)
    sha = os.environ.get("GITHUB_SHA", "")[:7] or "local"
    return "0.0.0-dev+" + sha, "0.0.0.0"


def main():
    if not os.path.isfile(os.path.join(SOURCE, "Anchor.bat")):
        raise SystemExit("FAIL no %s — run ci/package_windows.py%s first" % (SOURCE, " --voice" if VOICE else ""))
    if VOICE != os.path.isfile(os.path.join(SOURCE, "voice", "kokoro-v1.0.onnx")):
        raise SystemExit("FAIL %s is not the %s build" % (SOURCE, "voice" if VOICE else "plain"))
    v, num = version()
    argv = [iscc(), "/Q", "/O" + DIST, "/DSourceDir=" + SOURCE, "/DAppVersion=" + v, "/DNumVersion=" + num]
    if VOICE:
        argv.append("/DVoice")
    sign = os.environ.get("ANCHOR_SIGN_COMMAND", "").strip()
    if sign:
        argv += ["/DSIGN", "/Sanchorsign=" + sign]
    argv.append(ISS)
    if os.path.exists(SETUP):
        os.remove(SETUP)
    print("installer %s  version %s  %s" % (os.path.basename(SETUP), v, "SIGNED" if sign else "unsigned (no ANCHOR_SIGN_COMMAND)"))
    subprocess.check_call(argv)
    if not os.path.isfile(SETUP):
        raise SystemExit("FAIL iscc made no %s" % SETUP)
    if sign:
        st = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "(Get-AuthenticodeSignature -LiteralPath '%s').Status" % SETUP],
                            capture_output=True, text=True).stdout.strip()
        print("signature status: %s" % st)
        if st != "Valid":
            raise SystemExit("FAIL signing was asked for and the installer's signature is %r" % st)
    print("installer %s  %.1f MB" % (os.path.basename(SETUP), os.path.getsize(SETUP) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
