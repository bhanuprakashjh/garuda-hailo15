#!/usr/bin/env bash
# Explicit bench lifecycle; never installs an init script or alters boot startup.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOST="${GARUDA_H15L_HOST:-root@10.0.0.1}"
ACTION="${1:-status}"
case "$ACTION" in
  status)
    ssh -o BatchMode=yes "$HOST" 'pgrep -af "^/opt/garuda-fresh/garuda-fresh-tracking|^python3 /opt/garuda-fresh/fresh_shim.py"; curl -s --max-time 3 http://127.0.0.1:8099/api/state'
    ;;
  start|start-current|start-phone|start-letterbox|start-tiles|start-follow|start-follow-native|start-follow-native-compare|start-aerial|start-person-reid|start-capture|start-paired-capture|start-similarity|start-roi-assist|start-roi-shadow)
    CONFIG_NAME=perception.json
    if [ "$ACTION" = start-current ]; then CONFIG_NAME=current.json; fi
    if [ "$ACTION" = start-phone ]; then CONFIG_NAME=perception-yolov8m-phone.json; fi
    if [ "$ACTION" = start-letterbox ]; then CONFIG_NAME=perception-letterbox.json; fi
    if [ "$ACTION" = start-tiles ]; then CONFIG_NAME=perception-tiles.json; fi
    if [ "$ACTION" = start-follow ]; then CONFIG_NAME=perception-follow.json; fi
    if [ "$ACTION" = start-follow-native ]; then CONFIG_NAME=perception-follow-native.json; fi
    if [ "$ACTION" = start-follow-native-compare ]; then CONFIG_NAME=perception-follow-native-compare.json; fi
    if [ "$ACTION" = start-aerial ]; then CONFIG_NAME=perception-aerial.json; fi
    if [ "$ACTION" = start-person-reid ]; then CONFIG_NAME=perception-person-reid-bench.json; fi
    if [ "$ACTION" = start-capture ]; then CONFIG_NAME=perception-stream-bench.json; fi
    if [ "$ACTION" = start-paired-capture ]; then CONFIG_NAME=perception-paired-stream-bench.json; fi
    if [ "$ACTION" = start-similarity ]; then CONFIG_NAME=perception-similarity-bench.json; fi
    if [ "$ACTION" = start-roi-assist ]; then CONFIG_NAME=perception-roi-assist-bench.json; fi
    if [ "$ACTION" = start-roi-shadow ]; then CONFIG_NAME=perception-roi-shadow-bench.json; fi
    ssh -o BatchMode=yes "$HOST" sh -s "$CONFIG_NAME" <<'REMOTE_START'
      set -e
      case "$1" in perception-roi-assist-bench.json|perception-roi-shadow-bench.json)
        CAPS=$(LD_LIBRARY_PATH=/opt/garuda-fresh/lib /opt/garuda-fresh/garuda-fresh-tracking --capabilities 2>/dev/null) || {
          echo "ROI profile requires the new build; build and stage it first" >&2; exit 1;
        }
        case "$CAPS" in *'"target_roi_v1":true'*) ;; *) echo "binary lacks target ROI support" >&2; exit 1 ;; esac
      esac
      if pgrep -f "^/opt/garuda-fresh/garuda-fresh-tracking " >/dev/null; then
        if cmp -s "/opt/garuda-fresh/$1" /opt/garuda-fresh/current.json; then echo "already running this profile"; exit 0; fi
        echo "another profile is running; stop it before switching profiles" >&2; exit 1
      fi
      case "$1" in perception-person-reid-bench.json|perception-follow.json|perception-follow-native.json|perception-follow-native-compare.json)
        ACTUAL=$(sha256sum /opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef) || { echo "OSNet HEF not staged" >&2; exit 1; }
        [ "${ACTUAL%% *}" = 49a46e48ee96e51bb5ccd6f739879402cce018c00803fe64ea70f4957bdf34f7 ] || exit 1
      esac
      case "$1" in perception-aerial.json)
        # The aerial detector and the aerial re-identification descriptor are staged candidates:
        # each starts only against the hash recorded next to it by stage_fresh_tracking.sh
        # (GARUDA_FRESH_AERIAL_HEF_SHA / GARUDA_FRESH_AERIAL_REID_HEF_SHA), never by filename.
        for CANDIDATE in /opt/garuda-fresh/models/yolov11s_aerial_hailo15l_v5.3.0.hef /opt/garuda-fresh/models/osnet_aerial_hailo15l_v5.3.0.hef; do
          EXPECTED=$(cat "$CANDIDATE.sha256") || { echo "$CANDIDATE not staged" >&2; exit 1; }
          ACTUAL=$(sha256sum "$CANDIDATE") || exit 1
          [ "${ACTUAL%% *}" = "$EXPECTED" ] || { echo "$CANDIDATE checksum mismatch" >&2; exit 1; }
        done
      esac
      case "$1" in perception-roi-assist-bench.json|perception-roi-shadow-bench.json)
        ACTUAL=$(sha256sum /opt/garuda-fresh/models/yolov11m_hailo15l_v5.3.0.hef)
        [ "${ACTUAL%% *}" = 65d875e84dc4ad7c18789724c6cbef534c3cf712c7d578a624e2a71d2587ec20 ] || exit 1
      esac
      if [ "$1" != current.json ]; then cp "/opt/garuda-fresh/$1" /opt/garuda-fresh/current.json; fi
      test -x /opt/garuda-fresh/garuda-fresh-tracking
      if test -x /etc/init.d/garuda-perception; then /etc/init.d/garuda-perception stop; fi
      cd /opt/garuda-fresh
      LD_LIBRARY_PATH=/opt/garuda-fresh/lib nohup /opt/garuda-fresh/garuda-fresh-tracking --config /opt/garuda-fresh/current.json > /tmp/garuda-fresh.log 2>&1 < /dev/null &
      echo $! > /tmp/garuda-fresh.pid
      if ! pgrep -f "^python3 /opt/garuda-fresh/fresh_shim.py" >/dev/null; then
        nohup python3 /opt/garuda-fresh/fresh_shim.py > /tmp/garuda-fresh-shim.log 2>&1 < /dev/null &
        echo $! > /tmp/garuda-fresh-shim.pid
      fi
REMOTE_START
    python3 "$ROOT/hosts/hailo15l/wait_fresh_camera.py" --host "${HOST#*@}"
    ;;
  stop|restore)
    ssh -o BatchMode=yes "$HOST" '
      pkill -TERM -f "^/opt/garuda-fresh/garuda-fresh-tracking " || true
      pkill -TERM -f "^python3 /opt/garuda-fresh/fresh_shim.py" || true
      # Tearing down the media pipeline and the NPU after SIGTERM occasionally takes more than
      # the 2 s this used to allow (two replay campaigns lost a clip to it on 2026-09-18).
      for i in $(seq 50); do
        if ! pgrep -f "^/opt/garuda-fresh/garuda-fresh-tracking " >/dev/null; then exit 0; fi
        sleep 0.2
      done
      echo "fresh process did not stop; inspect /tmp/garuda-fresh.log" >&2; exit 1
    '
    if [ "$ACTION" = restore ]; then ssh -o BatchMode=yes "$HOST" '/etc/init.d/garuda-perception start'; fi
    ;;
  *) echo "usage: $0 [start|start-current|start-phone|start-letterbox|start-tiles|start-follow|start-follow-native|start-follow-native-compare|start-aerial|start-person-reid|start-capture|start-paired-capture|start-similarity|start-roi-assist|start-roi-shadow|stop|status|restore]" >&2; exit 2 ;;
esac
