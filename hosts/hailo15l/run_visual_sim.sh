#!/usr/bin/env bash
# Bench only: temporarily lend the 15L NPU to Gazebo. No boot/driver/HEF changes.
# Run in foreground; Ctrl-C lands the owned simulator, then restores the desk app.
# The stream executable must first be staged alongside, under /opt/garuda-sim.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "${GARUDA_SIM:-}" != 1 ]; then echo "GARUDA_SIM=1 is required" >&2; exit 2; fi
if [ "$#" -lt 2 ] || [ "$1" != --out ]; then
  echo "usage: GARUDA_SIM=1 bash hosts/hailo15l/run_visual_sim.sh --out NEW_DIRECTORY [--auto-demo --duration 60]" >&2
  exit 2
fi
OUT="$2"
if [ -e "$OUT" ]; then echo "Use a new output directory; evidence is never overwritten" >&2; exit 2; fi
ssh -oBatchMode=yes -oConnectTimeout=5 root@10.0.0.1 '
  test -x /opt/garuda-sim/garuda-causal-stream
  test -r /opt/garuda-sim/profile.json
  if pgrep -f "^/opt/garuda-sim/garuda-causal-stream" >/dev/null; then
    echo "A board simulation stream is already running" >&2; exit 1
  fi
'
WAS_RUNNING=0
if ssh -oBatchMode=yes root@10.0.0.1 'pgrep -f "^/opt/garuda-fresh/garuda-fresh-tracking " >/dev/null'; then
  WAS_RUNNING=1
fi
restore_desk() {
  if [ "$WAS_RUNNING" = 1 ]; then
    echo "Restoring the desk pipeline using its unchanged current.json (selection will be cleared)."
    bash "$ROOT/hosts/hailo15l/fresh_tracking_ctl.sh" start-current || {
      echo "DESK RESTORE FAILED: run fresh_tracking_ctl.sh start-current and inspect the board" >&2
      return 1
    }
  fi
}
trap restore_desk EXIT
if [ "$WAS_RUNNING" = 1 ]; then
  echo "Pausing the desk camera. Its binary, profile, models and ISP configuration files are retained."
  bash "$ROOT/hosts/hailo15l/fresh_tracking_ctl.sh" stop
fi
python3 "$ROOT/bench/sim/gazebo_follow.py" --board-binary /opt/garuda-sim/garuda-causal-stream "$@"
