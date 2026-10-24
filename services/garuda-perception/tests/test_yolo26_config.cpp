#undef NDEBUG
#include "garuda/yolo26_decode.hpp"
#include <nlohmann/json.hpp>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// Config-contract test (Final Fix Wave item E, M2): asserts the two COMMITTED config files
// (config/yolo26_post.json, config/perception.json) and the M2 media-library profile
// (hosts/hailo15l/medialib/profile/application_settings.json) agree with each other and with the
// compiled-in constants (garuda::yolo26::COCO), so a hand-edit to any one of the three that breaks
// the others is caught here rather than only discovered live on the board. This never touches the
// board or the plugin's shared object — it only reads the committed JSON files given on argv.
namespace {

std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("cannot read " + path);
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: test_yolo26_config <yolo26_post.json> <perception.json> <application_settings.json>\n";
        return 1;
    }
    const nlohmann::json post = nlohmann::json::parse(read_file(argv[1]));
    const nlohmann::json perc = nlohmann::json::parse(read_file(argv[2]));
    const nlohmann::json app = nlohmann::json::parse(read_file(argv[3]));

    // 1. labels == garuda::yolo26::COCO, 80 entries, in order — the plugin's own init() rejects a
    // mismatch here at runtime (yolo26_post.cpp); this test catches the same class of error at
    // build time, against the same compiled-in table the plugin checks against.
    const auto& labels = post.at("labels");
    if (labels.size() != 80) {
        std::cerr << "yolo26_post.json: labels has " << labels.size() << " entries, want 80\n";
        return 1;
    }
    for (int i = 0; i < 80; ++i) {
        std::string got = labels[i].get<std::string>();
        if (got != garuda::yolo26::COCO[i]) {
            std::cerr << "yolo26_post.json: labels[" << i << "] = '" << got << "', want '" << garuda::yolo26::COCO[i] << "'\n";
            return 1;
        }
    }

    // 2. box_tensors/cls_tensors == the fixed name<->stride correspondence the decoder, both goldens
    // (tests/yolo26_test_common.hpp) and the plugin's own default all assume.
    const std::vector<std::string> want_box = {"conv71", "conv87", "conv101"};
    const std::vector<std::string> want_cls = {"conv74", "conv90", "conv104"};
    auto got_box = post.at("box_tensors").get<std::vector<std::string>>();
    auto got_cls = post.at("cls_tensors").get<std::vector<std::string>>();
    if (got_box != want_box) {
        std::cerr << "yolo26_post.json: box_tensors mismatch\n";
        return 1;
    }
    if (got_cls != want_cls) {
        std::cerr << "yolo26_post.json: cls_tensors mismatch\n";
        return 1;
    }

    // 3. frame_w/frame_h ASPECT RATIO matches perception.json's — not the absolute values (see
    // node_main.cpp's det_sink comment: the plugin normalises by its own frame_w/h, the node
    // multiplies by its own frame_w/h, so a uniform scale between the two cancels; only a shape
    // mismatch would produce wrong letterbox padding).
    double post_w = post.at("frame_w").get<double>(), post_h = post.at("frame_h").get<double>();
    double perc_w = perc.at("frame_w").get<double>(), perc_h = perc.at("frame_h").get<double>();
    double post_aspect = post_w / post_h, perc_aspect = perc_w / perc_h;
    if (std::fabs(post_aspect - perc_aspect) >= 1e-9) {
        std::cerr << "frame_w/frame_h aspect mismatch: yolo26_post.json " << post_w << "x" << post_h
                   << " (aspect " << post_aspect << ") vs perception.json " << perc_w << "x" << perc_h
                   << " (aspect " << perc_aspect << ")\n";
        return 1;
    }

    // 4. conf_thresh == perception.json's track.conf_floor — the plugin's own post-process floor
    // must match det_sink's floor (node_main.cpp), or one of the two silently truncates the other's
    // intended [low_thr, high_thr) re-association band (see hosts/hailo15l/README.md §8).
    double post_conf = post.at("conf_thresh").get<double>();
    double track_floor = perc.at("track").at("conf_floor").get<double>();
    if (std::fabs(post_conf - track_floor) >= 1e-12) {
        std::cerr << "conf_thresh (" << post_conf << ") != perception.json track.conf_floor (" << track_floor << ")\n";
        return 1;
    }

    // 5. in_w/in_h == the M2 profile's sink0 width/height — the plugin's network input geometry must
    // match what the media library actually delivers to the detect stage, or letterbox_for's own
    // in_w/in_h no longer describes the real input buffer.
    int post_in_w = post.at("in_w").get<int>(), post_in_h = post.at("in_h").get<int>();
    int sink0_w = -1, sink0_h = -1;
    for (auto& r : app.at("application_input_streams").at("resolutions")) {
        if (r.at("stream_id").get<std::string>() == "sink0") {
            sink0_w = r.at("width").get<int>();
            sink0_h = r.at("height").get<int>();
        }
    }
    if (sink0_w < 0 || sink0_h < 0) {
        std::cerr << "application_settings.json: no sink0 entry in application_input_streams.resolutions\n";
        return 1;
    }
    if (post_in_w != sink0_w || post_in_h != sink0_h) {
        std::cerr << "in_w/in_h (" << post_in_w << "x" << post_in_h << ") != M2 profile's sink0 "
                   << sink0_w << "x" << sink0_h << "\n";
        return 1;
    }

    std::cout << "yolo26 config contract ok\n";
    return 0;
}
