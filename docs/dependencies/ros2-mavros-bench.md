# ROS 2 / MAVROS on Hailo-15L — bench dependency boundary

Owner requires ROS 2 and MAVROS on the 15L, not just the PC. Native HailoRT
and inference stay on stock Yocto; Jazzy/MAVROS use a separately installed
Ubuntu Noble ARM64 userspace at `/opt/garuda-ros-jazzy`. This is an explicit
bench alternative to the Pi Docker decision: no Docker runtime exists on this
board. It is not a security sandbox or a production Yocto port.

- Ubuntu Base 24.04.4 ARM64: package-specific licenses, including GPL system
  utilities. **Bench/evaluation only, not-product-cleared**. No host library,
  driver, kernel, boot or partition replacement.
- ROS 2 Jazzy core: Apache-2.0/BSD package-specific licensing.
- MAVROS / mavros_msgs: GPL-3.0 and BSD-3-Clause components; keep the executable
  as a separate bench process, not linked into shippable services.
- CycloneDDS: EPL-2.0 / EDL-1.0; rmw_cyclonedds_cpp: Apache-2.0.
- GeographicLib: MIT software; data is separate. Installed EGM96-5 geoid grid
  from the GeographicLib distribution, derived from NGA EGM96. See the
  [GeographicLib data description](https://geographiclib.sourceforge.io/C++/doc/geoid.html).
  This attribution is not a product redistribution license approval.
  Archive SHA256: `c46224f8f723dc915d97179f4e1580a98d6c742fe2b82cd8fef0ecaaad13e614`.

The installer uses signed apt metadata. Retain `dpkg-query -W`, the rootfs
checksum, ROS key checksum and installation logs with each bench run. The
package proxy is temporary, host-allowlisted, GET-only, PC loopback, forwarded
over SSH. Board routing/DNS are unchanged. Product integration requires
license review and reproducible recipes against the product Yocto release.

Installed Ubuntu Base 24.04.4 ARM64 archive SHA256:
`04207713ece899c3740823d33690441ad3a7f0ded1101aca744e2b0f37ac7ff2`.
MAVROS `2.15.1-1noble.20260903.001241`, rclpy
`7.1.12-1noble.20260902.143245`, rmw_cyclonedds_cpp
`2.2.4-1noble.20260902.140937`. Full package inventory is in the run snapshots.
The installer currently resolves signed repository versions; it is **not** an
offline, pinned, production-reproducible image build. Retained inventory/hash
evidence does not fix that limitation.

References: https://docs.ros.org/en/jazzy/Installation.html,
https://github.com/mavlink/mavros, https://github.com/eclipse-cyclonedds/cyclonedds.
