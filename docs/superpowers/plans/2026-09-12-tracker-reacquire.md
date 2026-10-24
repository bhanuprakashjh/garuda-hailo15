# Tracker Re-acquire Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Bounded, gated re-acquire of the selected target in
`garuda::fresh::Tracker` so a loss longer than the coast window is no longer
terminal, with zero tolerance for identity transfer.

**Architecture:** A `LostMemory` retained when the selected track expires
(label, motion-compensated box, appearance, loss clock, last-observation
clock); an explicit gate ladder over confirmed candidate tracks
(born-after-loss, size, expanding radius, appearance, uniqueness margin); an
N-of-M pending confirmation before rebinding. Ordinary association still
never resurrects an expired id; the learned-person `TargetOwner` path is
untouched and takes precedence when active.

**Tech Stack:** C++17, existing `garuda_tracking` static library, CHECK-macro
test binary `test_fresh_tracking` (ctest name `fresh_tracking`), replay
evaluation via `garuda-track-replay` + `bench/hailo_reference` converters.

**Spec:** `docs/superpowers/specs/2026-09-12-follow-platform-and-reacquire-design.md`

## Global Constraints

- Defaults exactly as speced: window 7000 ms (0 disables), hits 3, confirm
  600 ms, gap 250 ms, size ratio 2.5, radius 2.0 extents growing 0.5/s,
  appearance gate and ambiguity margin reuse the existing config values.
- `wrong_identity` must measure 0 on every replay evaluation.
- Epoch does not change on re-acquire (same user selection).
- Build/test natively: `cmake -S services/garuda-tracking -B <dir>
  -DGARUDA_TRACKING_TESTS=ON && cmake --build <dir> && ctest`.
- Commits follow repo style with the session attribution trailer.

---

### Task 1: Config fields + validation

**Files:**
- Modify: `services/garuda-tracking/include/garuda_tracking/tracker.hpp` (struct `Config`)
- Modify: `services/garuda-tracking/src/tracker.cpp` (constructor validation)
- Modify: `services/garuda-tracking/include/garuda_tracking/json.hpp` (`config_from_json` GARUDA_PARAM list)
- Test: `services/garuda-tracking/tests/test_tracking.cpp`

**Interfaces:**
- Produces on `Config`: `double reacquire_window_ms=7000, reacquire_confirm_ms=600, reacquire_gap_ms=250, reacquire_size_ratio=2.5, reacquire_radius=2.0, reacquire_radius_growth=.5; unsigned reacquire_hits=3;`

- [x] **Step 1: Failing test** — in `test_tracking.cpp` add and register:

```cpp
void reacquire_config_validation() {
    Config c;CHECK(c.reacquire_window_ms==7000);CHECK(c.reacquire_hits==3);
    c.reacquire_window_ms=0;Tracker ok(c);              // 0 disables, accepted
    c.reacquire_window_ms=-1;
    bool threw=false;try{Tracker t(c);}catch(const std::invalid_argument&){threw=true;}
    CHECK(threw);
    c=Config{};c.reacquire_size_ratio=.5;
    threw=false;try{Tracker t(c);}catch(const std::invalid_argument&){threw=true;}
    CHECK(threw);
}
```

- [x] **Step 2: Run to fail** — `ctest -R fresh_tracking` fails to compile (missing fields).
- [x] **Step 3: Implement** — add the seven fields to `Config`; in the
  constructor validate `reacquire_window_ms>=0` and finite; the five other
  doubles `>0` and finite; `reacquire_size_ratio>1`; `reacquire_hits` in
  [1,100]; add the seven `GARUDA_PARAM(...)` lines to `config_from_json`.
- [x] **Step 4: Run to pass** — `ctest -R fresh_tracking`.
- [x] **Step 5: Commit** `feat: re-acquire configuration surface`.

### Task 2: Loss memory, states, window expiry, disable switch

**Files:**
- Modify: `services/garuda-tracking/include/garuda_tracking/tracker.hpp` (private `LostMemory`)
- Modify: `services/garuda-tracking/src/tracker.cpp` (expiry scan in `update`, `snapshot`, `unlock`, `select`)
- Test: `services/garuda-tracking/tests/test_tracking.cpp`

**Interfaces:**
- Produces (private): `struct LostMemory { std::string label; Box box; std::optional<Appearance> appearance; double lost_ms=0,last_seen_ms=0; uint64_t lost_id=0,pending_id=0; unsigned pending_hits=0; double pending_start_ms=0,pending_last_ms=0; }; std::optional<LostMemory> lost_memory_;`
- Target states while memory is live: `lost/watching_for_return`, after
  expiry `lost/reacquire_window_expired`; with window 0 today's
  `lost/reselection_required` is preserved verbatim.

- [x] **Step 1: Failing tests**

```cpp
void reacquire_memory_states() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    for(int i=0;i<30;++i) t.update(frame(4+i,1200+i*60,{}));   // > coast, track expires
    auto o=t.snapshot(3100);
    CHECK(o.target.state=="lost");CHECK(o.target.reason=="watching_for_return");
    o=t.snapshot(1130+8000);                                    // beyond 7 s window
    CHECK(o.target.reason=="reacquire_window_expired");
}
void reacquire_disabled_matches_today() {
    Config c;c.reacquire_window_ms=0;Tracker t(c);warm(t);CHECK(t.select(1,3,1130));
    for(int i=0;i<30;++i) t.update(frame(4+i,1200+i*60,{}));
    auto o=t.snapshot(3100);
    CHECK(o.target.state=="lost");CHECK(o.target.reason=="reselection_required");
}
```

- [x] **Step 2: Run to fail.**
- [x] **Step 3: Implement** — in the expiry scan of `update`, when the erased
  state is the selected target and the feature is enabled and the owner is
  not active, snapshot `LostMemory{label, box, appearance, f.now_ms,
  last_seen_ms, id}` before erasing; advance `lost_memory_->box` with
  `f.motion.transform` each accepted frame; in `snapshot`, when
  `target_lost_` and memory present render `watching_for_return`, and when
  `now-lost_ms > reacquire_window_ms` render `reacquire_window_expired`;
  `unlock()` and successful `select()` clear the memory.
- [x] **Step 4: Run to pass.**
- [x] **Step 5: Commit** `feat: retained loss memory and re-acquire states`.

### Task 3: Gate ladder + pending confirmation + rebind

**Files:**
- Modify: `services/garuda-tracking/src/tracker.cpp` (new private step after births, before `snapshot`)
- Modify: `services/garuda-tracking/include/garuda_tracking/tracker.hpp` (declare `void try_reacquire(const Frame&);`)
- Test: `services/garuda-tracking/tests/test_tracking.cpp`

**Interfaces:**
- Consumes: `LostMemory` from Task 2; `states_` with `born_ms`; `appearance_distance`.
- Produces: rebinding sets `target_id_=<new id>`, `target_lost_=false`,
  clears memory, leaves `epoch_` unchanged; while pending the target
  publishes `state=="reacquiring"`, `reason=="verifying_returning_identity"`,
  `control_valid==false`.

- [x] **Step 1: Failing tests** (helpers `person(x,color,conf,label)`, `frame` already exist)

```cpp
void lose(Tracker& t,int& seq,double& ms) {                      // helper
    for(int i=0;i<30;++i){t.update(frame(seq++,ms,{}));ms+=60;}  // ~1.8 s empty
}
void reacquire_rebinds_new_id() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.32)}));ms+=60;}
    CHECK(o.target.state=="tracking");CHECK(o.target.id&&*o.target.id!=1);
    CHECK(o.target.epoch==1);CHECK(o.target.control_valid);
}
void reacquire_refuses_preexisting_id() {
    Tracker t;warm(t,{person(.3),person(.7)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;
    for(int i=0;i<60;++i){t.update(frame(seq++,ms,{person(.7)}));ms+=60;}   // other person persists
    auto o=t.snapshot(ms);
    CHECK(o.target.state!="tracking");CHECK(!o.target.id||*o.target.id==1);
}
void reacquire_gates_size_and_radius() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Detection wrong=person(.31);wrong.box.w=.5;wrong.box.h=.9;              // size ratio >2.5
    Output o;for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{wrong}));ms+=60;}
    CHECK(o.target.state!="tracking");
}
void reacquire_ambiguous_pair_refused() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;
    for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.28),person(.36)}));ms+=60;}
    CHECK(o.target.state!="tracking");
}
void reacquire_pending_resets_on_switch() {
    Tracker t;warm(t);CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    t.update(frame(seq++,ms,{person(.32,3)}));ms+=60;                        // candidate A appears
    t.update(frame(seq++,ms,{person(.32,3)}));ms+=60;
    for(int i=0;i<10;++i){t.update(frame(seq++,ms,{person(.32,9)}));ms+=800;}// B far apart in time
    auto o=t.snapshot(ms);CHECK(o.target.state!="tracking");
}
void reacquire_appearance_gate() {
    Tracker t;warm(t,{person(.3,2)});CHECK(t.select(1,3,1130));
    int seq=4;double ms=1180;lose(t,seq,ms);
    Output o;for(int i=0;i<25;++i){o=t.update(frame(seq++,ms,{person(.31,60)}));ms+=60;}
    CHECK(o.target.state!="tracking");                                       // different colour refused
}
```

- [x] **Step 2: Run to fail.**
- [x] **Step 3: Implement `try_reacquire`** (called from `update` after track
  births when `target_lost_ && lost_memory_ && (!owner_||!owner_->active())`):
  expire memory past the window; else collect candidates over `states_`
  passing: label match; confirmed/observed/!ambiguous; confidence ≥
  `birth_confidence`; `s.born_ms > memory.last_seen_ms || id==memory.lost_id`;
  width and height ratio vs memory box each within `reacquire_size_ratio`;
  center distance ≤ `min(2.0, (reacquire_radius + reacquire_radius_growth *
  (f.capture_ms-memory.lost_ms)/1000) * max(memory.box.w,memory.box.h))`;
  appearance distance ≤ `appearance_gate` when both sides carry histograms.
  Fused score `.6*appearance(0.5 neutral when absent) + .4*distance/radius`;
  if ≥2 candidates and best−second < `ambiguity_margin` the frame is
  refused. A sole winner advances pending (same rules as `TargetOwner`:
  reset when id differs or gap > `reacquire_gap_ms`; bind when hits ≥
  `reacquire_hits` and span ≥ `reacquire_confirm_ms`... bind = set
  `target_id_`, clear `target_lost_`, clear memory). While pending,
  `snapshot` renders `reacquiring`/`verifying_returning_identity` with
  `control_valid=false`.
- [x] **Step 4: Run to pass**, full suite `ctest` (all 7 binaries).
- [x] **Step 5: Commit** `feat: gated re-acquire with pending confirmation`.

### Task 4: Replay evaluation + evidence + docs

**Files:**
- Create: `bench/results/2026-09-12-reacquire/README.md` (+ score JSONs)
- Modify: `docs/decisions.md` (dated entry), `docs/superpowers/specs/...-follow-platform-and-reacquire-design.md` (acceptance numbers filled)

**Interfaces:**
- Consumes: `make_replay_input.py`, `mot_to_replay.py`, `score_lock_replay.py`, native `garuda-track-replay`.

- [x] **Step 1:** Rebuild the native test/replay binaries; rerun the three
  baselines (recorded controlled + old streams, MOT17-02 gid 19 with 1 s and
  3 s outages) with the hardened tracker at defaults.
- [x] **Step 2:** Score with `score_lock_replay.py`; verify wrong_identity==0
  everywhere and the 3 s outage recovers ≤1 s after return; capture the
  recorded-stream control_valid delta.
- [x] **Step 3:** Add at least two more MOT17 sequences (05, 09) with the
  same outage pattern; verify wrong_identity==0.
- [x] **Step 4:** Write the evidence README with the numbers; update
  decisions.md; commit `docs(bench): re-acquire evaluation evidence`.
