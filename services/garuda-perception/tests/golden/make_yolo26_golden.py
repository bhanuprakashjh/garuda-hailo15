#!/usr/bin/env python3
"""Synthetic golden for the C++ port of decode_yolo26 (tests/golden/hailo_yolo26_ref.py, byte-identical
to the Pi's decoder). Cases: the Pi's own unit tests (letterbox at 640 and 960, squash resize), plus
per-class NMS, cross-class overlap kept, clamping at the frame edge, and a uint16-quantised variant.
Scores never sit within 1e-3 of a threshold (float32 vs float64 comparisons must not decide a case)."""
import importlib.util, json, pathlib
import numpy as np
here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ref", here / "hailo_yolo26_ref.py"); ref = importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
PREFIX = "yolo26m/"
GRID = {8: 80, 16: 40, 32: 20}     # the 640x640 HEF's grids; the reference only needs consistent shapes

def logit(p): return float(np.log(p / (1.0 - p)))
def empty_outs(grid=GRID):
    outs = {}
    for bsfx, csfx, s in ref.PAIRS:
        g = grid[s]
        outs[bsfx] = np.zeros((g, g, 4), np.float32)
        outs[csfx] = np.full((g, g, 80), -50.0, np.float32)
    return outs
def hit(outs, stride, y, x, class_id, score): outs[next(c for b, c, s in ref.PAIRS if s == stride)][y, x, class_id] = logit(score)
def place(outs, stride, y, x, x0, y0, x1, y1):
    """ltrb distances at cell (y,x)/stride so the decode reconstructs the letterboxed-space box (x0,y0,x1,y1)."""
    cx, cy = (x + 0.5) * stride, (y + 0.5) * stride
    outs[next(b for b, c, s in ref.PAIRS if s == stride)][y, x] = ((cx - x0) / stride, (cy - y0) / stride, (x1 - cx) / stride, (y1 - cy) / stride)
def lb_for(in_w, in_h, w, h):
    r = min(in_w / w, in_h / h); nw, nh = round(w * r), round(h * r)
    return (r, (in_w - nw) // 2, (in_h - nh) // 2)

cases = []
def add(name, outs, orig_w, orig_h, lb, conf=0.15, iou=0.5, in_w=640, in_h=640, quantise=False):
    tensors = {}
    outs_for_ref = {}
    for k, arr in outs.items():
        is_box = any(k == b for b, c, s in ref.PAIRS)
        fill_val = 0.0 if is_box else -50.0   # box tensors default 0.0 (empty_outs), class tensors default -50.0
        if quantise:
            # emulate the HEF's UINT16 output: choose zp/scale covering the array's range with margin, round to uint16
            lo, hi = float(arr.min()) - 1.0, float(arr.max()) + 1.0
            scale = np.float32((hi - lo) / 65535.0); zp = np.float32(-lo / float(scale))
            raw = np.clip(np.round(arr / scale + zp), 0, 65535).astype(np.uint16)
            deq = (raw.astype(np.float32) - np.float32(zp)) * np.float32(scale)
            fill_raw = int(np.clip(np.round(fill_val / scale + zp), 0, 65535))
            idx = np.argwhere(raw != fill_raw)
            entries = [[int(y), int(x), int(ch), int(raw[y, x, ch])] for y, x, ch in idx]
            tensors[PREFIX + k] = {"shape": list(arr.shape), "dtype": "uint16", "zp": float(zp), "scale": float(scale), "fill": fill_raw, "entries": entries}
            outs_for_ref[k] = deq
        else:
            idx = np.argwhere(arr != fill_val)
            entries = [[int(y), int(x), int(ch), float(arr[y, x, ch])] for y, x, ch in idx]
            tensors[PREFIX + k] = {"shape": list(arr.shape), "dtype": "float32", "zp": 0.0, "scale": 1.0, "fill": fill_val, "entries": entries}
            outs_for_ref[k] = arr
    dets = ref.decode_yolo26(outs_for_ref, orig_w, orig_h, "", conf, iou, lb, in_w=in_w, in_h=in_h)
    cases.append({"name": name, "in_w": in_w, "in_h": in_h, "orig_w": orig_w, "orig_h": orig_h, "lb": list(lb) if lb else None,
                  "conf_thresh": conf, "iou_thresh": iou, "tensors": tensors,
                  "expected": [[int(d.class_id), d.label, float(d.conf), float(d.x), float(d.y), float(d.w), float(d.h)] for d in dets]})

# 1) the Pi's unit test at 640: one person box (100,100,400,200) px in a 1280x720 frame
lb = lb_for(640, 640, 1280, 720); o = empty_outs(); hit(o, 8, 0, 0, 0, 0.9); place(o, 8, 0, 0, 100*lb[0]+lb[1], 100*lb[0]+lb[2], 500*lb[0]+lb[1], 300*lb[0]+lb[2]); add("pi_letterbox_640", o, 1280, 720, lb, conf=0.3)
# 2) the Pi's unit test at 960 (a different net size; grids scale with it)
lb9 = lb_for(960, 960, 1280, 720); g9 = {8: 120, 16: 60, 32: 30}; o = empty_outs(g9); hit(o, 8, 0, 0, 0, 0.9); place(o, 8, 0, 0, 100*lb9[0]+lb9[1], 100*lb9[0]+lb9[2], 500*lb9[0]+lb9[1], 300*lb9[0]+lb9[2]); add("pi_letterbox_960", o, 1280, 720, lb9, conf=0.3, in_w=960, in_h=960)
# 3) the Pi's squash-resize test (lb=None): car at 0.6
o = empty_outs(); rx, ry = 640/1280, 640/720; hit(o, 8, 0, 0, 2, 0.6); place(o, 8, 0, 0, 100*rx, 100*ry, 500*rx, 300*ry); add("pi_squash_640", o, 1280, 720, None, conf=0.3)
# 4) per-class NMS: two overlapping person boxes at stride 16 -> the higher score survives; plus a cup overlapping both, kept (different class)
o = empty_outs(); hit(o, 16, 5, 5, 0, 0.8); place(o, 16, 5, 5, 60, 150, 200, 400); hit(o, 16, 5, 6, 0, 0.7); place(o, 16, 5, 6, 70, 160, 210, 410); hit(o, 16, 6, 5, 41, 0.5); place(o, 16, 6, 5, 80, 170, 220, 420); add("nms_per_class", o, 1280, 720, lb)
# 5) same two persons but NOT overlapping enough (IoU below 0.5) -> both kept, sorted by conf
o = empty_outs(); hit(o, 16, 5, 5, 0, 0.8); place(o, 16, 5, 5, 60, 150, 160, 300); hit(o, 16, 9, 9, 0, 0.7); place(o, 16, 9, 9, 250, 300, 350, 450); add("nms_no_overlap", o, 1280, 720, lb)
# 6) clamping: a box extending into the letterbox padding and past the left edge -> clamped to [0, orig]
o = empty_outs(); hit(o, 32, 0, 0, 56, 0.9); place(o, 32, 0, 0, -30, 100, 200, 180); add("clamp_edges", o, 1280, 720, lb)
# 7) below-threshold candidates are dropped; a class-79 (toothbrush) and class-0 mix at stride 8, one under conf 0.15
o = empty_outs(); hit(o, 8, 10, 10, 79, 0.16); place(o, 8, 10, 10, 80, 200, 120, 260); hit(o, 8, 20, 20, 0, 0.14); place(o, 8, 20, 20, 160, 300, 220, 400); add("threshold_015", o, 1280, 720, lb)
# 8) the uint16 variant of case 4 (dequantised in float32 on both sides)
o = empty_outs(); hit(o, 16, 5, 5, 0, 0.8); place(o, 16, 5, 5, 60, 150, 200, 400); hit(o, 16, 5, 6, 0, 0.7); place(o, 16, 5, 6, 70, 160, 210, 410); hit(o, 16, 6, 5, 41, 0.5); place(o, 16, 6, 5, 80, 170, 220, 420); add("nms_per_class_uint16", o, 1280, 720, lb, quantise=True)
(here / "yolo26_golden.json").write_text(json.dumps({"format": "sparse-v1", "cases": cases}, indent=1) + "\n")
print(len(cases), "cases ->", here / "yolo26_golden.json", "expected counts:", [len(c["expected"]) for c in cases])
