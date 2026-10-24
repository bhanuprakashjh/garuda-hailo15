#pragma once
#include "garuda/lock_core.hpp"
#include <nlohmann/json.hpp>
#include <cassert>
#include <fstream>
#include <map>
#include <string>
#include <vector>

// Shared loader for the two on-board capture replays (tests/test_lock_replay.cpp — routine 1, run 5;
// tests/test_lock_replay2.cpp — routine 2, run 7). Both fixtures are the same shape: an array of
// `{t_ms, tracks:[{id, cls, conf, x, y, w, h, coasting}]}` rows extracted verbatim from a PC-side
// timestamped SSE capture of the board, `t_ms` relative to the first row of the extracted window.
//
// **Both replays are COARSER than the live pipeline.** The SSE shim caps at ~10 Hz where the board
// runs the core at ~25-30 fps, so every gap the core sees here is ~3x the real one: covariances grow
// more between frames and the gates are correspondingly wider. On balance that makes a replay a
// WEAKER gate than the on-board run, not a stronger one — passing here does not by itself prove the
// on-board numbers, it stops the mechanisms these captures exposed from regressing silently.
namespace lock_replay {

struct Track {
    int id = -1;
    std::string cls;
    double conf = 0, x = 0, y = 0, w = 0, h = 0;
    bool coasting = false;
};
struct Row {
    double t_ms = 0;
    std::vector<Track> tracks;
};

inline std::vector<Row> load(const char* path) {
    std::ifstream in(path);
    assert(in && "fixture not readable");
    nlohmann::json j;
    in >> j;
    assert(j.is_array() && !j.empty());
    std::vector<Row> rows;
    rows.reserve(j.size());
    for (const auto& jr : j) {
        Row r;
        r.t_ms = jr.at("t_ms").get<double>();
        for (const auto& jt : jr.at("tracks")) {
            Track t;
            t.id = jt.at("id").get<int>();
            t.cls = jt.at("cls").get<std::string>();
            t.conf = jt.at("conf").get<double>();
            t.x = jt.at("x").get<double>();
            t.y = jt.at("y").get<double>();
            t.w = jt.at("w").get<double>();
            t.h = jt.at("h").get<double>();
            t.coasting = jt.at("coasting").get<bool>();
            r.tracks.push_back(t);
        }
        rows.push_back(std::move(r));
    }
    return rows;
}

// On-board fix round 10 (Ruling 32b): `first_seen_ms` per tracker id, DERIVED from the capture --
// the `t_ms` of the FIRST row in which that id appears anywhere in `tracks[]` (live or coasting, any
// class, any confidence). The captures predate the field, so it cannot be read off them; this is the
// closest faithful reconstruction of what the node would have stamped, and it is the same rule the
// live adapter uses ("the frame the id was first seen"), modulo the capture's own sampling rate.
//
// Two honest caveats, both making the reconstruction CONSERVATIVE rather than optimistic:
//   - a capture window that opens mid-run stamps every already-present id with the window's first
//     row, so such an id looks "born" at t_ms 0 -- i.e. before any later loss, which is exactly the
//     pre-existing case Ruling 32(b) refuses. It cannot manufacture a born-after-loss id.
//   - a coasting entry counts as an appearance, so an id is never stamped later than it truly began.
inline std::map<int, double> firstSeenMs(const std::vector<Row>& rows) {
    std::map<int, double> first;
    for (const auto& r : rows)
        for (const auto& t : r.tracks)
            first.emplace(t.id, r.t_ms);   // emplace: the earliest row wins, later ones are no-ops
    return first;
}

inline garuda::lock::Obs toObs(const Track& t, const std::map<int, double>* first = nullptr) {
    garuda::lock::Obs o;
    o.id = t.id; o.cls = t.cls; o.conf = t.conf;
    o.x = t.x; o.y = t.y; o.w = t.w; o.h = t.h;
    if (first) {
        auto it = first->find(t.id);
        if (it != first->end()) o.first_seen_ms = it->second;
    }
    return o;
}

// Node parity: `src/node_main.cpp` builds its `live_obs` from records with `time_since_update == 0`
// only, so coasting entries never reach LockCore. The fixtures keep them (they are a faithful copy of
// what the board published); this is where they are dropped.
inline std::vector<garuda::lock::Obs> liveObs(const Row& r, const std::map<int, double>* first = nullptr) {
    std::vector<garuda::lock::Obs> dets;
    dets.reserve(r.tracks.size());
    for (const auto& t : r.tracks) {
        if (t.coasting) continue;
        dets.push_back(toObs(t, first));
    }
    return dets;
}

} // namespace lock_replay
