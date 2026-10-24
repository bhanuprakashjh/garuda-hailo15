#include "garuda/yolo26_decode.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>

// Comments cite lines in tests/golden/hailo_yolo26_ref.py (the parity oracle, byte-identical to the
// Pi's hosts/pi5/hailo_yolo26.py).
namespace garuda {
namespace yolo26 {

const char* const COCO[80] = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
};

// NHWC element lookup + dequant. is_u16: fix_scale dequant, (raw - zp) * scale, computed in float32
// (matches make_yolo26_golden.py's quantise path: raw.astype(float32) - float32(zp), * float32(scale)).
static inline float at(const TensorView& t, int row, int col, int ch) {
    size_t pos = (size_t)(t.w * t.c) * (size_t)row + (size_t)t.c * (size_t)col + (size_t)ch;
    if (t.is_u16) return (float(((const uint16_t*)t.data)[pos]) - t.zp) * t.scale;
    return ((const float*)t.data)[pos];
}

// _sigmoid applied to a single float32 element (the max class logit — see decode()'s comment below
// for why this is equivalent to numpy's elementwise sigmoid-then-max).
static inline float sigmoid32(float x) { return 1.0f / (1.0f + std::exp(-x)); }

// _iou: (x1,y1,x2,y2) boxes, all arithmetic in double.
static double iou(const RawDet& a, const RawDet& b) {
    double xa = std::max(a.x1, b.x1), ya = std::max(a.y1, b.y1);
    double xb = std::min(a.x2, b.x2), yb = std::min(a.y2, b.y2);
    double inter = std::max(0.0, xb - xa) * std::max(0.0, yb - ya);
    double ua = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
    return ua > 0.0 ? inter / ua : 0.0;
}

// HailoYolo26.infer: r = min(in_w/w, in_h/h); nw,nh = round(w*r), round(h*r); px,py = (in_w-nw)//2, (in_h-nh)//2.
// Python round() is banker's rounding; std::lround rounds half-away-from-zero — they agree for every
// non-.5 fractional value, which is the only case real camera geometries produce (see the two unit
// assertions in tests/test_yolo26_decode.cpp). (in_w - nw) is non-negative by construction of r, so
// integer division here (truncation toward zero) is equivalent to Python's floor division (//).
Letterbox letterbox_for(int in_w, int in_h, int orig_w, int orig_h) {
    double r = std::min((double)in_w / orig_w, (double)in_h / orig_h);
    long nw = std::lround(orig_w * r), nh = std::lround(orig_h * r);
    return {r, r, (double)((in_w - nw) / 2), (double)((in_h - nh) / 2)};
}

// decode_yolo26's lb=None branch: r_x = in_w/orig_w, r_y = in_h/orig_h, px = py = 0.
Letterbox squash_for(int in_w, int in_h, int orig_w, int orig_h) {
    return {(double)in_w / orig_w, (double)in_h / orig_h, 0.0, 0.0};
}

std::vector<RawDet> decode(const TensorView box[3], const TensorView cls[3], const Params& p,
                            int orig_w, int orig_h, const Letterbox& lb) {
    std::vector<RawDet> raw;
    for (int s = 0; s < 3; ++s) { // for bsfx, csfx, stride in PAIRS
        const int stride = STRIDES[s];
        const TensorView& B = box[s];
        const TensorView& C = cls[s];
        for (int y = 0; y < C.h; ++y) {
            for (int x = 0; x < C.w; ++x) { // np.where over (h, w): row-major, matches iteration order
                int cid = 0;
                float best = at(C, y, x, 0);
                for (int k = 1; k < C.c; ++k) { // argmax keeps the FIRST max (strict '>', ties don't overwrite)
                    float v = at(C, y, x, k);
                    if (v > best) { best = v; cid = k; }
                }
                // sc.max(-1) == sigmoid(max logit): the VALUE identity holds because sigmoid is
                // monotonic increasing, so whichever logit is largest also has the largest sigmoid.
                // The INDEX this loop picks (cid, the argmax) can still disagree with numpy's
                // sc.argmax(-1) in one edge case: sigmoid saturates in float32 once its input is
                // large enough (roughly |logit| >~ 11) that two distinct logits round to the exact
                // same float32 sigmoid value; numpy's argmax over the post-sigmoid array then returns
                // the LOWEST-indexed tied class, while this loop's argmax runs over the pre-sigmoid
                // logits and (by the strict '>' above) keeps the FIRST logit it saw as strictly
                // greater — which, since sigmoid is monotonic and the pre-image logits are NOT tied
                // (only their sigmoids saturate to the same float32 value), is the HIGHEST-logit
                // class, not necessarily numpy's lowest-tied-index choice. Not observed on the real
                // bench frame (tests/golden/yolo26_real_frame.json): its max class logit is 3.34, far
                // below the ~11 saturation threshold, so no code change — flagged here only so a
                // future high-confidence frame near saturation isn't a surprise.
                float cf = sigmoid32(best);
                if (!(cf > p.conf_thresh)) continue; // cf > conf_thresh
                double l = at(B, y, x, 0), t = at(B, y, x, 1), r = at(B, y, x, 2), b = at(B, y, x, 3);
                double cx = (x + 0.5) * stride, cy = (y + 0.5) * stride;
                RawDet d;
                d.class_id = cid;
                d.conf = cf;
                d.x1 = std::min(std::max(((cx - l * stride) - lb.px) / lb.r_x, 0.0), (double)orig_w);
                d.y1 = std::min(std::max(((cy - t * stride) - lb.py) / lb.r_y, 0.0), (double)orig_h);
                d.x2 = std::min(std::max(((cx + r * stride) - lb.px) / lb.r_x, 0.0), (double)orig_w);
                d.y2 = std::min(std::max(((cy + b * stride) - lb.py) / lb.r_y, 0.0), (double)orig_h);
                raw.push_back(d);
            }
        }
    }
    // raw.sort(key=lambda d: -d[1]): descending by conf, stable (ties keep insertion order).
    std::stable_sort(raw.begin(), raw.end(), [](const RawDet& a, const RawDet& b) { return a.conf > b.conf; });
    // Per-class greedy NMS: reject only when IoU strictly exceeds iou_thresh against an already-kept
    // detection of the same class.
    std::vector<RawDet> keep;
    for (const auto& d : raw) {
        bool ok = true;
        for (const auto& k : keep) {
            if (d.class_id == k.class_id && iou(d, k) > p.iou_thresh) { ok = false; break; }
        }
        if (ok) keep.push_back(d);
    }
    return keep;
}

} // namespace yolo26
} // namespace garuda
