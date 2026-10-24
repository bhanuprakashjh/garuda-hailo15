#!/usr/bin/env bash
# One owned simulator at a time. No real-FC option; no hot source switch in flight.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "${GARUDA_SIM:-}" != 1 ]; then echo 'Set GARUDA_SIM=1; simulation only' >&2; exit 2; fi
if [ "$#" -lt 2 ]; then
  echo 'usage: run_grand_demo.sh live|gazebo NEW_OUTPUT [--aerial] [runner options]'
  echo '       run_grand_demo.sh replay NEW_OUTPUT PREPARED_DATASET [--aerial] [runner options]'
  echo '       --aerial: board runs the staged aerial profile (VisDrone fine-tuned HEF, wide caps,'
  echo '                 1500/2000 follow schedule, adaptive tiles+ROI) instead of the desk fullview profile'
  exit 2
fi
MODE="$1"; OUT="$2"; shift 2
# The board profile for gazebo/replay: the desk-derived fullview profile by default, the aerial
# profile with --aerial (both staged by hosts/hailo15l/stage_sim_stream.sh). Live mode reads the
# desk node, whose profile is chosen with fresh_tracking_ctl.sh.
PROFILE=/opt/garuda-sim/profile-fullview.json
ARGS=()
for arg in "$@"; do
  if [ "$arg" = --aerial ]; then PROFILE=/opt/garuda-sim/profile-aerial.json; else ARGS+=("$arg"); fi
done
set -- "${ARGS[@]+"${ARGS[@]}"}"
if pgrep -x px4 >/dev/null; then echo 'Stop the existing owned demo before switching sources' >&2; exit 1; fi
if [ -e "$OUT" ]; then echo 'Use a new output directory; evidence is never overwritten' >&2; exit 2; fi
case "$MODE" in
  live)
    exec python3 "$ROOT/bench/sim/gazebo_follow.py" --out "$OUT" --live-camera --transport mavros-15l --gui "$@"
    ;;
  gazebo)
    exec bash "$ROOT/hosts/hailo15l/run_visual_sim.sh" --out "$OUT" --transport mavros-15l --gui \
      --board-binary /opt/garuda-sim/garuda-causal-stream-diagnostics \
      --board-profile "$PROFILE" "$@"
    ;;
  replay)
    if [ "$#" -lt 1 ] || [ ! -f "$1/manifest.json" ] || [ ! -f "$1/source.nv12" ]; then
      echo 'Existing prepared manifest.json and source.nv12 required' >&2; exit 2
    fi
    REPLAY="$1"; shift
    # Interactive use: the clip restarts when it ends (loop count shown in the console) so the
    # operator can take off, click and watch at their own pace; a clip is 20–75 s long.
    exec bash "$ROOT/hosts/hailo15l/run_visual_sim.sh" --out "$OUT" --transport mavros-15l --gui \
      --board-binary /opt/garuda-sim/garuda-causal-stream-diagnostics \
      --board-profile "$PROFILE" --replay "$REPLAY" --replay-loop "$@"
    ;;
  *) echo 'Mode must be live, gazebo or replay' >&2; exit 2 ;;
esac
