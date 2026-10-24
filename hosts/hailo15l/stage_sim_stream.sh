#!/usr/bin/env bash
# Stage the demo's board stream executable and its bench profiles under /opt/garuda-sim.
# Bench only: nothing here touches the desk node's binary, profiles or models. The stream
# executable is the causal replay built by build_fresh_tracking.sh (it serves --stream); the
# grand demo's normal path /opt/garuda-sim/garuda-causal-stream-diagnostics is replaced, with
# the previous file kept beside it, and the profiles from hosts/hailo15l/sim/ are copied.
# profile-aerial.json refers to the aerial detector and aerial re-identification slots staged by
# stage_fresh_tracking.sh (GARUDA_FRESH_AERIAL_HEF/_SHA, GARUDA_FRESH_AERIAL_REID_HEF/_SHA) and
# is refused unless both slots' recorded hashes still match.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${GARUDA_H15L_HOST:-root@10.0.0.1}"
BUILD="${GARUDA_FRESH_BUILD:-/tmp/garuda-fresh}/h15l"
STREAM="$BUILD/garuda-causal-replay"
DEST=/opt/garuda-sim
STAMP="$(date +%Y%m%d-%H%M%S)"
test -f "$STREAM" || { echo "missing $STREAM (run build_fresh_tracking.sh)" >&2; exit 1; }
LOCAL_SHA="$(sha256sum "$STREAM" | cut -d' ' -f1)"
ssh -o BatchMode=yes -o ConnectTimeout=5 "$HOST" "
  set -e
  if pgrep -f '^$DEST/garuda-causal-stream' >/dev/null; then echo 'a board simulation stream is running; stop the demo first' >&2; exit 1; fi
  mkdir -p $DEST
  for CANDIDATE in /opt/garuda-fresh/models/yolov11s_aerial_hailo15l_v5.3.0.hef /opt/garuda-fresh/models/osnet_aerial_hailo15l_v5.3.0.hef; do
    EXPECTED=\$(cat \"\$CANDIDATE.sha256\") || { echo \"\$CANDIDATE not staged (stage_fresh_tracking.sh with GARUDA_FRESH_AERIAL_HEF / GARUDA_FRESH_AERIAL_REID_HEF)\" >&2; exit 1; }
    ACTUAL=\$(sha256sum \"\$CANDIDATE\")
    [ \"\${ACTUAL%% *}\" = \"\$EXPECTED\" ] || { echo \"\$CANDIDATE checksum mismatch\" >&2; exit 1; }
  done
  if [ -f $DEST/garuda-causal-stream-diagnostics ]; then cp -p $DEST/garuda-causal-stream-diagnostics $DEST/garuda-causal-stream-diagnostics.before-$STAMP; fi
"
scp -q "$STREAM" "$HOST:$DEST/garuda-causal-stream-diagnostics.new"
scp -q "$ROOT/hosts/hailo15l/sim/profile-fullview.json" "$ROOT/hosts/hailo15l/sim/profile-aerial.json" "$HOST:$DEST/"
BOARD_SHA="$(ssh -o BatchMode=yes "$HOST" "sha256sum $DEST/garuda-causal-stream-diagnostics.new" | cut -d' ' -f1)"
[ "$BOARD_SHA" = "$LOCAL_SHA" ] || { echo "stream executable checksum mismatch after transfer" >&2; exit 1; }
ssh -o BatchMode=yes "$HOST" "chmod +x $DEST/garuda-causal-stream-diagnostics.new && mv $DEST/garuda-causal-stream-diagnostics.new $DEST/garuda-causal-stream-diagnostics && test -x $DEST/garuda-causal-stream"
echo "Staged $DEST/garuda-causal-stream-diagnostics sha256 $LOCAL_SHA and profiles fullview/aerial; desk node untouched."
