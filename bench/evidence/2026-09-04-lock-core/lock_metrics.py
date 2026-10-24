#!/usr/bin/env python3
"""Lock-focused metrics over one or more timestamped SSE captures (the M1 capture script's format,
bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py: "<unix_time> <json>" per line
against http://<board>:8098/api/events, shim cap 10 Hz) -- built for F1 lock core
(services/garuda-perception/include/garuda/lock_core.hpp; snapshot fields emitted by
services/garuda-perception/src/snapshot.cpp; published semantics: hosts/hailo15l/README.md
"10. Lock core"; benchmark ask: docs/superpowers/specs/2026-09-02-hailo15l-perception-node-design.md
§8.2's "Lock-focused benchmark" bullet). Reads `.gz` inputs transparently, same convention as
bench/evidence/2026-09-03-tracker-engine-captures/compare_{person,phone}_runs.py.

Per capture, computes:

  - **re-locks** (`relocks`): count of changes in `lock.epoch`, EXCLUDING the capture's first
    non-zero epoch (the first lock of the session is not a re-lock). `LockCore` bumps `epoch` on
    every successful `lock()` and never resets it (`lock_core.cpp`), so an epoch change means the
    node genuinely started a NEW lock: a click, a target change, or a post-LOST hand-over. This is
    the column that answers "did the lock move to a different physical object".
  - **tracker id churn ridden through** (`id_churn`): count of rows where `lock.identity_locked` is
    true on both this row and the previous row, `lock.epoch` is unchanged between them, and
    `lock.id` differs -- the underlying multi-object tracker renumbered the SAME object and
    `LockCore` held on through it. `lock_core.cpp` deliberately lets `last_id` follow whichever
    candidate wins the gate ("the id itself is not sacred"), so this is a SUCCESS metric, not a
    failure one: a high count on the phone/all-classes routine can be a good result.
    (Fix round 2, review finding I2: these two were previously one "identity switches" column,
    which could not distinguish the failure F1 exists to prevent from the success it exists to
    deliver -- both showed up as a `lock.id` change.)
  - **class switches** (`class_switches`, on-board fix round 5 / Ruling 22.4): count of rows where
    `lock.class` differs from the previous row's while `lock.identity_locked` is true on both and
    `lock.epoch` is unchanged -- the lock stayed on "the same target" while the class it publishes
    changed. Since Ruling 22.3 `lock.class` is the class of the core's last associated observation
    (`lock_core.cpp`'s `m_last_obs_cls`), not the frozen locked class, so this column can move at
    all; before that fix it was structurally always 0 and the run-10e failure it exists to catch was
    invisible. Two things produce it, and the harness cannot tell them apart from the capture alone:
    a genuine detector re-label of the same object (a phone read as `remote` for a few frames) and
    the core following something it should not have. On a single-target routine the second is the
    one that matters, which is why it joins the false-relocks alias below rather than getting its own
    verdict.
    **This column reads 0 on every capture taken before round 5, including run 10e's own** -- those
    builds published the class frozen at `lock()`, so `lock.class` structurally could not change and
    a 0 there means "this capture cannot answer", not "no class switch happened". Run 10e is exactly
    that case: re-running this harness over `run10e_routine5_phone.txt.gz` still prints
    `class switches  0` for the twelve-minute suitcase. There is no field in an old capture from
    which the metric could be reconstructed -- the class the core followed was simply never
    published -- so the honest reading is capture-version-dependent, and no attempt is made to guess
    it from `tracks[]`.
  - **false relocks**: for a SINGLE-TARGET routine (see ROUTINES.md -- every owner routine this
    harness is built for has exactly one true target in frame at a time), any re-lock is by
    construction a false one. Since round 5 this is `relocks + class_switches`, printed as that sum
    -- never including `id_churn`. Run 10e is why the sum and not `relocks` alone: the core walked
    off a `cell phone` onto a static `suitcase` and sat there for twelve minutes inside ONE epoch, so
    `relocks` was 0 and the column read a clean run (bench/benchlog.md, "Run 10e"). The
    single-target premise is a property of the routine, not something derivable from the capture, so
    the alias stays an alias -- both components are also printed on their own.
  - **LOST events**: count of rows where `lock.state == "lost"` and the previous row's state was
    NOT "lost" -- i.e. new entries into the terminal state, not a per-frame tally of every LOST
    row (LOST is sticky: once entered it holds until an explicit re-lock, `lock_core.hpp`'s state
    table).
  - **time-to-reacquire**: for each CONFIRMED -> {OCCLUDED, REACQUIRING}+ -> CONFIRMED episode (an
    occlusion that recovered), a duration in seconds; min/mean/max over every such episode in the
    capture, plus the episode count. An episode that instead reaches LOST or NONE (unlock, e.g. a
    target/click change) before recovering is NOT a reacquire -- it contributes no duration (its
    LOST event, if any, is already counted separately above) and is dropped entirely (not even as
    "untimed", below); an episode still open at end-of-capture (still OCCLUDED/REACQUIRING on the
    last row) is incomplete and also dropped, not extrapolated.

    The episode is armed the first row that leaves CONFIRMED for OCCLUDED **or REACQUIRING**
    (fix round 1: the original version only armed on a CONFIRMED->OCCLUDED transition, so a capture
    that jumps straight from CONFIRMED to REACQUIRING between two sampled rows -- a dropped SSE
    line, or a gap between samples wide enough that `occlusion_ms` had already elapsed by the next
    sample -- never armed the timer, and the later recovery was silently dropped from both the
    duration list AND the episode count, with no trace it had ever happened).

    **The duration's start is the PREVIOUS CONFIRMED row's own timestamp, not the row where
    OCCLUDED/REACQUIRING is first observed.** Chosen over "the first non-CONFIRMED row's timestamp"
    because it matches what the metric is actually meant to measure -- wall-clock time since the
    target was last truly confirmed -- and because it is exactly `LockCore`'s own definition of
    `obs_age_ms` (`lock_core.cpp`: `obs_age_ms = ts - m_last_confirmed_ts_ms`, the same quantity by
    construction): the node itself uses "time since the last confirmed row", not "time since the
    first miss we happened to sample", so the harness should reconstruct the same anchor rather than
    a sampling-dependent approximation of it. This also means a dropped/late sample no longer
    shortens the measured duration -- the anchor is the last row we know for certain the target was
    confirmed, however sparse the samples after it were.

    **`untimed_reacquisitions`**: if a capture's very first row (or the first row after a NONE/LOST
    reset) is already OCCLUDED or REACQUIRING -- no CONFIRMED row exists anywhere earlier in this
    trace to anchor a start time on -- the episode is still tracked (so a later recovery to
    CONFIRMED is not silently dropped the way the original bug dropped the skipped-OCCLUDED case),
    but with an unknown start; if it recovers, it is counted in `untimed_reacquisitions` instead of
    contributing a (fabricated) duration. Reported in the row rather than dropped. A NONE/LOST row
    therefore clears BOTH the in-progress episode and the last-CONFIRMED anchor (fix round 2, review
    finding I1): a CONFIRMED row from before a reset can never anchor an episode after it, so the
    "re-lock that misses on its next sampled frame" shape (CONFIRMED ... LOST, NONE, OCCLUDED,
    CONFIRMED -- realistic at 10 Hz SSE sampling) reports one untimed reacquisition rather than a
    fabricated multi-second duration.
  - **observation_valid fraction**: fraction of rows with `lock.observation_valid == true`.
  - **`core_miss_live`** (on-board fix round 3, Ruling 19.6): of the rows where the TRACKER ENGINE
    has a live box for the locked identity — `tracks[]` carries a **non-coasting** entry whose `id`
    equals this row's `lock.id` — the percentage where the core nevertheless reports `occluded` or
    `reacquiring`. It is the column that separates *the core failed to associate* from *the detector
    or the engine lost the target*: `obs_valid` conflates the two, because a low `obs_valid` looks
    identical whether the engine had nothing to offer or the core refused what it offered. Run 5
    (`run5_routine1_walk.txt.gz`) is the motivating case — `obs_valid 62%` looked like a detector
    problem, and this column read 29 % (306 of the 1048 rows where the engine had a live box for the
    locked id), which is what identified the three gate bugs Ruling 19 fixes. Purely id-based, like
    the `classify_rows.py` helper next to this file: it never re-runs any association logic, it just
    asks whether the engine's own record for the locked id was live on that row. Rows where no such
    entry exists (including every `none`/`lost` row, whose `lock.id` is null) are outside the
    denominator entirely rather than counted as successes; a capture with no such row at all reports
    `n/a`. Expected on a healthy run: single digits, ideally 0.
  - **state fractions**: none/confirmed/occluded/reacquiring/lost, each as a fraction of n (must
    sum to 1.0 -- `lock.state` is exactly one of `garuda::lock::state_name()`'s five strings on
    every row that has the field at all; any other string is an assertion error naming it, not a
    silently-dropped row).
  - **off-screen published boxes**: count of rows whose `lock.box` (the box `LockCore` itself
    publishes -- the filtered box while CONFIRMED, the frozen last-confirmed box while
    OCCLUDED/REACQUIRING, null while NONE/LOST) has its **CENTRE** outside the published frame:
    `cx = x + w/2 < 0 or > width`, or `cy = y + h/2 < 0 or > height`, with `width`/`height` from that
    row's `frame` object when it has one and 1280x720 otherwise (a substitution the printed row
    states). Rows with a null `lock.box` contribute nothing. Expected 0 on a real run; a nonzero count
    means the thing the user sees as "what's locked" is no longer on screen at all.
    Fix round 3 (on-board fix round 1, Ruling 16.3): this used to count a box that crossed the frame
    edge *at all* (`x < 0 or y < 0 or x+w > width or y+h > height`), which flagged 109 rows of run 1
    for a target that had genuinely walked out at the right edge -- its last confirmed box legitimately
    overhung the boundary by a few px, and a detector box for a person at the edge of frame is
    routinely clipped-looking rather than wrong. The centre test asks the question the metric is for:
    is the published lock still pointing at something on screen?
    Fix round 2 (review finding I5): this used to read the `tracks[]` entry sharing the row's
    `lock.id`, because `lock.box` did not exist -- which measured the TRACKER ENGINE's coasting box
    (ByteTrack extrapolates it, `bytetrack.cpp`'s `bbox += vel`; the hailo adapter freezes it), a
    separate, pre-existing behaviour rather than anything F1 does. That reading is why a real pre-F1
    capture (`bench/evidence/2026-09-03-tracker-engine-captures/phone.txt`) shows track id 35 at
    x=-9092 while `lock.id` was 32 -- a genuine example of the engines' extrapolation running away,
    but not a measurement of the lock core. Comparing the two boxes on real data is Recommendation 4
    of the review (one mono-engine run alongside the hailo runs), still deferred.
  - **max uncertainty_px**: max of `lock.uncertainty_px` over the capture.

Fields absent from a capture print "n/a" rather than being guessed, checked once against the first
row's `lock` object:
  - no `state` key (a pre-F1 capture): re-locks / id churn / false relocks / LOST events /
    time-to-reacquire / observation_valid fraction / state fractions / max uncertainty_px are all
    "n/a";
  - no `epoch` key (an F1 capture from before the final-fix wave): re-locks, id churn, class
    switches and false relocks are all "n/a" -- every one of them is defined in terms of the epoch,
    and none can be reconstructed from `lock.id` alone;
  - no `box` key (likewise): off-screen published boxes is "n/a".
`n` and `span` never depend on any of them and are always computed, which is how this script runs
cleanly over the earlier (pre-F1) captures too, e.g.
bench/evidence/2026-09-03-tracker-engine-captures/phone.txt. An empty capture (0 lines) prints
"EMPTY CAPTURE (n/a all metrics)" and skips all computation rather than crashing on an empty list.

usage: lock_metrics.py <file> [<file> ...]
"""
import gzip
import json
import sys


def load(path):
    """Read a timestamped SSE capture: "<unix_time> <json>" per line. Skips blank lines and any
    comment/shell lines a hand-annotated capture file might carry (leading '#' or '$', matching the
    style of bench/evidence/2026-09-03-m1-coast-window.txt) and any line that fails to parse as
    JSON, so an annotated file is tolerated the same way a raw sse_capture.py dump is."""
    rows = []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("$"):
                continue
            t, sep, js = line.partition(" ")
            if not sep:
                continue
            try:
                ts = float(t)
                d = json.loads(js)
            except (ValueError, json.JSONDecodeError):
                continue
            rows.append((ts, d))
    return rows


DEFAULT_FRAME = (1280, 720)
STATE_NAMES = ("none", "confirmed", "occluded", "reacquiring", "lost")


def is_offscreen_box(box, fw, fh):
    """True if the CENTRE of `box` (a lock.box dict) is outside the fw x fh frame -- see the module
    docstring for why the centre and not any-edge-crossing."""
    cx = box["x"] + box["w"] / 2.0
    cy = box["y"] + box["h"] / 2.0
    return not (0 <= cx <= fw and 0 <= cy <= fh)


def compute(rows):
    """Returns a dict of every metric this module documents, with None where the capture lacks the
    fields a metric is defined on (see the module docstring's "n/a" rules). Never raises on an empty
    `rows` -- callers must check for that separately (see `report`); this function assumes at least
    one row."""
    n = len(rows)
    first_lock = rows[0][1].get("lock", {})
    has_lock_core = "state" in first_lock
    has_epoch = "epoch" in first_lock
    has_lock_box = "box" in first_lock

    # `diag` (on-board fix round 9): per-frame stage counters, so a capture alone can answer "where
    # did the boxes go" without re-running the pipeline. Reported as MEANS over the rows that carry
    # the field, and a value of -1 ("this engine cannot see that stage", e.g. raw_dets under the
    # hailo engine, where the SDK TrackerStage hides the pre-tracker detection list) is excluded from
    # its own mean rather than dragged into it as a number -- a mean of -1 and 12 would be a
    # fabrication. A key whose every row is -1 reports "n/a", which is the honest reading. Absent
    # from every pre-round-9 capture, in which case the whole line is simply not printed.
    DIAG_KEYS = ("raw_dets", "sdk_tracks", "live_raw", "published", "core_candidates")
    has_diag = isinstance(rows[0][1].get("diag"), dict)
    diag_mean = {}
    if has_diag:
        for k in DIAG_KEYS:
            vals = [d["diag"][k] for _, d in rows
                    if isinstance(d.get("diag"), dict) and isinstance(d["diag"].get(k), int)
                    and d["diag"][k] >= 0]
            diag_mean[k] = (sum(vals) / len(vals)) if vals else None

    # Off-screen published boxes: LockCore's own published box (lock.box), not the tracker engine's
    # tracks[] entry -- see the module docstring.
    off_screen_ts = []
    frame_default_used = False
    if has_lock_box:
        for t, d in rows:
            box = d.get("lock", {}).get("box")
            if not box:
                continue
            frame = d.get("frame") or {}
            fw, fh = frame.get("width"), frame.get("height")
            if fw is None or fh is None:
                fw, fh = DEFAULT_FRAME
                frame_default_used = True
            if is_offscreen_box(box, fw, fh):
                off_screen_ts.append(t)

    result = {
        "n": n,
        "span": rows[-1][0] - rows[0][0],
        "off_screen_count": len(off_screen_ts) if has_lock_box else None,
        "off_screen_ts": off_screen_ts,
        "frame_default_used": frame_default_used,
        "has_lock_core": has_lock_core,
        "has_epoch": has_epoch,
        "has_lock_box": has_lock_box,
        "has_diag": has_diag,
        "diag_mean": diag_mean,
    }
    if not has_lock_core:
        return result

    state_counts = {name: 0 for name in STATE_NAMES}
    obs_valid_count = 0
    uncertainty_max = 0.0

    # core_miss_live (Ruling 19.6): denominator = rows where tracks[] holds a NON-coasting entry
    # with id == lock.id; numerator = those of them where lock.state is occluded/reacquiring.
    core_miss_live_num = 0
    core_miss_live_den = 0

    # Fix round 2 (review finding I2): the old single "identity switches" column, split.
    relocks = 0            # lock.epoch changes, excluding the capture's first non-zero epoch
    id_churn = 0           # lock.id changes WITHIN one epoch while identity_locked
    class_switches = 0     # lock.class changes WITHIN one epoch while identity_locked (round 5)
    prev_epoch = None
    seen_nonzero_epoch = bool(first_lock.get("epoch")) if has_epoch else False
    prev_locked, prev_id, prev_cls = False, None, None

    lost_events = 0
    prev_state = None

    reacquire_durations = []
    untimed_reacquisitions = 0
    # `occ_start` anchors an in-progress OCCLUDED/REACQUIRING episode: a float (the previous
    # CONFIRMED row's timestamp) once a start time is known, the sentinel "unknown" if we are mid an
    # episode whose start predates anything CONFIRMED we've seen in this trace (capture opens
    # mid-episode, or a prior NONE/LOST reset without ever seeing a CONFIRMED row after it before
    # the next occlusion -- both mean there is no CONFIRMED row to anchor on), or None when not
    # currently in an episode. `last_confirmed_t` is the previous row's timestamp whenever that row
    # was CONFIRMED -- exactly the anchor `occ_start` is armed with, see the module docstring.
    occ_start = None
    last_confirmed_t = None

    for t, d in rows:
        lock = d["lock"]
        state = lock["state"]
        # An unknown state string is a schema mismatch (a renamed state, a capture from a different
        # build), not a row to quietly leave out of fractions that must sum to 1.0.
        if state not in state_counts:
            raise AssertionError(
                "unknown lock.state %r at t=%r (expected one of %s)" % (state, t, ", ".join(STATE_NAMES)))
        state_counts[state] += 1
        if lock["observation_valid"]:
            obs_valid_count += 1
        uncertainty_max = max(uncertainty_max, lock["uncertainty_px"])

        locked, lid, lcls = lock["identity_locked"], lock["id"], lock.get("class")

        # The engine's own view of the locked id on this row (id-based, no re-association).
        if lid is not None and any(
                t.get("id") == lid and not t.get("coasting") for t in (d.get("tracks") or [])):
            core_miss_live_den += 1
            if state in ("occluded", "reacquiring"):
                core_miss_live_num += 1

        epoch = lock.get("epoch")
        if has_epoch:
            if prev_epoch is not None and epoch != prev_epoch:
                if prev_epoch == 0 and not seen_nonzero_epoch:
                    pass          # 0 -> N: this capture's FIRST lock, not a re-lock
                else:
                    relocks += 1
            if epoch:
                seen_nonzero_epoch = True
            if prev_locked and locked and epoch == prev_epoch and lid != prev_id:
                id_churn += 1
            # Round 5 (Ruling 22.4): same guard as id churn -- both rows locked, same epoch -- but on
            # the class field. Rows where the lock holds no identity carry an empty class and are
            # excluded by the `prev_locked and locked` test, so a lock/unlock boundary never counts.
            if prev_locked and locked and epoch == prev_epoch and lcls != prev_cls:
                class_switches += 1
            prev_epoch = epoch
        prev_locked, prev_id, prev_cls = locked, lid, lcls

        if state == "lost" and prev_state != "lost":
            lost_events += 1

        if state == "confirmed":
            if occ_start == "unknown":
                untimed_reacquisitions += 1
            elif occ_start is not None:
                reacquire_durations.append(t - occ_start)
            occ_start = None
            last_confirmed_t = t
        elif state in ("occluded", "reacquiring"):
            if occ_start is None:
                # First row of a new episode -- covers both the ordinary CONFIRMED->OCCLUDED start
                # and the direct CONFIRMED->REACQUIRING jump (fix round 1) identically, since both
                # anchor on the same `last_confirmed_t`. If no CONFIRMED row has been seen yet in
                # this trace (capture opens mid-episode), the start is genuinely unknown.
                occ_start = last_confirmed_t if last_confirmed_t is not None else "unknown"
            # else: already mid-episode (occ_start, known or "unknown", carries forward unchanged).
        elif state in ("lost", "none"):
            occ_start = None          # episode failed to recover -- not a reacquire (timed or untimed)
            # ...and the anchor goes with it (fix round 2, review finding I1): a CONFIRMED row from
            # before this reset must never time an episode that starts after it.
            last_confirmed_t = None

        prev_state = state

    result.update({
        "state_frac": {k: v / n for k, v in state_counts.items()},
        "obs_valid_frac": obs_valid_count / n,
        "core_miss_live_num": core_miss_live_num,
        "core_miss_live_den": core_miss_live_den,
        "core_miss_live_frac": (core_miss_live_num / core_miss_live_den) if core_miss_live_den else None,
        "relocks": relocks if has_epoch else None,
        "id_churn": id_churn if has_epoch else None,
        "class_switches": class_switches if has_epoch else None,
        "false_relocks": (relocks + class_switches) if has_epoch else None,
        "lost_events": lost_events,
        "reacquire_durations": reacquire_durations,
        "untimed_reacquisitions": untimed_reacquisitions,
        "uncertainty_max": uncertainty_max,
    })
    return result


def format_row(name, m):
    if m is None:
        return "%-40s EMPTY CAPTURE (n/a all metrics)" % name

    # "n/a" wherever the capture lacks the field the metric is defined on -- never a substituted 0.
    off_s = "%4d" % m["off_screen_count"] if m["has_lock_box"] else " n/a"
    frame_note = " [frame default %dx%d]" % DEFAULT_FRAME if m["frame_default_used"] else ""

    lines = []
    if not m["has_lock_core"]:
        lines.append(
            "%-40s n=%-5d %6.1fs | states n/a (pre-F1 capture) | obs_valid n/a | "
            "core_miss_live n/a | "
            "relocks n/a (false relocks n/a) | id churn n/a | class switches n/a | "
            "LOST events n/a | "
            "reacq n/a (0 eps, 0 untimed) | off-screen boxes %s | max uncertainty_px n/a%s"
            % (name, m["n"], m["span"], off_s, frame_note)
        )
    else:
        sf = m["state_frac"]
        rd = m["reacquire_durations"]
        reacq_s = (
            "%.2f/%.2f/%.2fs" % (min(rd), sum(rd) / len(rd), max(rd)) if rd else " n/a / n/a / n/a"
        )
        relocks_s = "%2d" % m["relocks"] if m["has_epoch"] else "n/a"
        churn_s = "%2d" % m["id_churn"] if m["has_epoch"] else "n/a"
        # Round 5 (Ruling 22.4): the false-relocks alias is relocks + class_switches, so the two
        # components stay visible on their own and the alias is the number a single-target routine
        # is judged on.
        cls_sw_s = "%2d" % m["class_switches"] if m["has_epoch"] else "n/a"
        false_s = "%2d" % m["false_relocks"] if m["has_epoch"] else "n/a"
        # core_miss_live carries its own denominator: the percentage alone is unreadable without
        # knowing how many rows the engine actually had a live box for.
        cml_s = ("%3d%% (%d/%d)" % (int(100 * m["core_miss_live_frac"]),
                                    m["core_miss_live_num"], m["core_miss_live_den"])
                 if m["core_miss_live_frac"] is not None else "n/a (0 rows)")
        lines.append(
            "%-40s n=%-5d %6.1fs | states none/confirmed/occluded/reacquiring/lost = "
            "%2d%%/%2d%%/%2d%%/%2d%%/%2d%% | obs_valid %3d%% | core_miss_live %s | "
            "relocks %s (false relocks %s) | "
            "id churn %s | class switches %s | LOST events %2d | "
            "reacq min/mean/max %s (%d eps, %d untimed) | "
            "off-screen boxes %s | max uncertainty_px %6.2f%s"
            % (
                name, m["n"], m["span"],
                int(100 * sf["none"]), int(100 * sf["confirmed"]), int(100 * sf["occluded"]),
                int(100 * sf["reacquiring"]), int(100 * sf["lost"]),
                int(100 * m["obs_valid_frac"]),
                cml_s,
                # "false relocks" = relocks + class switches, never id churn (round 5, Ruling 22.4)
                relocks_s, false_s,
                churn_s, cls_sw_s,
                m["lost_events"], reacq_s, len(rd), m["untimed_reacquisitions"],
                off_s, m["uncertainty_max"], frame_note,
            )
        )
        if rd:
            lines.append(
                "%-40s reacquire durations (s): %s" % (name, ", ".join("%.2f" % x for x in rd))
            )
    # Round 9: one line of stage-by-stage means, only when the capture carries `diag` at all.
    if m.get("has_diag"):
        dm = m["diag_mean"]
        lines.append(
            "%-40s diag (means) raw_dets %s | sdk_tracks %s | live_raw %s | published %s | core_candidates %s"
            % (name, *["%.2f" % dm[k] if dm.get(k) is not None else "n/a"
                       for k in ("raw_dets", "sdk_tracks", "live_raw", "published", "core_candidates")])
        )
    if m["off_screen_ts"]:
        lines.append(
            "%-40s off-screen at t=%s"
            % (name, ", ".join("%.2f" % x for x in m["off_screen_ts"]))
        )
    return "\n".join(lines)


def report(name, path):
    rows = load(path)
    m = compute(rows) if rows else None
    print(format_row(name, m))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for path in sys.argv[1:]:
        report(path, path)
