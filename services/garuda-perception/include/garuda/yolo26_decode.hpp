#pragma once
#include <vector>

// Port of the Pi's YOLO26 decode (hosts/pi5/hailo_yolo26.py: decode_yolo26 / HailoYolo26.infer),
// pinned by the parity oracle at tests/golden/hailo_yolo26_ref.py (byte-identical to the Pi's
// decoder) and the synthetic golden at tests/golden/yolo26_golden.json (tests/golden/make_yolo26_golden.py).
// YOLO26 is NMS-free/DFL-free: the HEF emits 6 raw multi-scale tensors — 3 box heads (ltrb distances,
// H*W*4) and 3 class heads (logits, H*W*80) at strides 8/16/32 — decoded here (anchor-free ltrb*stride,
// sigmoid on class, light per-class NMS). Comments in the .cpp cite the Python line each block mirrors.
namespace garuda {
namespace yolo26 {

// One raw model output tensor, NHWC. element (row,col,ch) lives at index ((w*c)*row + c*col + ch).
// value = is_u16 ? (float(raw) - zp) * scale : the float32 value directly (fix_scale dequant, float32).
struct TensorView {
    const void* data;
    int h, w, c;
    bool is_u16;
    float zp, scale;
};

struct Params {
    float conf_thresh = 0.3f;
    float iou_thresh = 0.5f;
    int in_w = 640, in_h = 640;
};

// r_x/r_y: input-pixels-per-original-pixel scale; px/py: letterbox pad (input-space pixels).
// lb=None in the Python reference -> r_x=in_w/orig_w, r_y=in_h/orig_h, px=py=0 (squash resize).
struct Letterbox {
    double r_x, r_y, px, py;
};

// A decoded, NMS'd detection in original-image pixels, clamped to [0, orig_w]/[0, orig_h].
struct RawDet {
    int class_id;
    float conf;
    double x1, y1, x2, y2;
};

// HailoYolo26.infer's letterbox geometry: fit orig into in_w x in_h preserving aspect, centre-pad.
// Python uses round()/// (banker's rounding + floor div); no .5 case arises for real camera frames.
Letterbox letterbox_for(int in_w, int in_h, int orig_w, int orig_h);

// decode_yolo26's lb=None branch: plain non-aspect-preserving squash resize, no padding.
Letterbox squash_for(int in_w, int in_h, int orig_w, int orig_h);

// box[i]/cls[i] are the box/class tensors for STRIDES[i] (strides 8, 16, 32 — Python PAIRS order).
// Returns detections sorted by descending confidence, after per-class greedy NMS.
std::vector<RawDet> decode(const TensorView box[3], const TensorView cls[3], const Params& p,
                            int orig_w, int orig_h, const Letterbox& lb);

extern const char* const COCO[80];
constexpr int STRIDES[3] = {8, 16, 32};

} // namespace yolo26
} // namespace garuda
