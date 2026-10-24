#!/usr/bin/env python3
"""Real-tensor golden for the C++ port of decode_yolo26 (Task 5, M2). Unlike make_yolo26_golden.py
(synthetic, hand-placed logits), this decodes the SIX RAW UINT16 tensors the plugin actually saw on
hardware: captured 2026-09-03 from the Hailo-15L SBC (root@10.0.0.1) running yolo26m through
libyolo26_post.so (Task 3) with its dump option enabled (`dump.path`/`dump.frames` in
/opt/garuda/yolo26_post.json), one bench-scene frame of a 3-frame capture — frame 0, chosen because
it decoded to the most detections (11 vs 10 and 8 for the other two; see task-5-report.md). Its
raw bytes are committed byte-for-byte as yolo26_real_frame.bin; TENSORS below is the dump's own
`.0.json` header, copied verbatim (name/shape/dtype/zp/scale/bytes are HEF-baked quantisation
parameters, identical across all three captured frames, not invented here).

This script only computes what the plugin's dump does not already give us: the float32
dequantisation (Task 1's formula), the letterbox geometry (lb_for, identical to the C++
letterbox_for), and the expected detections (hailo_yolo26_ref.decode_yolo26 — the Pi's decoder).
Re-running it reads the same committed .bin and TENSORS, so the output JSON is byte-identical
every time (md5-checked in task-5-report.md)."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ref", HERE / "hailo_yolo26_ref.py")
ref = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ref)

BIN_PATH = HERE / "yolo26_real_frame.bin"
JSON_PATH = HERE / "yolo26_real_frame.json"

# The dump's y26dump.0.json header, copied verbatim (order: box stride 8/16/32, then class
# stride 8/16/32 — matches the .bin's byte layout and hailo_yolo26_ref.PAIRS).
TENSORS = [
    {"name": "yolo26m/conv71", "shape": [80, 80, 4], "dtype": "uint16",
     "zp": 2533.0, "scale": 0.0003943115589208901, "bytes": 51200},
    {"name": "yolo26m/conv87", "shape": [40, 40, 4], "dtype": "uint16",
     "zp": 648.0, "scale": 0.0006043125176802278, "bytes": 12800},
    {"name": "yolo26m/conv101", "shape": [20, 20, 4], "dtype": "uint16",
     "zp": 191.0, "scale": 0.0005940418923273683, "bytes": 3200},
    {"name": "yolo26m/conv74", "shape": [80, 80, 80], "dtype": "uint16",
     "zp": 30347.0, "scale": 0.001344601041637361, "bytes": 1024000},
    {"name": "yolo26m/conv90", "shape": [40, 40, 80], "dtype": "uint16",
     "zp": 31322.0, "scale": 0.0026236155536025763, "bytes": 256000},
    {"name": "yolo26m/conv104", "shape": [20, 20, 80], "dtype": "uint16",
     "zp": 30891.0, "scale": 0.0025314053054898977, "bytes": 64000},
]
CONF_THRESH = 0.15
IOU_THRESH = 0.5
IN_W = IN_H = 640
FRAME_W, FRAME_H = 1280, 720


def lb_for(in_w, in_h, w, h):
    """Same formula as garuda::yolo26::letterbox_for (and make_yolo26_golden.py's lb_for)."""
    r = min(in_w / w, in_h / h)
    nw, nh = round(w * r), round(h * r)
    return (r, (in_w - nw) // 2, (in_h - nh) // 2)


def main():
    raw = BIN_PATH.read_bytes()
    outs = {}
    offset = 0
    for t in TENSORS:
        h, w, c = t["shape"]
        n = h * w * c
        nbytes = n * 2  # uint16
        assert t["bytes"] == nbytes, f"{t['name']}: header bytes {t['bytes']} != h*w*c*2 {nbytes}"
        assert t["dtype"] == "uint16", f"{t['name']}: unexpected dtype {t['dtype']}"
        arr = np.frombuffer(raw, dtype="<u2", count=n, offset=offset).reshape(h, w, c)
        offset += nbytes
        # Task 1's dequantisation: float32 throughout, (raw - zp) * scale.
        deq = (arr.astype(np.float32) - np.float32(t["zp"])) * np.float32(t["scale"])
        suffix = t["name"].rsplit("/", 1)[-1]
        outs[suffix] = deq
    assert offset == len(raw), f"consumed {offset} bytes, file is {len(raw)}"

    lb = lb_for(IN_W, IN_H, FRAME_W, FRAME_H)
    dets = ref.decode_yolo26(outs, FRAME_W, FRAME_H, "", CONF_THRESH, IOU_THRESH, lb,
                              in_w=IN_W, in_h=IN_H)

    out = {
        "tensors": TENSORS,
        "conf_thresh": CONF_THRESH,
        "iou_thresh": IOU_THRESH,
        "in_w": IN_W,
        "in_h": IN_H,
        "frame_w": FRAME_W,
        "frame_h": FRAME_H,
        "lb": list(lb),
        "expected": [[int(d.class_id), d.label, float(d.conf), float(d.x), float(d.y), float(d.w), float(d.h)]
                     for d in dets],
    }
    JSON_PATH.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(dets)} detections -> {JSON_PATH}")
    for d in dets:
        print(f"  {d.label:14s} conf={d.conf:.4f}  x={d.x:.2f} y={d.y:.2f} w={d.w:.2f} h={d.h:.2f}")


if __name__ == "__main__":
    main()
