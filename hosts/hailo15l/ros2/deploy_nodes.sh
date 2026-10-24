#!/usr/bin/env bash
# Idempotent node staging into the owned bench userspace; no desk replacement.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ssh -oBatchMode=yes root@10.0.0.1 '
  test -f /opt/garuda-ros-jazzy/.garuda-bench-rootfs
  if pgrep -f "^python3 /opt/garuda/mavros_node.py " >/dev/null; then
    echo "Stop the owned ROS simulation before staging nodes" >&2; exit 1
  fi
  mkdir -p /opt/garuda-ros-jazzy/opt/garuda/garuda_interfaces
'
scp "$ROOT"/hosts/hailo15l/ros2/mavros_node.py "$ROOT"/hosts/hailo15l/ros2/mavros.yaml \
  "$ROOT"/hosts/hailo15l/ros2/native_camera.py "$ROOT"/hosts/hailo15l/ros2/native_camera_observe.py \
  "$ROOT"/hosts/hailo15l/ros2/run_camera_observe.sh \
  "$ROOT"/hosts/hailo15l/ros2/run_board.sh "$ROOT"/bench/sim/mavros_contract.py \
  "$ROOT"/services/garuda-follow/{perception_authority,follow_authority,follow_controller,fresh_follow,fresh_target_adapter}.py \
  "$ROOT"/services/garuda-bridge/sim_offboard_bridge.py \
  root@10.0.0.1:/opt/garuda-ros-jazzy/opt/garuda/
scp "$ROOT"/interfaces/garuda_interfaces/*.py root@10.0.0.1:/opt/garuda-ros-jazzy/opt/garuda/garuda_interfaces/
