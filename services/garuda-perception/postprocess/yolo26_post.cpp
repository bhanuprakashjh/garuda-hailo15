// libyolo26_post.so — post-process plugin for the Hailo model-zoo yolo26m (six raw heads, no baked NMS).
// Runs in the pipeline's post stage thread; decodes with garuda::yolo26 (the Pi decoder's port) and attaches
// HailoDetections with boxes normalised to the FRAME (already un-letterboxed), so the node's det_sink keeps
// its xmin*frame_w mapping. LICENCE: model weights are Ultralytics YOLO26 (AGPL-3.0, bench/eval only).
#include "garuda/yolo26_decode.hpp"
#include "hailo_postprocess_tools/objects/hailo_objects.hpp"
#include "hailo_postprocess_tools/objects/hailo_tensors.hpp"
#include "hailo_postprocess_tools/objects/hailo_common.hpp"
#include <nlohmann/json.hpp>
#include <sys/types.h>
#include <cstdio>
#include <exception>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

// Everything below is owned exclusively by the post stage that called init() and holds the returned
// pointer: filter()/free_resources() are only ever invoked by that one stage on its own thread, so no
// member here is shared mutable state across threads or across stage instances (each stage gets its
// own heap-allocated Yolo26Params from its own init() call).
struct Yolo26Params {
    garuda::yolo26::Params p; int frame_w = 1280, frame_h = 720; bool letterbox = true; std::string prefix;
    std::string box_names[3], cls_names[3]; std::vector<std::string> labels;
    std::string dump_path; int dump_frames = 0, dumped = 0; bool dump_failed = false;
    bool warned_missing_tensor = false;
    bool warned_bad_shape = false;
    bool warned_bad_dtype = false;
};

__BEGIN_DECLS
Yolo26Params* init(const std::string config_path, const std::string function_name) {
    (void)function_name;
    auto* q = new Yolo26Params();
    std::ifstream f(config_path);
    if (!f) { std::fprintf(stderr, "yolo26_post: cannot read %s\n", config_path.c_str()); delete q; return nullptr; }
    try {
        nlohmann::json c = nlohmann::json::parse(f);
        q->p.conf_thresh = c.value("conf_thresh", 0.15); q->p.iou_thresh = c.value("iou_thresh", 0.5);
        q->p.in_w = c.value("in_w", 640); q->p.in_h = c.value("in_h", 640);
        q->frame_w = c.value("frame_w", 1280); q->frame_h = c.value("frame_h", 720);
        // A non-positive value here would divide-by-zero or feed a negative dimension into
        // letterbox_for/squash_for (garuda::yolo26::decode's geometry) — reject at config-load time,
        // not partway through the first frame.
        if (q->p.in_w <= 0 || q->p.in_h <= 0 || q->frame_w <= 0 || q->frame_h <= 0) {
            std::fprintf(stderr, "yolo26_post: in_w/in_h/frame_w/frame_h must all be positive (got %d/%d/%d/%d)\n",
                         q->p.in_w, q->p.in_h, q->frame_w, q->frame_h);
            delete q; return nullptr;
        }
        q->letterbox = c.value("mode", std::string("letterbox")) == "letterbox";
        q->prefix = c.value("tensor_prefix", std::string("yolo26m/"));
        auto bn = c.value("box_tensors", std::vector<std::string>{"conv71", "conv87", "conv101"});
        auto cn = c.value("cls_tensors", std::vector<std::string>{"conv74", "conv90", "conv104"});
        if (bn.size() != 3 || cn.size() != 3) {
            std::fprintf(stderr, "yolo26_post: box_tensors/cls_tensors must have exactly 3 entries each (got %zu/%zu)\n", bn.size(), cn.size());
            delete q; return nullptr;
        }
        for (int i = 0; i < 3; ++i) { q->box_names[i] = q->prefix + bn[i]; q->cls_names[i] = q->prefix + cn[i]; }
        q->labels = c.value("labels", std::vector<std::string>{});
        if (q->labels.size() != 80) {
            std::fprintf(stderr, "yolo26_post: labels must have 80 entries (got %zu)\n", q->labels.size());
            delete q; return nullptr;
        }
        for (int i = 0; i < 80; ++i) {
            if (q->labels[i] != garuda::yolo26::COCO[i]) {
                std::fprintf(stderr, "yolo26_post: label %d is '%s', expected '%s'\n", i, q->labels[i].c_str(), garuda::yolo26::COCO[i]);
                delete q; return nullptr;
            }
        }
        auto d = c.value("dump", nlohmann::json::object());
        q->dump_path = d.value("path", std::string("")); q->dump_frames = d.value("frames", 0);
    } catch (const nlohmann::json::exception& e) {
        std::fprintf(stderr, "yolo26_post: bad config %s: %s\n", config_path.c_str(), e.what());
        delete q; return nullptr;
    }
    std::fprintf(stderr, "yolo26_post: conf=%.3f iou=%.2f net=%dx%d frame=%dx%d mode=%s prefix=%s dump=%s/%d\n",
                 q->p.conf_thresh, q->p.iou_thresh, q->p.in_w, q->p.in_h, q->frame_w, q->frame_h,
                 q->letterbox ? "letterbox" : "stretch", q->prefix.c_str(), q->dump_path.c_str(), q->dump_frames);
    return q;
}
void free_resources(void* params_void_ptr) { delete reinterpret_cast<Yolo26Params*>(params_void_ptr); }

// Builds a TensorView over the named ROI tensor's own backing storage (no copy). Returns false — and
// leaves *v untouched — when the ROI carries no tensor of that name. get_tensor() THROWS
// std::invalid_argument("No tensor with name ...") for a missing name (hailo_objects.hpp) rather than
// returning a null HailoTensorPtr, so the lookup itself must be guarded; the null check below is kept
// as a harmless extra guard in case a future SDK version returns null instead.
//
// Also rejects (returns false for) a tensor that is not UINT16: at() in yolo26_decode.cpp branches
// on TensorView::is_u16 and reads raw bytes as either uint16_t or float32 depending on it — an 8-bit
// (or any non-uint16) tensor handed through here would be silently reinterpreted as uint16 (wrong
// element size/stride) or misread as raw fixed-point when the HEF's actual quantisation differs from
// what this plugin assumes. Checked and warned about (once) here, BEFORE dump_frame() ever runs on
// this frame's tensors (filter() calls view_of() before the dump, so a bad-dtype frame never reaches
// the dump and never gets written 4x by all four dump call sites that would otherwise still fire on
// every remaining permitted frame).
static bool view_of(HailoROIPtr roi, const std::string& name, garuda::yolo26::TensorView& v, Yolo26Params* q) {
    HailoTensorPtr t;
    try {
        t = roi->get_tensor(name);
    } catch (const std::exception&) {
        return false;
    }
    if (!t) return false;
    if (!t->is_uint16()) {
        if (q && !q->warned_bad_dtype) {
            q->warned_bad_dtype = true;
            std::fprintf(stderr, "yolo26_post: tensor %s has an unexpected dtype, expected UINT16\n", name.c_str());
        }
        return false;
    }
    v.data = t->data(); v.h = (int)t->height(); v.w = (int)t->width(); v.c = (int)t->features();
    v.is_u16 = t->is_uint16(); v.zp = t->qp_zp(); v.scale = t->qp_scale();
    return true;
}

// One file per frame: <path>.<n>.bin = the six tensors' raw bytes back to back (box0,box1,box2,cls0,cls1,cls2);
// <path>.<n>.json = an array of six objects, each with keys in the literal order name/shape/dtype/
// zp/scale/bytes (Task 5 reads both). Built as nlohmann::ordered_json rather than plain nlohmann::json:
// plain json's object keys serialise alphabetically, which would silently break that stated order.
static void dump_frame(Yolo26Params* q, const garuda::yolo26::TensorView box[3], const garuda::yolo26::TensorView cls[3]) {
    char nb[512];
    std::snprintf(nb, sizeof nb, "%s.%d.bin", q->dump_path.c_str(), q->dumped);
    std::ofstream b(nb, std::ios::binary);
    nlohmann::ordered_json hdr = nlohmann::ordered_json::array();
    const garuda::yolo26::TensorView* all[6] = {&box[0], &box[1], &box[2], &cls[0], &cls[1], &cls[2]};
    const std::string* names[6] = {&q->box_names[0], &q->box_names[1], &q->box_names[2], &q->cls_names[0], &q->cls_names[1], &q->cls_names[2]};
    for (int i = 0; i < 6; ++i) {
        size_t n = (size_t)all[i]->h * (size_t)all[i]->w * (size_t)all[i]->c * (all[i]->is_u16 ? 2 : 4);
        b.write((const char*)all[i]->data, (std::streamsize)n);
        hdr.push_back({{"name", *names[i]}, {"shape", {all[i]->h, all[i]->w, all[i]->c}},
                       {"dtype", all[i]->is_u16 ? "uint16" : "float32"}, {"zp", all[i]->zp}, {"scale", all[i]->scale}, {"bytes", n}});
    }
    if (!b.good()) {
        q->dump_failed = true;
        std::fprintf(stderr, "yolo26_post: dump write failed at frame %d, disabling\n", q->dumped);
        return;
    }
    char nj[512];
    std::snprintf(nj, sizeof nj, "%s.%d.json", q->dump_path.c_str(), q->dumped);
    std::ofstream(nj) << hdr.dump(1) << "\n";
    if (++q->dumped >= q->dump_frames) {
        std::fprintf(stderr, "yolo26_post: dumped %d frames to %s.*\n", q->dumped, q->dump_path.c_str());
    }
}

void filter(HailoROIPtr roi, void* params_void_ptr) {
    auto* q = reinterpret_cast<Yolo26Params*>(params_void_ptr);
    // A null params pointer means init() either was never called or returned nullptr (a rejected
    // config) — the pipeline should not have wired this stage up in that case, but if it did, this
    // node is now silently blind (every frame returns here with no detections ever emitted) unless
    // something says so. warned_null_params is a function-local static, not a Yolo26Params field,
    // because there is by definition no params instance to hold it when q is null.
    if (!q) {
        static bool warned_null_params = false;
        if (!warned_null_params) {
            warned_null_params = true;
            std::fprintf(stderr, "yolo26_post: filter() called with null params (init() must have failed or was never called) — no detections will ever be emitted\n");
        }
        return;
    }
    if (!roi || !roi->has_tensors()) return;
    garuda::yolo26::TensorView box[3], cls[3];
    for (int i = 0; i < 3; ++i) {
        if (!view_of(roi, q->box_names[i], box[i], q) || !view_of(roi, q->cls_names[i], cls[i], q)) {
            if (!q->warned_missing_tensor) {
                q->warned_missing_tensor = true;
                std::fprintf(stderr, "yolo26_post: tensor %s or %s missing on the ROI (or rejected — see any dtype warning above)\n", q->box_names[i].c_str(), q->cls_names[i].c_str());
            }
            return;
        }
    }
    // Dumped ahead of the shape check below on purpose: a shape mismatch is exactly the case the
    // tensor dump exists to diagnose, so a bad-shape frame must still be captured, not skipped.
    if (!q->dump_path.empty() && q->dumped < q->dump_frames && !q->dump_failed) dump_frame(q, box, cls);
    // Guard against a wrong tensor being handed to decode() — a stale prefix, a stride mapping that no
    // longer matches this HEF, or a HEF with a differently-shaped head would otherwise feed garbage
    // into decode() and, for cls, could hand it a class_id past the end of q->labels (UB via
    // operator[]). Checked once per frame; cheap relative to decode() itself.
    const int n_labels = (int)q->labels.size();
    for (int i = 0; i < 3; ++i) {
        const int stride = garuda::yolo26::STRIDES[i];
        const int exp_h = q->p.in_h / stride, exp_w = q->p.in_w / stride;
        const bool ok = box[i].c == 4 && box[i].h == exp_h && box[i].w == exp_w &&
                        cls[i].c == n_labels && cls[i].h == exp_h && cls[i].w == exp_w;
        if (!ok) {
            if (!q->warned_bad_shape) {
                q->warned_bad_shape = true;
                std::fprintf(stderr,
                    "yolo26_post: shape mismatch at stride %d: %s is %dx%dx%d (want %dx%dx4), %s is %dx%dx%d (want %dx%dx%d)\n",
                    stride, q->box_names[i].c_str(), box[i].h, box[i].w, box[i].c, exp_h, exp_w,
                    q->cls_names[i].c_str(), cls[i].h, cls[i].w, cls[i].c, exp_h, exp_w, n_labels);
            }
            return;
        }
    }
    auto lb = q->letterbox ? garuda::yolo26::letterbox_for(q->p.in_w, q->p.in_h, q->frame_w, q->frame_h)
                           : garuda::yolo26::squash_for(q->p.in_w, q->p.in_h, q->frame_w, q->frame_h);
    auto dets = garuda::yolo26::decode(box, cls, q->p, q->frame_w, q->frame_h, lb);
    std::vector<HailoDetection> out; out.reserve(dets.size());
    for (const auto& d : dets) { // normalised to the FRAME: det_sink multiplies by frame_w/frame_h
        if (d.class_id < 0 || d.class_id >= n_labels) continue; // cannot happen after the shape check above; kept as a hard backstop
        HailoBBox bb((float)(d.x1 / q->frame_w), (float)(d.y1 / q->frame_h),
                     (float)((d.x2 - d.x1) / q->frame_w), (float)((d.y2 - d.y1) / q->frame_h));
        out.emplace_back(bb, d.class_id, q->labels[d.class_id], d.conf);
    }
    hailo_common::add_detections(roi, out);
}
__END_DECLS
