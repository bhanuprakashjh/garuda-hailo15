#!/bin/bash
# Inside the separate ROS rootfs. No MAVROS launch, flight endpoint or services.
set -eo pipefail
test "${GARUDA_SIM:-}" = 1
source /opt/ros/jazzy/setup.bash
export PYTHONPATH=/opt/garuda:${PYTHONPATH:-}
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_LOCALHOST_ONLY=1
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export ROS_DOMAIN_ID=73
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces><NetworkInterface name="lo" multicast="true"/></Interfaces><AllowMulticast>true</AllowMulticast></General></Domain></CycloneDDS>'
exec python3 /opt/garuda/native_camera_observe.py "$@"
