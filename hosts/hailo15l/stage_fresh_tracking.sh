#!/usr/bin/env bash
# Stage alongside the current installation. Does not stop/start services.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${GARUDA_H15L_HOST:-root@10.0.0.1}"
BUILD="${GARUDA_FRESH_BUILD:-/tmp/garuda-fresh}/h15l"
SDK="${GARUDA_H15L_SDK:-/media/bhanu1234/Development/hailo15/sdk}"
MODEL="${GARUDA_FRESH_HEF:-/media/bhanu1234/Development/hailo15/models/yolov11s_hailo15l_v5.3.0.controlled.hef}"
PHONE_MODEL="/media/bhanu1234/Development/hailo15/models/yolov8m_hailo15l_v5.3.0.hef"
PHONE_SHA=fe7a956375a1667e3d2fac58f546814453018ae4d9ad5fe33560f11d2117c947
REID_MODEL="${GARUDA_FRESH_REID_HEF:-}" # optional bench model, never downloaded implicitly
REID_SHA=49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7
ROI_MODEL="${GARUDA_FRESH_ROI_HEF:-}" # optional existing model; no implicit download
ROI_SHA=65d875e84dc4ad7c18789724c6cbef534c3cf712c7d578a624e2a71d2587ec20
if [ -n "$ROI_MODEL" ]; then
  ROI_ACTUAL="$(sha256sum "$ROI_MODEL")"
  [ "${ROI_ACTUAL%% *}" = "$ROI_SHA" ] || { echo "unexpected ROI HEF checksum" >&2; exit 1; }
fi
# Optional aerial detector for perception-aerial.json (a VisDrone fine-tune of the same YOLO11s
# recipe). A candidate, so its hash is never defaulted: both the path and the recorded hash must
# be given, and the hash is written next to the file on the board for start-aerial to check.
AERIAL_MODEL="${GARUDA_FRESH_AERIAL_HEF:-}"
AERIAL_SHA="${GARUDA_FRESH_AERIAL_HEF_SHA:-}"
AERIAL_DEST=/opt/garuda-fresh/models/yolov11s_aerial_hailo15l_v5.3.0.hef
if [ -n "$AERIAL_MODEL" ]; then
  [ -n "$AERIAL_SHA" ] || { echo "GARUDA_FRESH_AERIAL_HEF needs GARUDA_FRESH_AERIAL_HEF_SHA" >&2; exit 1; }
  AERIAL_ACTUAL="$(sha256sum "$AERIAL_MODEL")"
  [ "${AERIAL_ACTUAL%% *}" = "$AERIAL_SHA" ] || { echo "unexpected aerial HEF checksum" >&2; exit 1; }
fi
if [ -n "$REID_MODEL" ]; then
  REID_ACTUAL="$(sha256sum "$REID_MODEL")"
  [ "${REID_ACTUAL%% *}" = "$REID_SHA" ] || { echo "unexpected OSNet HEF checksum" >&2; exit 1; }
fi
# Optional aerial re-identification descriptor for perception-aerial.json (OSNet x1.0 fine-tuned
# on drone-view crops, bench/results/2026-09-18-reid-visdrone). A candidate like the aerial
# detector: path AND recorded hash, hash written beside the file for start-aerial to check.
AERIAL_REID_MODEL="${GARUDA_FRESH_AERIAL_REID_HEF:-}"
AERIAL_REID_SHA="${GARUDA_FRESH_AERIAL_REID_HEF_SHA:-}"
AERIAL_REID_DEST=/opt/garuda-fresh/models/osnet_aerial_hailo15l_v5.3.0.hef
if [ -n "$AERIAL_REID_MODEL" ]; then
  [ -n "$AERIAL_REID_SHA" ] || { echo "GARUDA_FRESH_AERIAL_REID_HEF needs GARUDA_FRESH_AERIAL_REID_HEF_SHA" >&2; exit 1; }
  AERIAL_REID_ACTUAL="$(sha256sum "$AERIAL_REID_MODEL")"
  [ "${AERIAL_REID_ACTUAL%% *}" = "$AERIAL_REID_SHA" ] || { echo "unexpected aerial OSNet HEF checksum" >&2; exit 1; }
fi
DEST=/opt/garuda-fresh
# The controlled COCO YOLO11s by default; a fine-tuned candidate must be staged with BOTH its
# path (GARUDA_FRESH_HEF) and its recorded hash (GARUDA_FRESH_HEF_SHA) so nothing is deployed
# by filename alone.
EXPECTED_HEF_SHA="${GARUDA_FRESH_HEF_SHA:-aec84f00e4797261e703689c670ad94a8558d584a35c776ca781611e34f32c58}"
LIB="$SDK/sysroots/armv8a-poky-linux/usr/lib/libturbojpeg.so.0.2.0"
for file in "$BUILD/garuda-fresh-tracking" "$BUILD/fresh-tracking/garuda-track-replay" "$LIB" "$MODEL" "$PHONE_MODEL"; do
  test -f "$file" || { echo "missing $file" >&2; exit 1; }
done
PHONE_ACTUAL="$(sha256sum "$PHONE_MODEL")"
[ "${PHONE_ACTUAL%% *}" = "$PHONE_SHA" ] || { echo "unexpected YOLOv8m HEF checksum" >&2; exit 1; }
MODEL_SHA="$(sha256sum "$MODEL")"
[ "${MODEL_SHA%% *}" = "$EXPECTED_HEF_SHA" ] || { echo "unexpected YOLO11s HEF checksum" >&2; exit 1; }
ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" '
  if pgrep -f "^/opt/garuda-fresh/garuda-fresh-tracking" >/dev/null; then
    echo "fresh tracker is running; stop it before restaging" >&2; exit 1
  fi
  test -f /usr/lib/hailo-post-processes/libyolo_hailortpp_post.so
  mkdir -p /opt/garuda-fresh/lib /opt/garuda-fresh/models /opt/garuda-fresh/backups
'
scp "$BUILD/garuda-fresh-tracking" "$BUILD/fresh-tracking/garuda-track-replay" "$ROOT/services/garuda-tracking/fresh_shim.py" \
    "$ROOT/services/garuda-tracking/fresh_tuning.py" "$ROOT/services/garuda-tracking/fresh_tuning.html" \
    "$ROOT/services/garuda-perception/shim/garuda_mono_shim.py" "$ROOT/hosts/hailo15l/fresh/"*.json "$HOST:$DEST/"
scp "$PHONE_MODEL" "$HOST:$DEST/models/"
if [ -n "$REID_MODEL" ]; then
  scp "$REID_MODEL" "$HOST:$DEST/models/osnet_x1_0_hailo15l_v5.3.0.hef"
  REID_ACTUAL="$(ssh -o BatchMode=yes "$HOST" 'sha256sum /opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef')"
  [ "${REID_ACTUAL%% *}" = "$REID_SHA" ] || { echo "board OSNet HEF checksum mismatch" >&2; exit 1; }
fi
if [ -n "$ROI_MODEL" ]; then
  scp "$ROI_MODEL" "$HOST:$DEST/models/yolov11m_hailo15l_v5.3.0.hef"
  ROI_ACTUAL="$(ssh -o BatchMode=yes "$HOST" 'sha256sum /opt/garuda-fresh/models/yolov11m_hailo15l_v5.3.0.hef')"
  [ "${ROI_ACTUAL%% *}" = "$ROI_SHA" ] || { echo "board ROI HEF checksum mismatch" >&2; exit 1; }
fi
if [ -n "$AERIAL_MODEL" ]; then
  scp "$AERIAL_MODEL" "$HOST:$AERIAL_DEST"
  AERIAL_BOARD="$(ssh -o BatchMode=yes "$HOST" "sha256sum $AERIAL_DEST")"
  [ "${AERIAL_BOARD%% *}" = "$AERIAL_SHA" ] || { echo "board aerial HEF checksum mismatch" >&2; exit 1; }
  ssh -o BatchMode=yes "$HOST" "printf '%s\n' '$AERIAL_SHA' > $AERIAL_DEST.sha256"
fi
if [ -n "$AERIAL_REID_MODEL" ]; then
  scp "$AERIAL_REID_MODEL" "$HOST:$AERIAL_REID_DEST"
  AERIAL_REID_BOARD="$(ssh -o BatchMode=yes "$HOST" "sha256sum $AERIAL_REID_DEST")"
  [ "${AERIAL_REID_BOARD%% *}" = "$AERIAL_REID_SHA" ] || { echo "board aerial OSNet HEF checksum mismatch" >&2; exit 1; }
  ssh -o BatchMode=yes "$HOST" "printf '%s\n' '$AERIAL_REID_SHA' > $AERIAL_REID_DEST.sha256"
fi
scp "$LIB" "$HOST:$DEST/lib/"
scp "$MODEL" "$HOST:$DEST/models/yolov11s_hailo15l_v5.3.0.hef"
ssh -o BatchMode=yes "$HOST" 'ln -sf libturbojpeg.so.0.2.0 /opt/garuda-fresh/lib/libturbojpeg.so.0'
BOARD_SHA="$(ssh -o BatchMode=yes "$HOST" 'sha256sum /opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef')"
[ "${BOARD_SHA%% *}" = "$EXPECTED_HEF_SHA" ] || { echo "board HEF checksum mismatch" >&2; exit 1; }
PHONE_BOARD_SHA="$(ssh -o BatchMode=yes "$HOST" 'sha256sum /opt/garuda-fresh/models/yolov8m_hailo15l_v5.3.0.hef')"
[ "${PHONE_BOARD_SHA%% *}" = "$PHONE_SHA" ] || { echo "board phone HEF checksum mismatch" >&2; exit 1; }
echo "Staged in $DEST; current services have not been changed."
