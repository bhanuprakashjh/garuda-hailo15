#!/usr/bin/env bash
# Native tests and exact-SDK ARM build. No board changes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SDK="${GARUDA_H15L_SDK:-/media/bhanu1234/Development/hailo15/sdk}"
OUT="${GARUDA_FRESH_BUILD:-/tmp/garuda-fresh}"
MOTION="${GARUDA_FRESH_OPENCV_MOTION:-OFF}"
VISUAL="${GARUDA_FRESH_VISUAL_TARGET:-OFF}"
case "$VISUAL" in ON|OFF) ;; *) echo "GARUDA_FRESH_VISUAL_TARGET must be ON or OFF" >&2; exit 1 ;; esac
case "$MOTION" in ON|OFF) ;; *) echo "GARUDA_FRESH_OPENCV_MOTION must be ON or OFF" >&2; exit 1 ;; esac
cmake -S "$ROOT/services/garuda-tracking" -B "$OUT/native" -DCMAKE_BUILD_TYPE=Release -DGARUDA_TRACKING_OPENCV="$MOTION" -DGARUDA_TRACKING_VISUAL_TARGET="$VISUAL"
cmake --build "$OUT/native" -j2
ctest --test-dir "$OUT/native" --output-on-failure
GARUDA_REPLAY_BIN="$OUT/native/garuda-track-replay" python3 -m unittest discover -s "$ROOT/services/garuda-tracking/tests" -p 'test_*.py' -v
GARUDA_REPLAY_BIN="$OUT/native/garuda-track-replay" python3 -m unittest discover -s "$ROOT/services/garuda-follow/tests" -p 'test_*.py' -v
python3 -m unittest discover -s "$ROOT/services/garuda-bridge/tests" -p 'test_sim_offboard_bridge.py' -v
set +u
source "$SDK/environment-setup-armv8a-poky-linux"
set -u
cmake -S "$ROOT/services/garuda-perception" -B "$OUT/h15l" -DCMAKE_BUILD_TYPE=Release \
  -DGARUDA_BUILD_NODE=ON -DGARUDA_BUILD_TESTS=OFF -DGARUDA_BUILD_FRESH_TRACKING=ON \
  -DGARUDA_TRACKING_OPENCV="$MOTION" \
  -DGARUDA_TRACKING_VISUAL_TARGET="$VISUAL" \
  -DCMAKE_TOOLCHAIN_FILE="$OECORE_NATIVE_SYSROOT/usr/share/cmake/OEToolchainConfig.cmake"
cmake --build "$OUT/h15l" --target garuda-fresh-tracking garuda-track-replay garuda-model-probe garuda-embedding-probe garuda-crop-probe garuda-region-probe garuda-causal-replay -j2
if [ "$MOTION" = ON ]; then cmake --build "$OUT/h15l" --target garuda-motion-probe -j2; fi
echo "Built $OUT/h15l/garuda-fresh-tracking"
