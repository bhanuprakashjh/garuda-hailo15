#!/usr/bin/env python3
"""Make an all-classes A/B copy of a `services/garuda-perception/config/perception-yolov*.json`
config: set `tracker.hailo.classification_id` to -1 (no class filter -- the SDK tracker's default
`1` is person-only) and `jpeg_fps` to 30 (the shim's SSE capture rate for these routines, matching
`sse_capture_flush.py`'s 30 Hz shim cap rather than a config's own default, which varies per model).

Written for the 2026-09-04 evening detector A/B (bench/benchlog.md, "Hailo-15L SBC: detector A/B on
the phone -- yolov8m vs yolov11m vs yolov11s"): the same owner-paced phone routine run once per
model, all-classes so the capture also carries a `person` reference line and the `cell phone` boxes
that are otherwise filtered out under the shipped person-only profile.

usage: mk_allclasses.py <src config> <dst config>
       mk_allclasses.py services/garuda-perception/config/perception-yolov11s.json \
           /tmp/perception-yolov11s-allclasses.json
"""
import json
import sys

if len(sys.argv) != 3:
    sys.exit(__doc__)

src, dst = sys.argv[1], sys.argv[2]
c = json.load(open(src))
c["tracker"]["hailo"]["classification_id"] = -1
c["jpeg_fps"] = 30
json.dump(c, open(dst, "w"), indent=2)
open(dst, "a").write("\n")
print(dst, "hef", c["hef"].split("/")[-1], "classification_id", c["tracker"]["hailo"]["classification_id"],
      "jpeg_fps", c["jpeg_fps"])
