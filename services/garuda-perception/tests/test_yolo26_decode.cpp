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

// Golden replay against tests/golden/yolo26_golden.json (sparse-v1, built by
// tests/golden/make_yolo26_golden.py from tests/golden/hailo_yolo26_ref.py — byte-identical to the
// Pi's decoder). Each case's 6 sparse tensors are rebuilt dense here, then decode()'d and compared.
// BOX_NAMES/CLS_NAMES, strip_prefix and the per-detection comparison live in yolo26_test_common.hpp
// (shared with test_yolo26_real.cpp).
namespace {

using garuda::yolo26::Letterbox;
using garuda::yolo26::Params;
using garuda::yolo26::RawDet;
using garuda::yolo26::TensorView;
using garuda_test::BOX_NAMES;
using garuda_test::CLS_NAMES;
using garuda_test::strip_prefix;

// Owns the dense buffer for one tensor so it outlives the TensorView built over it.
struct DenseTensor {
    std::vector<float> f32;
    std::vector<uint16_t> u16;
    TensorView view{};
};

DenseTensor build_tensor(const nlohmann::json& t) {
    DenseTensor d;
    int h = t["shape"][0].get<int>(), w = t["shape"][1].get<int>(), c = t["shape"][2].get<int>();
    bool is_u16 = t["dtype"].get<std::string>() == "uint16";
    size_t n = (size_t)h * (size_t)w * (size_t)c;
    if (is_u16) {
        d.u16.assign(n, (uint16_t)t["fill"].get<int>());
        for (auto& e : t["entries"]) {
            int y = e[0].get<int>(), x = e[1].get<int>(), ch = e[2].get<int>();
            size_t pos = (size_t)(w * c) * y + (size_t)c * x + ch;
            d.u16[pos] = (uint16_t)e[3].get<int>();
        }
        d.view.data = d.u16.data();
    } else {
        d.f32.assign(n, t["fill"].get<float>());
        for (auto& e : t["entries"]) {
            int y = e[0].get<int>(), x = e[1].get<int>(), ch = e[2].get<int>();
            size_t pos = (size_t)(w * c) * y + (size_t)c * x + ch;
            d.f32[pos] = e[3].get<float>();
        }
        d.view.data = d.f32.data();
    }
    d.view.h = h; d.view.w = w; d.view.c = c; d.view.is_u16 = is_u16;
    d.view.zp = t["zp"].get<float>(); d.view.scale = t["scale"].get<float>();
    return d;
}

} // namespace

int main(int argc, char** argv) {
    assert(argc == 2);

    // Unit assertions (the Pi's own test values): letterbox_for at two net sizes, squash_for's aspect-distorting ratios.
    {
        Letterbox lb = garuda::yolo26::letterbox_for(640, 640, 1280, 720);
        assert(lb.r_x == 0.5 && lb.r_y == 0.5 && lb.px == 0.0 && lb.py == 140.0);
    }
    {
        Letterbox lb = garuda::yolo26::letterbox_for(960, 960, 1280, 720);
        assert(lb.r_x == 0.75 && lb.r_y == 0.75 && lb.px == 0.0 && lb.py == 210.0);
    }
    {
        Letterbox sq = garuda::yolo26::squash_for(640, 640, 1280, 720);
        assert(std::fabs(sq.r_x - 0.5) < 1e-12);
        assert(std::fabs(sq.r_y - 0.8888888888888888) < 1e-12);
        assert(sq.px == 0.0 && sq.py == 0.0);
    }

    std::ifstream f(argv[1]);
    nlohmann::json golden;
    f >> golden;
    assert(golden["format"].get<std::string>() == "sparse-v1");

    for (auto& c : golden["cases"]) {
        int in_w = c["in_w"].get<int>(), in_h = c["in_h"].get<int>();
        int orig_w = c["orig_w"].get<int>(), orig_h = c["orig_h"].get<int>();
        std::string name = c["name"].get<std::string>();

        // Rebuild the 6 dense tensors, keyed by their bare vstream name (prefix stripped), then look
        // up box[3]/cls[3] BY NAME in the fixed BOX_NAMES/CLS_NAMES order — never inferred from shape —
        // so this golden is pinned to the same name<->stride contract Task 3's plugin uses.
        std::vector<DenseTensor> dense;
        std::unordered_map<std::string, int> by_name; // bare name -> index into dense
        for (auto& item : c["tensors"].items()) {
            dense.push_back(build_tensor(item.value()));
            by_name[strip_prefix(item.key())] = (int)dense.size() - 1;
        }

        TensorView box[3], cls[3];
        for (int i = 0; i < 3; ++i) {
            auto bit = by_name.find(BOX_NAMES[i]);
            assert(bit != by_name.end() && "golden missing named box tensor");
            box[i] = dense[bit->second].view;
            assert(box[i].c == 4 && "box tensor has unexpected channel count");

            auto cit = by_name.find(CLS_NAMES[i]);
            assert(cit != by_name.end() && "golden missing named class tensor");
            cls[i] = dense[cit->second].view;
            assert(cls[i].c == 80 && "class tensor has unexpected channel count");
        }

        Params p;
        p.conf_thresh = c["conf_thresh"].get<float>();
        p.iou_thresh = c["iou_thresh"].get<float>();
        p.in_w = in_w;
        p.in_h = in_h;

        Letterbox lb;
        if (c["lb"].is_null()) {
            lb = garuda::yolo26::squash_for(in_w, in_h, orig_w, orig_h);
        } else {
            lb.r_x = lb.r_y = c["lb"][0].get<double>();
            lb.px = c["lb"][1].get<double>();
            lb.py = c["lb"][2].get<double>();
        }

        std::vector<RawDet> got = garuda::yolo26::decode(box, cls, p, orig_w, orig_h, lb);
        auto& want = c["expected"];
        if (got.size() != want.size()) {
            std::cerr << "case " << name << ": got " << got.size() << " dets, want " << want.size() << "\n";
            return 1;
        }
        for (size_t i = 0; i < got.size(); ++i) {
            if (!garuda_test::detection_matches(got[i], want[i], "case " + name + " ", i)) return 1;
        }
    }
    std::cout << "yolo26 decode golden ok (" << golden["cases"].size() << " cases)\n";
    return 0;
}
