#include "garuda/snapshot.hpp"
#include <nlohmann/json.hpp>
#undef NDEBUG          // asserts are the assertions in these tests; never compile them out
#include <cassert>
#include <fstream>
#include <iostream>

// The Pi's golden (tests/golden/snapshot_v2.json, built from hosts/pi5/mono_state.py on a different
// branch) predates LockCore's eight additive fields (F1 lock-core) -- it will never contain them. So
// the golden comparison here is a SUBSET check (every key/value in `golden` must equal the
// corresponding one in `got`; extra keys in `got` are allowed and expected) rather than exact
// equality, and the new fields get their own presence/type assertions below instead.
static bool is_subset(const nlohmann::json& golden, const nlohmann::json& got, std::string* why) {
    if (golden.is_object()) {
        if (!got.is_object()) { *why = "expected object"; return false; }
        for (auto it = golden.begin(); it != golden.end(); ++it) {
            if (!got.contains(it.key())) { *why = "missing key " + it.key(); return false; }
            if (!is_subset(it.value(), got.at(it.key()), why)) { *why = it.key() + "." + *why; return false; }
        }
        return true;
    }
    if (golden.is_array()) {
        if (!got.is_array() || got.size() != golden.size()) { *why = "array size/type mismatch"; return false; }
        for (size_t i = 0; i < golden.size(); ++i)
            if (!is_subset(golden[i], got[i], why)) { *why = "[" + std::to_string(i) + "]." + *why; return false; }
        return true;
    }
    if (golden != got) { *why = "value mismatch (golden=" + golden.dump() + " got=" + got.dump() + ")"; return false; }
    return true;
}

int main(int argc, char** argv) {
    assert(argc == 2);
    std::ifstream f(argv[1]); nlohmann::json golden; f >> golden;
    garuda::SnapshotState s;
    s.tracks = {{7, "person", 0.91, 100, 50, 40, 120, false}, {9, "vehicle", 0.55, 600, 300, 200, 90, true}};
    s.lock_id = 7; s.lock_class = "person"; s.raw_m = 2.31; s.est_m = 2.4; s.valid = true;
    s.cal_n = 3; s.cal_fit = "a=1.00 b=0.00"; s.age_ms = 33;
    nlohmann::json got = nlohmann::json::parse(garuda::build_snapshot_json(s));
    std::string why;
    if (!is_subset(golden, got, &why)) {
        std::cerr << "MISMATCH: " << why << "\n got:    " << got.dump() << "\n golden: " << golden.dump() << "\n";
        return 1;
    }

    // LockCore's eight additive fields (F1 lock-core; `epoch` and `box` added by the final-fix wave,
    // I2/I5): not in the golden (it predates them), so assert their presence and JSON type directly
    // instead. With a default (never-locked) SnapshotState.lock_* this asserts against the untouched
    // defaults ("none", false, false, 0.0, 0.0, 0.0, epoch 0, box null).
    auto& lock = got["lock"];
    assert(lock.contains("state") && lock["state"].is_string() && lock["state"] == "none");
    assert(lock.contains("identity_locked") && lock["identity_locked"].is_boolean() && lock["identity_locked"] == false);
    assert(lock.contains("observation_valid") && lock["observation_valid"].is_boolean() && lock["observation_valid"] == false);
    assert(lock.contains("quality") && lock["quality"].is_number());
    assert(lock.contains("obs_age_ms") && lock["obs_age_ms"].is_number());
    assert(lock.contains("uncertainty_px") && lock["uncertainty_px"].is_number());
    assert(lock.contains("epoch") && lock["epoch"].is_number_integer() && lock["epoch"] == 0);
    assert(lock.contains("box") && lock["box"].is_null());   // no box while nothing is locked

    // lock.box carries LockCore's own Output.box (frame pixels) when there is one -- the published
    // box for the locked target, distinct from whatever the multi-object tracker's `tracks[]` entry
    // of the same id says (that one is the engine's own extrapolated/frozen box).
    garuda::SnapshotState b = s;
    b.lock_epoch = 3;
    b.lock_box = garuda::LockBox{100.5, 50.25, 40.0, 120.0};
    nlohmann::json bj = nlohmann::json::parse(garuda::build_snapshot_json(b));
    assert(bj["lock"]["epoch"].is_number_integer() && bj["lock"]["epoch"] == 3);
    assert(bj["lock"]["box"].is_object());
    assert(bj["lock"]["box"]["x"] == 100.5 && bj["lock"]["box"]["y"] == 50.25);
    assert(bj["lock"]["box"]["w"] == 40.0 && bj["lock"]["box"]["h"] == 120.0);

    // empty-state contract: no lock, no distance, no cal
    garuda::SnapshotState e; nlohmann::json ej = nlohmann::json::parse(garuda::build_snapshot_json(e));
    assert(ej["lock"]["id"].is_null()); assert(ej["distance"]["valid"] == false); assert(ej["cal"]["fit"].is_null());
    assert(ej["frame"]["width"] == 1280); assert(ej["gesture"]["name"].is_null());
    assert(ej["lock"]["state"] == "none"); assert(ej["lock"]["identity_locked"] == false);
    assert(ej["lock"]["epoch"] == 0); assert(ej["lock"]["box"].is_null());

    // On-board fix round 9 (Ruling 30): `lock.control_valid` -- freshness, additive. It is the flag
    // a follow controller must gate on: `observation_valid` alone says only "the core associated
    // something on its last frame", with no statement about how old that frame is by the time a
    // consumer reads it. The node computes it (node_main.cpp) as
    // observation_valid && (obs_age_ms + age_ms) <= lock.control_valid_ms; here we only pin the
    // key's presence and JSON type, plus that it defaults false on a never-locked snapshot.
    assert(ej["lock"].contains("control_valid") && ej["lock"]["control_valid"].is_boolean());
    assert(ej["lock"]["control_valid"] == false);
    garuda::SnapshotState cv = s;
    cv.lock_observation_valid = true; cv.lock_control_valid = true;
    nlohmann::json cvj = nlohmann::json::parse(garuda::build_snapshot_json(cv));
    assert(cvj["lock"]["control_valid"].is_boolean() && cvj["lock"]["control_valid"] == true);

    // On-board fix round 9: the `diag` object -- per-frame stage counters, additive, so stage-by-
    // stage accounting is possible from a capture alone. -1 means "this engine cannot see that
    // stage" (see hosts/hailo15l/README.md §9); every value is an integer.
    assert(ej.contains("diag") && ej["diag"].is_object());
    for (const char* k : {"raw_dets", "sdk_tracks", "live_raw", "published", "core_candidates"}) {
        assert(ej["diag"].contains(k));
        assert(ej["diag"][k].is_number_integer());
        assert(ej["diag"][k] == -1);            // untouched default: nothing counted yet
    }
    garuda::SnapshotState dg = s;
    dg.diag_raw_dets = 7; dg.diag_sdk_tracks = 5; dg.diag_live_raw = 4;
    dg.diag_published = 3; dg.diag_core_candidates = 4;
    nlohmann::json dj = nlohmann::json::parse(garuda::build_snapshot_json(dg));
    assert(dj["diag"]["raw_dets"] == 7 && dj["diag"]["sdk_tracks"] == 5);
    assert(dj["diag"]["live_raw"] == 4 && dj["diag"]["published"] == 3);
    assert(dj["diag"]["core_candidates"] == 4);
    std::cout << "snapshot parity ok\n"; return 0;
}
