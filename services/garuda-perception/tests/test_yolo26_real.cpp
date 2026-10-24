#undef NDEBUG
#include "garuda/yolo26_decode.hpp"
#include "yolo26_test_common.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

// Real-tensor golden (Task 5, M2): tests/golden/yolo26_real_frame.bin is the SIX RAW UINT16 tensors
// libyolo26_post.so's dump option wrote back-to-back on the Hailo-15L SBC for one live bench-scene
// frame (box stride 8/16/32, then class stride 8/16/32); tests/golden/yolo26_real_frame.json is that
// dump's own header (name/shape/dtype/zp/scale/bytes, file order) plus the parameters and the expected
// detections computed by tests/golden/make_yolo26_real_golden.py via hailo_yolo26_ref.decode_yolo26
// (byte-identical to the Pi's decoder). This is the dequantisation proof: unlike test_yolo26_decode's
// synthetic sparse golden, every logit here came off real hardware, so a mismatch here means the C++
// port's fixed-point-to-float32 dequantisation (or NMS/geometry) disagrees with the Python reference
// on actual device output, not on a hand-placed test vector.
// BOX_NAMES/CLS_NAMES, strip_prefix and the per-detection comparison live in yolo26_test_common.hpp
// (shared with test_yolo26_decode.cpp).
namespace {

using garuda::yolo26::Letterbox;
using garuda::yolo26::Params;
using garuda::yolo26::RawDet;
using garuda::yolo26::TensorView;
using garuda_test::BOX_NAMES;
using garuda_test::CLS_NAMES;
using garuda_test::strip_prefix;

std::vector<char> read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    assert(f && "cannot open golden .bin");
    std::streamsize n = f.tellg();
    f.seekg(0);
    std::vector<char> buf((size_t)n);
    assert(f.read(buf.data(), n) && "short read on golden .bin");
    return buf;
}

} // namespace

int main(int argc, char** argv) {
    assert(argc == 3 && "usage: test_yolo26_real <json> <bin>");

    std::ifstream jf(argv[1]);
    assert(jf && "cannot open golden .json");
    nlohmann::json g;
    jf >> g;

    std::vector<char> bin = read_file(argv[2]);

    // Walk the six header entries IN FILE ORDER to compute each tensor's byte offset (the dump wrote
    // them back to back: box0,box1,box2,cls0,cls1,cls2), then index box[3]/cls[3] BY NAME — never by
    // position — against the fixed BOX_NAMES/CLS_NAMES above, exactly as test_yolo26_decode.cpp does.
    std::unordered_map<std::string, TensorView> by_name;
    size_t offset = 0;
    for (auto& t : g["tensors"]) {
        std::string name = strip_prefix(t["name"].get<std::string>());
        int h = t["shape"][0].get<int>(), w = t["shape"][1].get<int>(), c = t["shape"][2].get<int>();
        std::string dtype = t["dtype"].get<std::string>();
        assert(dtype == "uint16" && "real-hardware dump tensors are always uint16");
        size_t expect_bytes = (size_t)h * (size_t)w * (size_t)c * 2;
        size_t hdr_bytes = t["bytes"].get<size_t>();
        assert(hdr_bytes == expect_bytes && "header bytes field disagrees with h*w*c*2");
        assert(offset + hdr_bytes <= bin.size() && "golden .bin shorter than header implies");

        TensorView v;
        v.data = bin.data() + offset;
        v.h = h; v.w = w; v.c = c;
        v.is_u16 = true;
        v.zp = t["zp"].get<float>();
        v.scale = t["scale"].get<float>();
        by_name[name] = v;
        offset += hdr_bytes;
    }
    assert(offset == bin.size() && "golden .bin has trailing bytes past the six headers' sizes");

    TensorView box[3], cls[3];
    for (int i = 0; i < 3; ++i) {
        auto bit = by_name.find(BOX_NAMES[i]);
        assert(bit != by_name.end() && "golden missing named box tensor");
        box[i] = bit->second;
        assert(box[i].c == 4 && "box tensor has unexpected channel count");

        auto cit = by_name.find(CLS_NAMES[i]);
        assert(cit != by_name.end() && "golden missing named class tensor");
        cls[i] = cit->second;
        assert(cls[i].c == 80 && "class tensor has unexpected channel count");
    }

    Params p;
    p.conf_thresh = g["conf_thresh"].get<float>();
    p.iou_thresh = g["iou_thresh"].get<float>();
    p.in_w = g["in_w"].get<int>();
    p.in_h = g["in_h"].get<int>();
    int frame_w = g["frame_w"].get<int>(), frame_h = g["frame_h"].get<int>();

    // Computed via the production letterbox_for (not read back from the json's own recorded "lb"),
    // so this test also exercises that the C++ geometry agrees with make_yolo26_real_golden.py's
    // lb_for on this exact frame — cross-checked against the recorded value below.
    Letterbox lb = garuda::yolo26::letterbox_for(p.in_w, p.in_h, frame_w, frame_h);
    assert(std::fabs(lb.r_x - g["lb"][0].get<double>()) < 1e-12);
    assert(std::fabs(lb.px - g["lb"][1].get<double>()) < 1e-12);
    assert(std::fabs(lb.py - g["lb"][2].get<double>()) < 1e-12);

    std::vector<RawDet> got = garuda::yolo26::decode(box, cls, p, frame_w, frame_h, lb);
    auto& want = g["expected"];
    if (got.size() != want.size()) {
        std::cerr << "yolo26_real: got " << got.size() << " dets, want " << want.size() << "\n";
        return 1;
    }
    for (size_t i = 0; i < got.size(); ++i) {
        if (!garuda_test::detection_matches(got[i], want[i], "yolo26_real ", i)) return 1;
    }
    std::cout << "yolo26 real-frame golden ok (" << got.size() << " detections)\n";
    return 0;
}
