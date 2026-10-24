#!/bin/bash
# Executed INSIDE the separate rootfs, via an owned SSH simulation session.
set -eo pipefail
test "${GARUDA_SIM:-}" = 1
test "$#" = 1 || { test "$#" = 2 && test "$2" = axis-test; } || { test "$#" = 3 && test "$2" = camera; }
source /opt/ros/jazzy/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=1
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=73
export PYTHONPATH=/opt/garuda:$PYTHONPATH
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="lo" multicast="true"/></Interfaces><AllowMulticast>true</AllowMulticast></General></Domain></CycloneDDS>'
/opt/ros/jazzy/lib/mavros/mavros_node --ros-args --params-file /opt/garuda/mavros.yaml >&2 &
MAVROS_PID=$!
cleanup() { kill -TERM "$MAVROS_PID" 2>/dev/null || true; wait "$MAVROS_PID" 2>/dev/null || true; }
trap cleanup EXIT
python3 /opt/garuda/mavros_node.py "$@"
