# Overnight Follow Hardening Plan (2026-09-12 → 13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Owner directive: "do all things overnight and give me the best possible results" — no owner present, no live person; everything must be validated offline or on the board without a person, committed, and summarised for the morning.

**Goal:** Leave the follow path measurably stronger by morning: association that does not swap ids between look-alike people, an acquisition mode that finds small/distant targets with the five tiles but tracks with the fast single-tile + ROI path, evidence across all eleven VisDrone-SOT sequences, tuned identity gates, and one report.

**Architecture:** Same components as the follow-path plan (`2026-09-12-follow-path.md`); changes are inside `garuda::fresh::Tracker::pair_cost` (descriptor-aware association), `hosts/hailo15l/fresh_node.cpp` (tiles gated on lock state), profiles, and the bench harness (target-class inference for non-person SOT targets, sweeps).

**Spec:** `docs/superpowers/specs/2026-09-12-follow-platform-and-reacquire-design.md`; decisions.md entries of 2026-09-12 (follow path, measured verdicts, live session).

## Global Constraints

- Rules 1, 6, 7 of CLAUDE.md; absolute paths in every shell call (memory `harness-cwd-drift`); the board is restored to a running profile after every bench run; the follow profile stays the default at the end.
- Descriptor files stay under `hailo-export/`; evidence dirs stay small (gzip logs, no descriptors).
- Every tracker change: unit test in `test_tracking.cpp`/`test_target_owner.cpp`, ctest 7/7, then an offline before/after on the same replay inputs with the numbers in the benchlog.

---

### Task 1: Evidence across all VisDrone-SOT sequences (board, background)
- Prepare + probe the eight remaining sequences with `--roi` (job started 23:15).
- `sot_to_replay.py`: infer the target class from the detector's majority label on the annotated box (person / car / …) so the `roi` merge and the click work for non-person targets; skip embeddings for non-person targets.
- Embeddings (cap 64) for sequences whose target is a person; driver with histogram configs and identity configs; table in the SOT README.

### Task 2: Descriptor-aware association in the tracker
- `Tracker::pair_cost`: when both the track's last observed embedding and the detection carry a compatible embedding, add `w_e * embedding_distance` to the visual cost and forbid pairs above `association_embedding_gate` (config, default 0.5 — a loose gate; identity is still decided by the owner). Tests: a crossing of two persons with distinct descriptors keeps ids; without descriptors behaviour is unchanged (existing suite).
- Offline before/after on 024 and 086 (single/five/roi × default/identity): off-target-while-valid and MOT id switches.

### Task 3: Acquire-with-tiles, track-with-ROI node mode
- `detection_tiles: "when_unlocked"` in `fresh_node.cpp`: run the corner tiles only while no lock is active (state none/lost/expired); once locked, single tile + ROI. Profile `perception-follow.json` adopts it with `freshness_ms` 500 (tile frames are ~200 ms old) — measured on the board without a person: tiles active when unlocked (`diag.detection_tiles.reason == tiled`), rate/age recorded.
- Profile test updated.

### Task 4: Identity gate sweep (local)
- Replays of 086 and 024 (roi flavour, identity config) over `identity` gates — requires exposing `identity_max_distance` and `identity_ambiguity_margin` in the tracking config (defaults unchanged) — choose by on-target vs off-target; record and, if a clear win, set in the follow profile.

### Task 5: MOT-val multi-target sweep (local)
- For each MOT-val sequence, the three longest pedestrians, target-only drop 2.5 s from a mid-point, appearance + camera motion + crowd flag: re-acquire rate, latency, wrong-id vs OFF. Append to the VisDrone-MOT README.

### Task 6: Morning report
- `bench/results/2026-09-13-overnight/README.md` summarising every measurement with links; benchlog and decisions entries; memory; board state verified; all committed.
