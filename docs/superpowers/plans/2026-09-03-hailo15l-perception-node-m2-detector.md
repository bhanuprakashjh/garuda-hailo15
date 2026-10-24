# Hailo-15L Perception Node — M2 (yolo26m detector + own post-process) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The board detects the 80 COCO classes with the same yolo26m model the Pi runs, decoded by a line-for-line port of the Pi's decoder running as the pipeline's post-process plugin, with letterboxed 640×640 input, the tracker's 0.15 floor finally live, a one-flag rollback to the stock detector, and numbers recorded.

**Architecture:** The model is Hailo's model-zoo `yolo26m` for `hailo15l` (already fetched, parsed and benchmarked — `models/yolo26m_h15l.md`). It exposes six raw UINT16 heads and no baked NMS, so a new shared library `libyolo26_post.so` implements the post stage's `init`/`filter`/`free_resources` ABI: it finds the six tensors on the ROI, dequantises them with the vstream zero-point/scale, decodes exactly as `hosts/pi5/hailo_yolo26.py` (ltrb×stride, sigmoid, per-class greedy NMS), un-letterboxes to frame pixels, and attaches standard detections normalised to the frame — so the node's detection callback keeps its current `xmin*FW` mapping unchanged. The decode itself lives in the core library (`garuda::yolo26`, no Hailo dependency) and is proven by golden tests generated from a byte-identical copy of the Pi decoder: synthetic cases (the Pi's own unit tests plus NMS/quantisation cases) and one real frame's raw tensors dumped on the board. The media-library profile letterboxes sink0 to 640×640; deploy gains a models step and a config switch.

**Tech Stack:** C++17, CMake (native tests + cross-build with the Hailo-15L SDK), nlohmann/json (vendored), Hailo `hailo_postprocess_tools` / `hailo_analytics` headers (board SDK), Python 3 + numpy (golden generation), `hailortcli` on the board.

**Spec:** `docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md` §8 item 3 (the approved M2 design, verbatim), §4 (contracts), §5 (bench gate), §7 (testing). Decisions: `docs/decisions.md` 2026-09-03 "(direction)".

## Global Constraints

- **Model:** `/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef` on the board (md5 `3aef604ab89ddaf9ecb4cefa9c6ea8af`, fetched by `models/fetch_yolo26m_h15l.sh`); input `yolo26m/input_layer1` NV12 640×640; outputs UINT16 `yolo26m/conv71` 80×80×4, `yolo26m/conv87` 40×40×4, `yolo26m/conv101` 20×20×4 (ltrb box heads, strides 8/16/32) and `yolo26m/conv74` 80×80×80, `yolo26m/conv90` 40×40×80, `yolo26m/conv104` 20×20×80 (class logits). No local recompile; no other HEF.
- **Parity is a test:** the decode is compared against `tests/golden/hailo_yolo26_ref.py`, a byte-identical copy of `feat/portal-tracking:hosts/pi5/hailo_yolo26.py`, never edited. Constants as the Pi runs them: `conf_thresh` = the tracker's `track.conf_floor` = 0.15, `iou_thresh` = 0.5, letterbox pad computed as `HailoYolo26.infer` does (`r = min(in_w/w, in_h/h)`, `nw,nh = round(w*r), round(h*r)`, `px = (in_w-nw)//2`, `py = (in_h-nh)//2`), COCO-80 lowercase names from the same file.
- **Numeric fidelity:** confidences computed as float32 sigmoid of the per-cell maximum logit (identical to numpy's `sigmoid(cls).max(-1)` for that element); argmax keeps the FIRST maximal class; candidates generated in the Python's order (strides 8, 16, 32; rows then columns) and sorted by descending confidence with a STABLE sort; geometry in double from float32 inputs; dequantisation `(raw - zp) * scale` in float32 (HailoTensor `fix_scale` semantics). Golden tolerances: confidence ±1e-5, pixels ±1e-3 for synthetic cases; the real-tensor golden ±1e-3 px and ±1e-5 conf after both sides dequantise in float32. Golden cases never place a score within 1e-3 of a threshold.
- **Snapshot contract unchanged** (v2; boxes in 1280×720 px; `tracks[].label` = COCO name). Tracker/lock code untouched. Threading: the plugin runs in the post stage's thread with no shared state beyond its own params; the node's detection callback keeps its contract from M1.
- **Rule 1:** every number in docs/commits comes from a pasted run on this board with conditions; `TBD-bench` otherwise. **Rule 6:** no new dependency (`libhailo_postprocess_tools.so.1` is on the image; nlohmann/json is vendored); the AGPL note where the model is fetched (already in the fetch script and card). **Rule 9:** red-team paragraph on every measurement.
- Board `root@10.0.0.1`; writes only under `/opt/garuda/`, `/etc/init.d/garuda-perception`, rc links, `/var/run`, `/tmp`; deploy via `hosts/hailo15l/deploy.sh`; never `pkill -x`; only anchored `pkill -f "^..."`; never a pattern matching your own shell; do not reboot; do not touch the Pi. Cross-build: source `/media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux`, `cmake -S services/garuda-perception -B services/garuda-perception/build-h15l -G Ninja -DCMAKE_TOOLCHAIN_FILE=$OECORE_NATIVE_SYSROOT/usr/share/cmake/OEToolchainConfig.cmake -DGARUDA_BUILD_NODE=ON -DGARUDA_BUILD_TESTS=OFF`, zero `warning:` lines under `-Wall -Wextra`. Native: `build-x86` at the worktree root (`-DGARUDA_BUILD_NODE=OFF -DGARUDA_BUILD_TESTS=ON`), `ctest` stays green (6 existing + new).
- Branch `feat/hailo15l-detector` (worktree `.claude/worktrees/feat-hailo15l-detector`, from `feat/hailo15l-perception` at 4fee82b). Commit trailer on every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_015dfMKyBmLK5bdtwfFmzgHq`.

---

## File structure

```
services/garuda-perception/
  include/garuda/yolo26_decode.hpp      # garuda::yolo26 — TensorView, Params, Letterbox, RawDet, decode(), letterbox_for(), COCO
  src/yolo26_decode.cpp                 # the port of decode_yolo26 (+ _sigmoid, _iou) — no Hailo dependency
  postprocess/yolo26_post.cpp           # the plugin: extern "C" init/filter/free_resources; tensor lookup; dump; HailoDetection output
  postprocess/CMakeLists.txt            # SHARED target yolo26_post (GARUDA_BUILD_NODE only), links garuda_perception_core + hailo_postprocess_tools
  config/yolo26_post.json               # plugin config: thresholds, geometry, tensor prefix, labels, dump
  config/perception.json                # hef/postprocess_so/postprocess_config -> the yolo26m artifacts; dump geometry keys
  config/perception-yolov8n.json        # the M1 configuration, kept verbatim for rollback
  tests/golden/hailo_yolo26_ref.py      # byte-identical copy of feat/portal-tracking:hosts/pi5/hailo_yolo26.py
  tests/golden/make_yolo26_golden.py    # synthetic cases -> yolo26_golden.json (float32 and uint16 tensors, base64)
  tests/golden/yolo26_golden.json       # generated, committed
  tests/golden/yolo26_real_frame.bin    # Task 5: one frame's six raw tensors dumped on the board (~1.4 MB)
  tests/golden/yolo26_real_frame.json   # Task 5: header (names/shapes/zp/scale) + expected boxes from the Python
  tests/golden/make_yolo26_real_golden.py
  tests/test_yolo26_decode.cpp          # replays yolo26_golden.json through garuda::yolo26::decode
  tests/test_yolo26_real.cpp            # replays the real frame
hosts/hailo15l/medialib/make_profile.py # sink0 640x640 LETTERBOX_MIDDLE; regenerate the JSON
hosts/hailo15l/deploy.sh                # models step (HEF/plugin/post config), GARUDA_PERCEPTION_CONFIG switch
hosts/hailo15l/README.md                # M2 sections
```

---

### Task 1: Reference copy and the synthetic golden (Python)

**Files:**
- Create: `services/garuda-perception/tests/golden/hailo_yolo26_ref.py`, `make_yolo26_golden.py`, `yolo26_golden.json`

**Interfaces:**
- Produces `yolo26_golden.json` (**sparse format, controller Ruling 2 during execution** — a dense base64 encoding of full grids weighed 31 MB): `{"format": "sparse-v1", "cases": [ {"name": str, "in_w": int, "in_h": int, "orig_w": int, "orig_h": int, "lb": [r, px, py] | null, "conf_thresh": float, "iou_thresh": float, "tensors": { "<name>": {"shape": [h, w, c], "dtype": "float32" | "uint16", "zp": float, "scale": float, "fill": raw, "entries": [[y, x, ch, raw], ...] } }, "expected": [[class_id, label, conf, x, y, w, h], ...] }, ... ]}`. `fill` is the raw value of every element not listed in `entries` (float32 tensors: boxes 0.0, classes -50.0; uint16 tensors: the raw code of the quantised fill); entry values are raw units too (the float itself, or the uint16 code). The consumer rebuilds the dense NHWC array from `shape`, `fill` and `entries`. Tensor names carry the board's prefix (`yolo26m/conv71` …). For `uint16` tensors the expected boxes were computed by dequantising the DENSE array in float32 (`(raw.astype(np.float32) - np.float32(zp)) * np.float32(scale)`) before calling the reference; for `float32` tensors the dense data is used as is.

- [ ] **Step 1: Byte-identical reference**

Run: `git show feat/portal-tracking:hosts/pi5/hailo_yolo26.py > services/garuda-perception/tests/golden/hailo_yolo26_ref.py` and verify `git show feat/portal-tracking:hosts/pi5/hailo_yolo26.py | diff - services/garuda-perception/tests/golden/hailo_yolo26_ref.py` prints nothing. (The file imports `target_range` inside a try/except and falls back to a namedtuple — no other dependency than numpy.)

- [ ] **Step 2: The generator**

`services/garuda-perception/tests/golden/make_yolo26_golden.py`:
```python
#!/usr/bin/env python3
"""Synthetic golden for the C++ port of decode_yolo26 (tests/golden/hailo_yolo26_ref.py, byte-identical
to the Pi's decoder). Cases: the Pi's own unit tests (letterbox at 640 and 960, squash resize), plus
per-class NMS, cross-class overlap kept, clamping at the frame edge, and a uint16-quantised variant.
Scores never sit within 1e-3 of a threshold (float32 vs float64 comparisons must not decide a case)."""
import base64, importlib.util, json, pathlib
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
        if quantise:
            # emulate the HEF's UINT16 output: choose zp/scale covering the array's range with margin, round to uint16
            lo, hi = float(arr.min()) - 1.0, float(arr.max()) + 1.0
            scale = np.float32((hi - lo) / 65535.0); zp = np.float32(-lo / float(scale))
            raw = np.clip(np.round(arr / scale + zp), 0, 65535).astype(np.uint16)
            deq = (raw.astype(np.float32) - np.float32(zp)) * np.float32(scale)
            tensors[PREFIX + k] = {"shape": list(arr.shape), "dtype": "uint16", "zp": float(zp), "scale": float(scale), "data_b64": base64.b64encode(raw.tobytes()).decode()}
            outs_for_ref[k] = deq
        else:
            tensors[PREFIX + k] = {"shape": list(arr.shape), "dtype": "float32", "zp": 0.0, "scale": 1.0, "data_b64": base64.b64encode(arr.astype(np.float32).tobytes()).decode()}
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
(here / "yolo26_golden.json").write_text(json.dumps({"cases": cases}, indent=1) + "\n")
print(len(cases), "cases ->", here / "yolo26_golden.json", "expected counts:", [len(c["expected"]) for c in cases])
```
Run: `python3 services/garuda-perception/tests/golden/make_yolo26_golden.py` — Expected: `8 cases -> ... expected counts: [1, 1, 1, 2, 2, 1, 1, 2]` (case 4: person 0.8 + cup; case 7: only the toothbrush at 0.16 survives the 0.15 floor; case 6: one clamped box whose x is 0). If a count differs, the case construction is wrong (not the reference): fix the case, never the reference, and say so in the report. Sanity-check by eye that case 1's expected box is `(100, 100, 400, 200)` ±1e-3 and case 6's x is exactly 0.0.

- [ ] **Step 3: Commit** — `test(perception): yolo26 decoder parity reference (byte-identical Pi decoder) + synthetic golden (8 cases incl. NMS, clamping, uint16)`.

---

### Task 2: The decode port in the core library, golden-tested

**Files:**
- Create: `include/garuda/yolo26_decode.hpp`, `src/yolo26_decode.cpp`, `tests/test_yolo26_decode.cpp`
- Modify: `services/garuda-perception/CMakeLists.txt` (add `src/yolo26_decode.cpp` to the core sources), `tests/CMakeLists.txt`

**Interfaces:**
- Produces:
  ```cpp
  namespace garuda::yolo26 {
  struct TensorView { const void* data; int h, w, c; bool is_u16; float zp, scale; };  // NHWC; element (row,col,ch) at ((w*c)*row + c*col + ch); value = is_u16 ? (float(raw)-zp)*scale : float
  struct Params { float conf_thresh = 0.3f; float iou_thresh = 0.5f; int in_w = 640, in_h = 640; };
  struct Letterbox { double r_x, r_y, px, py; };                                        // Python: lb=None -> r_x=in_w/orig_w, r_y=in_h/orig_h, px=py=0
  struct RawDet { int class_id; float conf; double x1, y1, x2, y2; };                   // original-image pixels, clamped to [0,orig]
  Letterbox letterbox_for(int in_w, int in_h, int orig_w, int orig_h);                  // HailoYolo26.infer's r/px/py (integer // for the pads)
  Letterbox squash_for(int in_w, int in_h, int orig_w, int orig_h);                     // the lb=None branch
  // box[i], cls[i] for strides {8,16,32} in that order (Python PAIRS order)
  std::vector<RawDet> decode(const TensorView box[3], const TensorView cls[3], const Params& p, int orig_w, int orig_h, const Letterbox& lb);
  extern const char* const COCO[80];
  constexpr int STRIDES[3] = {8, 16, 32};
  }
  ```

- [ ] **Step 1: Write the failing test** — `tests/test_yolo26_decode.cpp`: loads `yolo26_golden.json` (path from argv; assert `format == "sparse-v1"`), for each case rebuilds the six dense NHWC tensors from the sparse form (allocate `h*w*c` elements of the dtype, set every element to `fill`, then apply each `[y, x, ch, raw]` entry at index `(w*c)*y + c*x + ch`; keep the buffers alive for the decode call), builds the `TensorView`s (float32 → `is_u16=false`, uint16 → `is_u16=true` with zp/scale), builds `Params{conf_thresh, iou_thresh, in_w, in_h}`, `Letterbox` from `lb` (null → `squash_for`), calls `decode`, and asserts: same count; per detection in order: `class_id` equal, `label == COCO[class_id]` equals the golden label, `fabs(conf - exp) < 1e-5`, `fabs(x1 - ex) < 1e-3`, same for y and for `x2-x1` vs `w`, `y2-y1` vs `h`. Print `yolo26 decode golden ok (<n> cases)`. Register `add_test(NAME yolo26_decode COMMAND test_yolo26_decode ${CMAKE_CURRENT_SOURCE_DIR}/golden/yolo26_golden.json)`.
- [ ] **Step 2: Run to verify it fails** — missing header.
- [ ] **Step 3: Implement**

`src/yolo26_decode.cpp` (comments cite the Python line each block mirrors):
```cpp
#include "garuda/yolo26_decode.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
namespace garuda::yolo26 {
const char* const COCO[80] = { "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat","traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","couch","potted plant","bed","dining table","toilet","tv","laptop","mouse","remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush" };
static inline float at(const TensorView& t, int row, int col, int ch) {            // NHWC, HailoTensor::get() layout
    size_t pos = (size_t)(t.w * t.c) * row + (size_t)t.c * col + ch;
    if (t.is_u16) return (float(((const uint16_t*)t.data)[pos]) - t.zp) * t.scale; // fix_scale: (num - zp) * scale, float32
    return ((const float*)t.data)[pos];
}
static inline float sigmoid32(float x) { return 1.0f / (1.0f + std::exp(-x)); }     // _sigmoid on a float32 element
static double iou(const RawDet& a, const RawDet& b) {                                // _iou (x1,y1,x2,y2), doubles
    double xa = std::max(a.x1, b.x1), ya = std::max(a.y1, b.y1), xb = std::min(a.x2, b.x2), yb = std::min(a.y2, b.y2);
    double inter = std::max(0.0, xb - xa) * std::max(0.0, yb - ya);
    double ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
    return ua > 0 ? inter / ua : 0.0;
}
Letterbox letterbox_for(int in_w, int in_h, int orig_w, int orig_h) {                // HailoYolo26.infer
    double r = std::min((double)in_w / orig_w, (double)in_h / orig_h);
    long nw = std::lround(orig_w * r), nh = std::lround(orig_h * r);                 // Python round() is banker's; lround is not — equal for non-.5 values, which our geometries are (see test)
    return {r, r, (double)((in_w - nw) / 2), (double)((in_h - nh) / 2)};
}
Letterbox squash_for(int in_w, int in_h, int orig_w, int orig_h) { return {(double)in_w / orig_w, (double)in_h / orig_h, 0.0, 0.0}; }
std::vector<RawDet> decode(const TensorView box[3], const TensorView cls[3], const Params& p, int orig_w, int orig_h, const Letterbox& lb) {
    std::vector<RawDet> raw;
    for (int s = 0; s < 3; ++s) {                                                    // for bsfx, csfx, stride in PAIRS
        const int stride = STRIDES[s]; const TensorView& B = box[s]; const TensorView& C = cls[s];
        for (int y = 0; y < C.h; ++y) for (int x = 0; x < C.w; ++x) {               // np.where over (h, w): row-major
            int cid = 0; float best = at(C, y, x, 0);
            for (int k = 1; k < C.c; ++k) { float v = at(C, y, x, k); if (v > best) { best = v; cid = k; } }   // argmax keeps the FIRST max
            float cf = sigmoid32(best);                                              // sc.max(-1) == sigmoid(max logit): sigmoid is monotonic
            if (!(cf > p.conf_thresh)) continue;                                     // cf > conf_thresh
            double l = at(B, y, x, 0), t = at(B, y, x, 1), r = at(B, y, x, 2), b = at(B, y, x, 3);
            double cx = (x + 0.5) * stride, cy = (y + 0.5) * stride;
            RawDet d; d.class_id = cid; d.conf = cf;
            d.x1 = std::min(std::max(((cx - l * stride) - lb.px) / lb.r_x, 0.0), (double)orig_w);
            d.y1 = std::min(std::max(((cy - t * stride) - lb.py) / lb.r_y, 0.0), (double)orig_h);
            d.x2 = std::min(std::max(((cx + r * stride) - lb.px) / lb.r_x, 0.0), (double)orig_w);
            d.y2 = std::min(std::max(((cy + b * stride) - lb.py) / lb.r_y, 0.0), (double)orig_h);
            raw.push_back(d);
        }
    }
    std::stable_sort(raw.begin(), raw.end(), [](const RawDet& a, const RawDet& b) { return a.conf > b.conf; });   // raw.sort(key=-conf), stable
    std::vector<RawDet> keep;
    for (const auto& d : raw) {
        bool ok = true;
        for (const auto& k : keep) if (d.class_id == k.class_id && iou(d, k) > p.iou_thresh) { ok = false; break; }
        if (ok) keep.push_back(d);
    }
    return keep;
}
}
```
Note on the float32 threshold comparison: numpy compares the float32 `cf` with the Python float `conf_thresh`; the golden avoids scores within 1e-3 of a threshold so this cannot decide a case. Note on `round`: the Python `round()` is banker's rounding; `lround` rounds half away from zero; add a unit assertion in the test that `letterbox_for(640,640,1280,720)` gives `(0.5, 0.5, 0, 140)` and `letterbox_for(960,960,1280,720)` gives `(0.75, 0.75, 0, 210)` (the Pi's test values) — no .5 case arises for these frames.

- [ ] **Step 4: Build + run** — `cmake --build build-x86 -j4 && ctest --test-dir build-x86 --output-on-failure`: 7/7, `yolo26 decode golden ok (8 cases)`, zero warnings.
- [ ] **Step 5: Commit** — `feat(perception): yolo26 decode ported from hosts/pi5/hailo_yolo26.py into the core library, golden-tested (float32 + uint16)`.

---

### Task 3: The post-process plugin (cross-build only)

**Files:**
- Create: `services/garuda-perception/postprocess/yolo26_post.cpp`, `postprocess/CMakeLists.txt`, `config/yolo26_post.json`
- Modify: `services/garuda-perception/CMakeLists.txt` (`add_subdirectory(postprocess)` inside `if(GARUDA_BUILD_NODE)`)

**Interfaces:**
- Produces `libyolo26_post.so` exporting, with C linkage exactly as Hailo's stock plugin header declares them (`__BEGIN_DECLS` … `__END_DECLS`, C++ types in the signatures are fine — only the symbol names must be unmangled):
  ```cpp
  Yolo26Params* init(const std::string config_path, const std::string function_name);   // parses the JSON config; returns heap params
  void free_resources(void* params_void_ptr);                                          // deletes them
  void filter(HailoROIPtr roi, void* params_void_ptr);                                 // the post stage's default function name
  ```
- Config `config/yolo26_post.json`:
  ```json
  { "conf_thresh": 0.15, "iou_thresh": 0.5, "in_w": 640, "in_h": 640, "frame_w": 1280, "frame_h": 720,
    "mode": "letterbox", "tensor_prefix": "yolo26m/",
    "box_tensors": ["conv71", "conv87", "conv101"], "cls_tensors": ["conv74", "conv90", "conv104"],
    "labels": ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"],
    "dump": { "path": "", "frames": 0 } }
  ```
  `labels` must equal `garuda::yolo26::COCO` (init() verifies the 80 entries and refuses to start otherwise — one wrong label would silently break the portal's class names). `mode` is `"letterbox"` (→ `letterbox_for`) or `"stretch"` (→ `squash_for`).

- [ ] **Step 1: The plugin**

`postprocess/yolo26_post.cpp`:
```cpp
// libyolo26_post.so — post-process plugin for the Hailo model-zoo yolo26m (six raw heads, no baked NMS).
// Runs in the pipeline's post stage thread; decodes with garuda::yolo26 (the Pi decoder's port) and attaches
// HailoDetections with boxes normalised to the FRAME (already un-letterboxed), so the node's det_sink keeps
// its xmin*frame_w mapping. LICENCE: model weights are Ultralytics YOLO26 (AGPL-3.0, bench/eval only).
#include "garuda/yolo26_decode.hpp"
#include "hailo_postprocess_tools/objects/hailo_objects.hpp"
#include "hailo_postprocess_tools/objects/hailo_tensors.hpp"
#include "hailo_postprocess_tools/objects/hailo_common.hpp"
#include <nlohmann/json.hpp>
#include <cstdio>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

struct Yolo26Params {
    garuda::yolo26::Params p; int frame_w = 1280, frame_h = 720; bool letterbox = true; std::string prefix;
    std::string box_names[3], cls_names[3]; std::vector<std::string> labels;
    std::string dump_path; int dump_frames = 0, dumped = 0; bool dump_failed = false;
};

__BEGIN_DECLS
Yolo26Params* init(const std::string config_path, const std::string function_name) {
    (void)function_name;
    auto* q = new Yolo26Params();
    std::ifstream f(config_path); if (!f) { std::fprintf(stderr, "yolo26_post: cannot read %s\n", config_path.c_str()); delete q; return nullptr; }
    nlohmann::json c = nlohmann::json::parse(f);
    q->p.conf_thresh = c.value("conf_thresh", 0.15); q->p.iou_thresh = c.value("iou_thresh", 0.5);
    q->p.in_w = c.value("in_w", 640); q->p.in_h = c.value("in_h", 640);
    q->frame_w = c.value("frame_w", 1280); q->frame_h = c.value("frame_h", 720);
    q->letterbox = c.value("mode", std::string("letterbox")) == "letterbox";
    q->prefix = c.value("tensor_prefix", std::string("yolo26m/"));
    auto bn = c.value("box_tensors", std::vector<std::string>{"conv71", "conv87", "conv101"});
    auto cn = c.value("cls_tensors", std::vector<std::string>{"conv74", "conv90", "conv104"});
    for (int i = 0; i < 3; ++i) { q->box_names[i] = q->prefix + bn.at(i); q->cls_names[i] = q->prefix + cn.at(i); }
    q->labels = c.value("labels", std::vector<std::string>{});
    if (q->labels.size() != 80) { std::fprintf(stderr, "yolo26_post: labels must have 80 entries (got %zu)\n", q->labels.size()); delete q; return nullptr; }
    for (int i = 0; i < 80; ++i) if (q->labels[i] != garuda::yolo26::COCO[i]) { std::fprintf(stderr, "yolo26_post: label %d is '%s', expected '%s'\n", i, q->labels[i].c_str(), garuda::yolo26::COCO[i]); delete q; return nullptr; }
    auto d = c.value("dump", nlohmann::json::object()); q->dump_path = d.value("path", std::string("")); q->dump_frames = d.value("frames", 0);
    std::fprintf(stderr, "yolo26_post: conf=%.3f iou=%.2f net=%dx%d frame=%dx%d mode=%s prefix=%s dump=%s/%d\n", q->p.conf_thresh, q->p.iou_thresh, q->p.in_w, q->p.in_h, q->frame_w, q->frame_h, q->letterbox ? "letterbox" : "stretch", q->prefix.c_str(), q->dump_path.c_str(), q->dump_frames);
    return q;
}
void free_resources(void* params_void_ptr) { delete reinterpret_cast<Yolo26Params*>(params_void_ptr); }

static bool view_of(HailoROIPtr roi, const std::string& name, garuda::yolo26::TensorView& v) {
    HailoTensorPtr t = roi->get_tensor(name); if (!t) return false;
    v.data = t->data(); v.h = (int)t->height(); v.w = (int)t->width(); v.c = (int)t->features();
    v.is_u16 = t->is_uint16(); v.zp = t->qp_zp(); v.scale = t->qp_scale(); return true;
}
static void dump_frame(Yolo26Params* q, HailoROIPtr roi, const garuda::yolo26::TensorView box[3], const garuda::yolo26::TensorView cls[3]) {
    // One file per frame: <path>.<n>.bin = the six tensors' raw bytes back to back (box0,box1,box2,cls0,cls1,cls2);
    // <path>.<n>.json = names/shapes/dtype/zp/scale in the same order (Task 5 reads both).
    char nb[512]; std::snprintf(nb, sizeof nb, "%s.%d.bin", q->dump_path.c_str(), q->dumped); std::ofstream b(nb, std::ios::binary);
    nlohmann::json hdr = nlohmann::json::array();
    const garuda::yolo26::TensorView* all[6] = {&box[0], &box[1], &box[2], &cls[0], &cls[1], &cls[2]};
    const std::string* names[6] = {&q->box_names[0], &q->box_names[1], &q->box_names[2], &q->cls_names[0], &q->cls_names[1], &q->cls_names[2]};
    for (int i = 0; i < 6; ++i) {
        size_t n = (size_t)all[i]->h * all[i]->w * all[i]->c * (all[i]->is_u16 ? 2 : 4);
        b.write((const char*)all[i]->data, (std::streamsize)n);
        hdr.push_back({{"name", *names[i]}, {"shape", {all[i]->h, all[i]->w, all[i]->c}}, {"dtype", all[i]->is_u16 ? "uint16" : "float32"}, {"zp", all[i]->zp}, {"scale", all[i]->scale}, {"bytes", n}});
    }
    if (!b.good()) { q->dump_failed = true; std::fprintf(stderr, "yolo26_post: dump write failed at frame %d, disabling\n", q->dumped); return; }
    char nj[512]; std::snprintf(nj, sizeof nj, "%s.%d.json", q->dump_path.c_str(), q->dumped); std::ofstream(nj) << hdr.dump(1) << "\n";
    (void)roi; if (++q->dumped >= q->dump_frames) std::fprintf(stderr, "yolo26_post: dumped %d frames to %s.*\n", q->dumped, q->dump_path.c_str());
}
void filter(HailoROIPtr roi, void* params_void_ptr) {
    auto* q = reinterpret_cast<Yolo26Params*>(params_void_ptr);
    if (!q || !roi->has_tensors()) return;
    garuda::yolo26::TensorView box[3], cls[3];
    for (int i = 0; i < 3; ++i) if (!view_of(roi, q->box_names[i], box[i]) || !view_of(roi, q->cls_names[i], cls[i])) {
        static bool warned = false; if (!warned) { warned = true; std::fprintf(stderr, "yolo26_post: tensor %s or %s missing on the ROI\n", q->box_names[i].c_str(), q->cls_names[i].c_str()); } return;
    }
    if (!q->dump_path.empty() && q->dumped < q->dump_frames && !q->dump_failed) dump_frame(q, roi, box, cls);
    auto lb = q->letterbox ? garuda::yolo26::letterbox_for(q->p.in_w, q->p.in_h, q->frame_w, q->frame_h) : garuda::yolo26::squash_for(q->p.in_w, q->p.in_h, q->frame_w, q->frame_h);
    auto dets = garuda::yolo26::decode(box, cls, q->p, q->frame_w, q->frame_h, lb);
    std::vector<HailoDetection> out; out.reserve(dets.size());
    for (const auto& d : dets) {   // normalised to the FRAME: det_sink multiplies by frame_w/frame_h
        HailoBBox bb((float)(d.x1 / q->frame_w), (float)(d.y1 / q->frame_h), (float)((d.x2 - d.x1) / q->frame_w), (float)((d.y2 - d.y1) / q->frame_h));
        out.emplace_back(bb, d.class_id, q->labels[d.class_id], d.conf);
    }
    hailo_common::add_detections(roi, out);
}
__END_DECLS
```
Check the exact include paths and the `HailoTensor` accessor names against the SDK headers under `$OECORE_TARGET_SYSROOT/usr/include/hailo/hailo_postprocess_tools/objects/` (`hailo_tensors.hpp`: `data()`, `width()`, `height()`, `features()`, `qp_zp()`, `qp_scale()`, `is_uint16()`; `hailo_objects.hpp`: `HailoBBox(xmin, ymin, width, height)`, `HailoDetection(HailoBBox, int class_id, const std::string& label, float confidence)`, `HailoROI::get_tensor(name)`, `has_tensors()`; `hailo_common.hpp`: `add_detections(HailoROIPtr, std::vector<HailoDetection>)`). If a name differs, use the header's name and note it in the report.

`postprocess/CMakeLists.txt`:
```cmake
# The plugin needs the Hailo headers and libhailo_postprocess_tools from the board SDK: cross-build only.
add_library(yolo26_post SHARED yolo26_post.cpp)
target_compile_options(yolo26_post PRIVATE -Wall -Wextra -ffp-contract=off)
target_include_directories(yolo26_post PRIVATE ${GARUDA_HAILO_INCLUDE})
target_link_libraries(yolo26_post PRIVATE garuda_perception_core hailo_postprocess_tools)
set_target_properties(yolo26_post PROPERTIES OUTPUT_NAME yolo26_post)
install(TARGETS yolo26_post LIBRARY DESTINATION lib)
```
The core library is STATIC and linked into a SHARED object: add `set_target_properties(garuda_perception_core PROPERTIES POSITION_INDEPENDENT_CODE ON)` in the top-level CMakeLists (harmless for the executables). Add `add_subdirectory(postprocess)` inside the `if(GARUDA_BUILD_NODE)` block.

- [ ] **Step 2: Cross-build** — zero `warning:` lines; `file services/garuda-perception/build-h15l/postprocess/libyolo26_post.so` → `ELF 64-bit LSB shared object, ARM aarch64`; `nm -D … | grep -E " T (init|filter|free_resources)$"` shows the three unmangled symbols (use the SDK's `aarch64-poky-linux-nm` from the sourced env). Native build + ctest unaffected (7/7).
- [ ] **Step 3: Commit** — `feat(perception): libyolo26_post.so — post-process plugin for the six-head yolo26m HEF (dequantise, Pi-parity decode, frame-normalised detections, tensor dump)`.

---

### Task 4: Profile, config, deploy, node — yolo26m live on the board, with rollback

**Files:**
- Modify: `hosts/hailo15l/medialib/make_profile.py` (sink0), regenerate `hosts/hailo15l/medialib/profile/application_settings.json` + `garuda_medialib_config.json` by running it; `services/garuda-perception/config/perception.json`; create `config/perception-yolov8n.json` (a verbatim copy of the pre-change `perception.json`); `hosts/hailo15l/deploy.sh`; `src/node_main.cpp` (dump geometry from config, comments); `hosts/hailo15l/README.md`

**Interfaces:**
- `perception.json` (yolo26m): `"hef": "/opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef"`, `"postprocess_so": "/opt/garuda/lib/libyolo26_post.so"`, `"postprocess_config": "/opt/garuda/yolo26_post.json"`, plus `"dump_nv12": {"path": "", "frames": 0, "width": 640, "height": 640}` (new width/height keys replace the node's hardcoded 640×384; default 640×640).
- `deploy.sh`: env `GARUDA_PERCEPTION_CONFIG` (default `config/perception.json`; set to `config/perception-yolov8n.json` for rollback) selects which file lands as `/opt/garuda/perception.json`; a models step copies `libyolo26_post.so` → `/opt/garuda/lib/`, `config/yolo26_post.json` → `/opt/garuda/yolo26_post.json`, and the HEF from `/media/bhanu1234/Development/hailo15/models/yolo26m_hailo15l_v5.3.0.hef` → `/opt/garuda/models/` only if the board's copy is missing or its md5 differs (md5 `3aef604ab89ddaf9ecb4cefa9c6ea8af`; run `models/fetch_yolo26m_h15l.sh` first if the PC copy is missing).

- [ ] **Step 1: Profile** — in `make_profile.py` change sink0 to `{"stream_id": "sink0", "width": 640, "height": 640, "framerate": 30, "pool_max_buffers": 20, "scaling_mode": "LETTERBOX_MIDDLE"}` (the media library's schema enum, confirmed from `libmedialib.so`; NOT the `DSP_SCALING_MODE_` C spelling — fix the README line that guessed it); update the `description` strings to "garuda-perception M2"; run `python3 hosts/hailo15l/medialib/make_profile.py` and check `git diff` shows only those changes in the generated JSON.
- [ ] **Step 2: Config + rollback file** — `cp config/perception.json config/perception-yolov8n.json` BEFORE editing; then edit `perception.json` as above. Keep every other key identical.
- [ ] **Step 3: Node** — replace `constexpr int DUMP_SRC_W = 640, DUMP_SRC_H = 384;` by values read from `dump_cfg` (`width`/`height`, defaults 640/640) and use them in the guard/loops/warning; update the det_sink comment at the `xmin*FW` line: "the post-process plugin already un-letterboxed and normalised to the frame (yolo26_post.json frame_w/h must equal frame_w/h here); the stock yolov8n path is a STRETCH of the same FOV — both map by simple multiplication"; update the comment near `set_nms_score_threshold`: "no effect on the yolo26m HEF (no baked NMS; the plugin applies conf_thresh); kept for the stock HEF". Native ctest stays 7/7; cross-build zero warnings.
- [ ] **Step 4: deploy.sh** — add, after the existing `mkdir` line: `/opt/garuda/models` to the mkdir list; the config selection (`CFG="${GARUDA_PERCEPTION_CONFIG:-$SVC/config/perception.json}"` used by the existing `scp` of perception.json — it must land as `/opt/garuda/perception.json` whatever its source name: `scp -q "$CFG" "$HOST:/opt/garuda/perception.json"`); copy `$SVC/build-h15l/postprocess/libyolo26_post.so` → `/opt/garuda/lib/` and `$SVC/config/yolo26_post.json` → `/opt/garuda/yolo26_post.json`; the HEF step with the md5 guard (`ssh "$HOST" 'md5sum /opt/garuda/models/yolo26m_hailo15l_v5.3.0.hef 2>/dev/null | cut -c1-32'` compared on the PC side; scp only on mismatch). Keep the script idempotent and `--no-restart` working.
- [ ] **Step 5: Deploy yolo26m and verify** — `hosts/hailo15l/deploy.sh`; then on the board: `tail -20 /var/log/garuda-perception.log` must show the plugin's `yolo26_post: conf=0.150 …` init line and `frames=` lines; `curl -s http://10.0.0.1:8098/api/state | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['lock'], [(t['id'],t['label'],round(t['conf'],2)) for t in d['tracks']])"` several times over a minute. The bench scene (chair, suitcases, books, a ring light, the owner if present) should yield COCO labels other than person/face — paste what appears verbatim; if NOTHING is detected for a minute, do not tune thresholds: dump one letterboxed sink0 frame with `dump_nv12` (frames 1, 640×640) and one tensor dump (`yolo26_post.json` dump frames 1), copy both to the PC, and report BLOCKED with them (Task 5's golden path will show whether the decode or the input is wrong). Also record the letterbox pad colour: from the NV12 dump, the Y value of row 0 and row 639 (padding rows) vs the Pi's 114 — paste the numbers.
- [ ] **Step 6: Rollback check** — `GARUDA_PERCEPTION_CONFIG=services/garuda-perception/config/perception-yolov8n.json hosts/hailo15l/deploy.sh`, confirm the stock detector is back (`face`/`person` labels only, log shows the stock post-process), then `hosts/hailo15l/deploy.sh` again to return to yolo26m and confirm. Paste both.
- [ ] **Step 7: README** — new section "yolo26m on the board (M2)": what runs, the config switch, the rollback command, the pad-colour observation, and "What changes for a portal user vs M1" (COCO-80 labels; the class dropdown works; the tracker's low band is live because the plugin floors at 0.15). Fix the `DSP_SCALING_MODE_` guess. No numbers except pasted outputs.
- [ ] **Step 8: Commit** — `feat(hailo15l): yolo26m live on the SBC — letterboxed 640x640 profile, plugin config, deploy models step + GARUDA_PERCEPTION_CONFIG rollback, node dump geometry from config`.

---

### Task 5: Real-tensor golden (the dequantisation proof)

**Files:**
- Create: `tests/golden/make_yolo26_real_golden.py`, `tests/golden/yolo26_real_frame.bin`, `tests/golden/yolo26_real_frame.json`, `tests/test_yolo26_real.cpp`
- Modify: `tests/CMakeLists.txt`

**Interfaces:**
- `yolo26_real_frame.json`: `{"tensors": [ {"name", "shape", "dtype", "zp", "scale", "bytes"} ×6 in file order ], "conf_thresh": 0.15, "iou_thresh": 0.5, "in_w": 640, "in_h": 640, "frame_w": 1280, "frame_h": 720, "lb": [r, px, py], "expected": [[class_id, label, conf, x, y, w, h], ...]}`; `yolo26_real_frame.bin` = the six tensors' raw bytes back to back exactly as the plugin dumped them.

- [ ] **Step 1: Capture on the board** — edit `/opt/garuda/yolo26_post.json` on the board only: `"dump": {"path": "/opt/garuda/state/y26dump", "frames": 3}`; restart the service; wait for `yolo26_post: dumped 3 frames` in the log; `scp` `y26dump.*.bin/json` to the scratchpad; restore the board config by re-running `hosts/hailo15l/deploy.sh` (copies the committed config) and confirm health. Pick the frame with the most detections in the node's snapshot at that time (or frame 0), copy its `.bin` to `tests/golden/yolo26_real_frame.bin` (about 1.4 MB: (6400+1600+400)×84×2 bytes) and its `.json` header into the golden json's `tensors` array.
- [ ] **Step 2: Python golden** — `make_yolo26_real_golden.py`: reads the header + bin, splits the six tensors, dequantises `uint16` in float32 as in Task 1, builds `outs` keyed by the Python's suffixes (`conv71` …, prefix stripped), computes `lb` with the same formula as `letterbox_for`, calls `ref.decode_yolo26(outs, 1280, 720, "", 0.15, 0.5, lb)`, writes `expected` + all parameters into `yolo26_real_frame.json`. Print the detections (label, conf, box) — they should look like the scene (chair, suitcase, person, …); paste them in the report.
- [ ] **Step 3: C++ test** — `test_yolo26_real.cpp`: loads the json + bin, builds the six `TensorView`s from the header, decodes with `Params{0.15, 0.5, 640, 640}` and `letterbox_for(640,640,1280,720)`, asserts the same count and per-detection class/label, conf ±1e-5, pixels ±1e-3. Register `add_test(NAME yolo26_real COMMAND test_yolo26_real ${CMAKE_CURRENT_SOURCE_DIR}/golden/yolo26_real_frame.json ${CMAKE_CURRENT_SOURCE_DIR}/golden/yolo26_real_frame.bin)`. 8/8 green.
- [ ] **Step 4: Commit** — `test(perception): real-frame yolo26 golden — six raw UINT16 tensors dumped on the SBC, decoded by the Pi's Python, matched by the C++ port`.

---

### Task 6: Bench and record

- [ ] **Step 1:** 10-minute run on the deployed yolo26m node, the same procedure and commands as the M1 section of `bench/benchlog.md` (conditions block with `md5sum` of the binary and the HEF, `frames=` lines for the window, three `top -b -n 3 -d 5` samples with the corrected pattern, thermal/`free`/`uptime` at start/mid/end, SSE capture + tally: distinct labels seen, frames with non-empty tracks, distinct `lock.id`). If the owner is present, include the person walk-in/out routine and record it as in the coast-window addendum (`bench/evidence/2026-09-03-m1-coast-window-scripts/`); otherwise state the scene. New section `## 2026-09-0x — Hailo-15L SBC: M2 yolo26m detector` at the end of the benchlog, numbers verbatim, comparison rows quoting the M1 section and the zoo-HEF section (`yolo26m: FPS: 25.97` NPU-only) by line reference, red-team paragraph (post stage CPU cost now includes the decode; 17-context HEF; warm board; detections depend on the scene; low band now live so the tracker sees more boxes than in M1).
- [ ] **Step 2:** `bench/versions.md` sub-entry (node commit, HEF md5, plugin), `docs/decisions.md` entry (what M2 taught: plugin ABI with C linkage, tensors UINT16 with zp/scale, letterbox enum, pad colour observation, anything that bit), `CLAUDE.md` §7 one line, `models/yolo26m_h15l.md` "Integration" → done with the commit, the README threshold note → "low band live since M2".
- [ ] **Step 3: Commit** — `bench(hailo15l): M2 yolo26m detector run`.

---

### Task 7: Spec status and hand-off

- [ ] **Step 1:** Spec changelog line (dated): M2 implemented; §8 item 3 gets a one-line status pointer to the benchlog section; §7 testing gains the two yolo26 goldens. `hosts/hailo15l/README.md` "Pending owner presence" list updated for anything the M2 run covered.
- [ ] **Step 2: Commit** — `docs: spec status after M2`. (The controller updates the memory file.)

---

## Self-review

- **Spec coverage:** §8 item 3 — zoo HEF (constraints), own plugin (T3), Pi decode port + letterbox (T2/T4), score floor 0.15 (config), COCO names (T3 verifies), parity incl. real-tensor golden (T1/T2/T5), deploy models step + rollback (T4), bench vs M1 with the NPU ceiling (T6), out-of-scope list respected. §7 testing: goldens in ctest. §5 gate: T6.
- **Placeholders:** none; every step has its content; the only conditional branches (nothing detected in T4 Step 5 → BLOCKED with dumps; header name differences in T3) are explicit.
- **Type consistency:** `TensorView{data,h,w,c,is_u16,zp,scale}`, `Params{conf_thresh,iou_thresh,in_w,in_h}`, `Letterbox{r_x,r_y,px,py}`, `RawDet{class_id,conf,x1,y1,x2,y2}`, `decode(box[3], cls[3], Params, orig_w, orig_h, Letterbox)`, `letterbox_for/squash_for(in_w,in_h,orig_w,orig_h)` used identically in T2, T3, T5; golden JSON field names identical between T1's generator and T2's test, and between T3's dump header and T5's golden.
