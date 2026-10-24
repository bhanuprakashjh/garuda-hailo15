#pragma once
// Shared scaffolding for the yolo26 golden-replay tests (test_yolo26_decode.cpp's synthetic golden
// and test_yolo26_real.cpp's real-hardware-tensor golden): the fixed name<->stride correspondence
// both goldens (and the plugin, postprocess/yolo26_post.cpp's box_tensors/cls_tensors default) use,
// a helper to strip a "prefix/" off a vstream name, and the per-detection comparison + mismatch
// print both files previously duplicated verbatim. Behaviour is unchanged from the pre-extraction
// copies in each test file — this only removes the duplication.
#include "garuda/yolo26_decode.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <string>

namespace garuda_test {

// Fixed name<->stride correspondence, matching the plugin's tensor_prefix config default (box heads
// conv71/conv87/conv101, class heads conv74/conv90/conv104, in STRIDES order {8,16,32}). Pinning
// this here — rather than inferring it from tensor shape — keeps these goldens and the plugin's
// literal name map from silently drifting apart.
inline const char* const BOX_NAMES[3] = {"conv71", "conv87", "conv101"};
inline const char* const CLS_NAMES[3] = {"conv74", "conv90", "conv104"};

// Strip any "prefix/" (e.g. "yolo26m/") down to the bare vstream name, e.g. "yolo26m/conv71" -> "conv71".
inline std::string strip_prefix(const std::string& key) {
    auto pos = key.rfind('/');
    return pos == std::string::npos ? key : key.substr(pos + 1);
}

// Compares one decoded detection `d` against an "expected" golden entry `w` (an array
// [class_id, label, conf, x, y, w, h]), within the same tolerances both callers used (1e-5 on
// confidence, 1e-3 on geometry). On mismatch, prints "<msg_prefix>det <i> mismatch: got/want ..." —
// msg_prefix is caller-supplied so each test keeps its own original wording ("case NAME " for the
// synthetic golden's multi-case replay, "yolo26_real " for the single-case real-tensor replay).
// Returns true (no output) when it matches.
inline bool detection_matches(const garuda::yolo26::RawDet& d, const nlohmann::json& w,
                               const std::string& msg_prefix, size_t i) {
    int exp_class = w[0].get<int>();
    std::string exp_label = w[1].get<std::string>();
    double exp_conf = w[2].get<double>();
    double exp_x = w[3].get<double>(), exp_y = w[4].get<double>();
    double exp_w = w[5].get<double>(), exp_h = w[6].get<double>();
    double got_w = d.x2 - d.x1, got_h = d.y2 - d.y1;
    bool ok = d.class_id == exp_class
           && std::string(garuda::yolo26::COCO[d.class_id]) == exp_label
           && std::fabs((double)d.conf - exp_conf) < 1e-5
           && std::fabs(d.x1 - exp_x) < 1e-3
           && std::fabs(d.y1 - exp_y) < 1e-3
           && std::fabs(got_w - exp_w) < 1e-3
           && std::fabs(got_h - exp_h) < 1e-3;
    if (!ok) {
        std::cerr << msg_prefix << "det " << i << " mismatch:\n"
                  << "  got:  class=" << d.class_id << " label=" << garuda::yolo26::COCO[d.class_id]
                  << " conf=" << d.conf << " x=" << d.x1 << " y=" << d.y1 << " w=" << got_w << " h=" << got_h << "\n"
                  << "  want: class=" << exp_class << " label=" << exp_label
                  << " conf=" << exp_conf << " x=" << exp_x << " y=" << exp_y << " w=" << exp_w << " h=" << exp_h << "\n";
    }
    return ok;
}

} // namespace garuda_test
