#undef NDEBUG
#include "garuda/bytetrack.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>

// Tracker-only parity: replay the scenario and compare the alive set (confirmed && tsu<=25) per frame with the golden's
// tracks (id, label, bbox, conf, coasting). Lock fields are checked by test_lock.
int main(int argc, char** argv) {
    assert(argc == 3);
    nlohmann::json sc, gd; std::ifstream(argv[1]) >> sc; std::ifstream(argv[2]) >> gd;
    garuda::track::ByteTracker tr(0.4, 0.12, 0.3, 25, 2);
    size_t n = sc["frames"].size(); assert(n == gd["frames"].size());
    for (size_t i = 0; i < n; ++i) {
        std::vector<garuda::track::Det> dets;
        for (auto& d : sc["frames"][i]["dets"]) if (d[5].get<double>() >= 0.15)
            dets.push_back({d[0], d[1], d[2], d[3], d[4].get<std::string>(), d[5]});
        tr.update(dets);
        std::vector<const garuda::track::Track*> alive;
        for (auto& t : tr.tracks()) if (t.confirmed() && t.time_since_update <= 25) alive.push_back(&t);
        auto& want = gd["frames"][i]["tracks"];
        if (alive.size() != want.size()) { std::cerr << "frame " << i << ": " << alive.size() << " tracks, golden " << want.size() << "\n"; return 1; }
        for (size_t k = 0; k < alive.size(); ++k) {
            auto& w = want[k]; const garuda::track::Track* t = alive[k];
            bool ok = t->track_id == w[0].get<int>() && t->cls == w[1].get<std::string>()
                   && std::fabs(t->bbox[0] - w[2].get<double>()) < 1e-9 && std::fabs(t->bbox[1] - w[3].get<double>()) < 1e-9
                   && std::fabs(t->bbox[2] - w[4].get<double>()) < 1e-9 && std::fabs(t->bbox[3] - w[5].get<double>()) < 1e-9
                   && std::fabs(t->conf - w[6].get<double>()) < 1e-9 && (t->time_since_update > 0) == w[7].get<bool>();
            if (!ok) { std::cerr << "frame " << i << " track " << k << " mismatch: id " << t->track_id << " vs " << w[0] << "\n"; return 1; }
        }
    }
    // unit cases from the Pi's test_bytetrack.py
    garuda::track::ByteTracker t2(0.5, 0.1, 0.3, 30, 1);
    std::vector<double> vx;
    for (int x = 0; x < 50; x += 10) { auto out = t2.update({{(double)x, 0, 20, 20, "0", 0.9}}); assert(out.size() == 1 && out[0]->track_id == 1); vx.push_back(out[0]->vel[0]); }
    assert(vx[0] == 0.0); for (size_t i = 1; i < vx.size(); ++i) assert(vx[i] == 10.0);   // steady displacement, not oscillating
    garuda::track::ByteTracker t3(0.5, 0.1, 0.3, 2, 1);
    t3.update({{0, 0, 20, 20, "0", 0.9}});
    assert(t3.tracks().size() == 1);                                                     // born, time_since_update == 0
    t3.update({}); t3.update({});                                                        // exactly max_lost (=2) empty updates
    assert(t3.tracks().size() == 1 && t3.tracks()[0].time_since_update == 2);            // still kept: tsu == max_lost, not culled yet
    t3.update({});                                                                       // one more empty update: tsu == 3 > max_lost
    assert(t3.tracks().empty());                                                         // culled after max_lost
    std::cout << "bytetrack parity ok (" << n << " frames)\n"; return 0;
}
