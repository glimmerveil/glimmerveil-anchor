#!/bin/bash
# Glimmerveil Anchor for Linux: one AppImage, no model inside (bring your own .gguf or use Ollama's).
# Same shape as the Forge's: bundled python-build-standalone + manylinux wheels (CPU and Vulkan engines)
# + voice files + Anchor's source, readable (Apache-2.0).
#
#   ARTIFACTS=<dir> VERSION=<x.y.z> packaging/linux/build_appimage.sh
#
# ARTIFACTS must hold: cpython-3.12.*-linux-x86_64.tar.gz · appimage-runtime-x86_64 · wheel-cpu/ (or
# wheel-cpu-tuned/) · wheel-vulkan/ · voice/{kokoro-v1.0.onnx,voices-v1.0.bin,ggml-base.en.bin}
# MKSQUASHFS may point at a mksquashfs binary; otherwise the host's is used.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ART="${ARTIFACTS:?set ARTIFACTS to the folder holding the build inputs}"
VERSION="${VERSION:?set VERSION, e.g. 1.0.0}"
OUT="$REPO/dist/linux"
APPDIR="$OUT/AppDir"
VEIL="$APPDIR/opt/veil"

PYRT_TAR="$(ls "$ART"/cpython-3.12.*-linux-x86_64.tar.gz | head -1)"
WHEEL_CPU="$(ls "$ART"/wheel-cpu-tuned/llama_cpp_python-*.whl 2>/dev/null | head -1 || true)"
WHEEL_CPU="${WHEEL_CPU:-$(ls "$ART"/wheel-cpu/llama_cpp_python-*.whl | head -1)}"
WHEEL_VULKAN="$(ls "$ART"/wheel-vulkan/llama_cpp_python-*.whl | head -1)"
RUNTIME="$ART/appimage-runtime-x86_64"
for f in "$PYRT_TAR" "$WHEEL_CPU" "$WHEEL_VULKAN" "$RUNTIME" \
         "$ART/voice/kokoro-v1.0.onnx" "$ART/voice/voices-v1.0.bin" "$ART/voice/ggml-base.en.bin"; do
  [ -f "$f" ] || { echo "MISSING INPUT: $f" >&2; exit 1; }
done
MKSQ="${MKSQUASHFS:-$(command -v mksquashfs || true)}"
[ -n "$MKSQ" ] || { echo "no mksquashfs (set MKSQUASHFS)" >&2; exit 1; }

echo "== [1/7] clean AppDir"
rm -rf "$APPDIR"
mkdir -p "$VEIL"/{app,voice,licenses}

echo "== [2/7] bundled python"
tar xzf "$PYRT_TAR" -C "$VEIL"
pip() { "$VEIL/python/bin/python3" -m pip "$@"; }

echo "== [3/7] Anchor's source (readable — Apache-2.0)"
for f in "$REPO"/src/*.py; do
  case "$(basename "$f")" in test_*) ;; *) cp "$f" "$VEIL/app/" ;; esac
done
grep -q '^SAFETY_RAILS = True' "$VEIL/app/veil_spine.py" || { echo "RAILS ARE NOT ON" >&2; exit 1; }
cp -r "$REPO/docs" "$VEIL/app/docs"
cp -r "$REPO/examples" "$VEIL/app/examples"
cp "$REPO/LICENSE" "$VEIL/licenses/"

echo "== [4/7] python deps (manylinux wheels only)"
WHEELHOUSE="$OUT/wheelhouse"
mkdir -p "$WHEELHOUSE"
DEPS=(kokoro-onnx soundfile sounddevice pywhispercpp numpy typing-extensions diskcache jinja2)
pip download -q -d "$WHEELHOUSE" --only-binary=:all: \
    --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --platform none-any \
    --python-version 312 --implementation cp "${DEPS[@]}"
pip install -q --no-index --find-links "$WHEELHOUSE" --target "$VEIL/lib" "${DEPS[@]}"

echo "== [5/7] the two engines (CPU / Vulkan)"
pip install -q --no-deps --target "$VEIL/lib-llama-cpu" "$WHEEL_CPU"
pip install -q --no-deps --target "$VEIL/lib-llama-vulkan" "$WHEEL_VULKAN"

echo "== [6/7] voice, AppRun, desktop, icon"
cp "$ART/voice/kokoro-v1.0.onnx" "$ART/voice/voices-v1.0.bin" "$ART/voice/ggml-base.en.bin" "$VEIL/voice/"
cp "$HERE/AppRun" "$APPDIR/AppRun" && chmod +x "$APPDIR/AppRun"
cp "$HERE/glimmerveil-anchor.desktop" "$APPDIR/"
if [ -f "$HERE/glimmerveil-anchor.png" ]; then
  cp "$HERE/glimmerveil-anchor.png" "$APPDIR/"
else
  "$VEIL/python/bin/python3" - "$APPDIR/glimmerveil-anchor.png" <<'PYEOF'
import struct, sys, zlib
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
w = h = 256
row = b"\x00" + bytes((24, 40, 64, 255)) * w
open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                              + chunk(b"IDAT", zlib.compress(row * h)) + chunk(b"IEND", b""))
PYEOF
fi
find "$APPDIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
for d in tests test; do
  find "$VEIL/lib" "$VEIL/lib-llama-cpu" "$VEIL/lib-llama-vulkan" -type d -name "$d" -exec rm -rf {} + 2>/dev/null || true
done
for bad in "*.gguf" "*.db" "card.json" "*.veil"; do
  hit="$(find "$APPDIR" -name "$bad" | head -1)"
  [ -z "$hit" ] || { echo "REFUSED: the AppImage would carry $hit" >&2; exit 1; }
done

echo "== [7/7] squashfs + type-2 runtime"
OUTFILE="$OUT/GlimmerveilAnchor-$VERSION-x86_64.AppImage"
SQ="$OUT/anchor-$VERSION.squashfs"
rm -f "$SQ" "$OUTFILE"
"$MKSQ" "$APPDIR" "$SQ" -comp zstd -b 128K -root-owned -noappend -mkfs-time 0
cat "$RUNTIME" "$SQ" > "$OUTFILE"
rm -f "$SQ"
chmod +x "$OUTFILE"
sha256sum "$OUTFILE" | tee "$OUTFILE.sha256"
echo "READY: $OUTFILE"
