# Gazebo visual-follow bench dependencies

Local evaluation only; no new board packages or product runtime dependency.
Existing Gazebo Harmonic: gz-sim 8.10.0, gz-transport 13.5.0 Python bindings,
gz-msgs 10 (Apache-2.0). Existing NumPy (BSD-3-Clause) and Pillow (HPND)
handle fixed-shape RGB → BT.601 limited-range NV12 and preview JPEGs.
PX4 is BSD-3-Clause. Existing pymavlink remains bench-only (LGPL-3.0).
HEFs retain their existing model/licensing status; this adds no model weights.

Actor attribution: **Mingfei, “actor”, version 1**, Gazebo Fuel,
CC BY 4.0, https://fuel.gazebosim.org/1.0/Mingfei/models/actor/1 .
License metadata checked through Fuel API on 2026-09-13;
https://creativecommons.org/licenses/by/4.0/ .
The original walking mesh/texture is unmodified; the world supplies a new
trajectory. Download into the normal external Fuel cache, not into this repo:

```
gz fuel download -u https://fuel.gazebosim.org/1.0/Mingfei/models/actor/1
```

Primary transport documentation:
https://gazebosim.org/api/transport/13/python.html .
Asset realism, detector domain shift, actor depth rendering and source timing
must be tested. Successful synthetic-world following is not outdoor validation.
