"""Tests for lock_metrics.py. Plain assert-style test functions (the convention every other
test_*.py under bench/ and services/ uses; see pytest.ini's --import-mode=importlib), loaded via
importlib.util so this runs regardless of pytest's import-mode/rootdir resolution. Expected numbers
in test_synthetic_capture_full_metrics are derived BY HAND against synth_capture.py's ROWS -- see
that file's own docstring for the row-by-row narrative these numbers come from; nothing here is
copied from a program's own output.

Run: python3 -m pytest bench/evidence/2026-09-04-lock-core/test_lock_metrics.py -v
     or, with no pytest installed: python3 bench/evidence/2026-09-04-lock-core/test_lock_metrics.py
"""
import gzip
import importlib.util
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def _load_module():
    spec = importlib.util.spec_from_file_location("lock_metrics", HERE / "lock_metrics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lm = _load_module()
SYNTHETIC_GZ = HERE / "synthetic_capture.txt.gz"


def test_synthetic_capture_full_metrics():
    """Hand-computed against synth_capture.py's 19 rows (see that file's docstring for the full
    narrative, including fix round 1's added episode 4):

    - n=19, span = 1.80 - 0.00 = 1.80s.
    - State counts by row: none {t=0.00, t=1.20} = 2; confirmed {0.10, 0.20, 0.50, 0.60, 1.30, 1.50,
      1.60, 1.80} = 8; occluded {0.30, 0.70, 1.40} = 3; reacquiring {0.40, 0.80, 0.90, 1.70} = 4;
      lost {1.00, 1.10} = 2. 2+8+3+4+2=19. Fractions /19: none 2/19, confirmed 8/19, occluded 3/19,
      reacquiring 4/19, lost 2/19 (sums to 1.0).
    - observation_valid true exactly on the 8 confirmed rows -> 8/19 (matching LockCore's own
      invariant: a winner is found iff CONFIRMED -- lock_core.cpp's update()).
    - re-locks (lock.epoch changes, excluding this capture's first non-zero epoch): the epoch column
      is 0 once (t=0.00), 1 for t=0.10..1.20, 2 for t=1.30..1.80. Two changes: 0->1 at t=0.10 (the
      capture's FIRST lock -- excluded by definition) and 1->2 at t=1.30 (the explicit re-lock onto
      the phone). Total = 1.
    - id churn (lock.id changes within one epoch, both rows identity_locked): walking
      (identity_locked, epoch, id) row by row, the only consecutive pair with both sides locked, the
      same epoch and a different id is t=0.50 (T,1,5) -> t=0.60 (T,1,6); every other locked->locked
      pair (including every pair from t=1.30 through t=1.80, all epoch 2 / id 9) keeps the same id,
      the t=1.20 -> t=1.30 pair spans an unlock (t=1.20 is not identity_locked) AND an epoch change,
      and every pair spanning a lock/unlock boundary has at least one side identity_locked=false so
      is excluded by construction. Total = 1.
    - class switches (round 5, Ruling 22.4 -- lock.class changes within one epoch while both rows are
      identity_locked): the class column is '' at t=0.00, 'person' for t=0.10..0.90, '' on the two
      lost rows and t=1.20, then 'cell phone' for t=1.30..1.80. The only two changes of the VALUE are
      'person' -> '' (t=0.90 -> t=1.00, where the later row is not identity_locked) and
      '' -> 'cell phone' (t=1.20 -> t=1.30, where the EARLIER row is not identity_locked and the
      epoch also changes) -- both excluded by the same both-rows-locked/same-epoch guard that
      excludes them from id churn. Total = 0, which is the honest answer for this fixture: the class
      change in it is the deliberate re-lock onto the phone, already counted once in re-locks.
      false relocks = relocks + class switches = 1 + 0 = 1, unchanged from before round 5.
    - LOST events: one run of consecutive "lost" rows (t=1.00, t=1.10); t=1.00 is preceded by
      "reacquiring" so it counts once, t=1.10 is preceded by "lost" so it does not count again.
      Total = 1.
    - reacquire durations (fix round 1's anchor rule: duration is measured from the PREVIOUS
      CONFIRMED row's own timestamp, not the first OCCLUDED/REACQUIRING row -- see
      lock_metrics.py's module docstring):
      - Episode 1: leaves CONFIRMED at t=0.30 (OCCLUDED); the previous CONFIRMED row is t=0.20;
        recovers at t=0.50 -> duration 0.50-0.20=0.30s.
      - Episode 2: leaves CONFIRMED at t=0.70 (OCCLUDED), previous CONFIRMED row t=0.60; runs
        occluded->reacquiring->reacquiring->LOST (t=1.00) -- reaches LOST before any CONFIRMED, so
        it is dropped entirely (no duration, not even "untimed" -- it never recovered; already
        reflected in the LOST-events count above).
      - Episode 3: leaves CONFIRMED at t=1.40 (OCCLUDED), previous CONFIRMED row t=1.30; recovers
        at t=1.50 -> duration 1.50-1.30=0.20s.
      - Episode 4 (the fix round 1 regression case -- direct CONFIRMED->REACQUIRING jump, OCCLUDED
        never observed): leaves CONFIRMED at t=1.70 (REACQUIRING, not OCCLUDED), previous CONFIRMED
        row t=1.60; recovers at t=1.80 -> duration 1.80-1.60=0.20s. Under the pre-fix code, this
        episode's timer would never have armed (it only checked for a CONFIRMED->OCCLUDED
        transition), so this duration -- and this episode's very existence -- would have been
        silently missing from the output.
      So durations = [0.30, 0.20, 0.20], min 0.20, mean (0.30+0.20+0.20)/3 = 0.2333..., max 0.30,
      over 3 episodes. untimed_reacquisitions = 0 -- every episode in THIS fixture starts from a
      known CONFIRMED row; the "capture opens mid-episode, no CONFIRMED row to anchor on" case is
      covered separately in test_untimed_reacquisition_when_capture_starts_mid_episode below, not
      mixed into this fixture's linear narrative.
    - off-screen boxes (read off lock.box, not tracks[] -- review finding I5 -- and counted when the
      box's CENTRE leaves the frame, fix round 3 / Ruling 16.3): the only such row is t=0.40, whose
      box -60,101,50x100 has centre (-60+25, 101+50) = (-35, 151), i.e. cx < 0. Every other non-null
      lock.box has its centre well inside 1280x720 (the furthest right is t=1.80's 615,305,40x60 ->
      centre (635, 335)), and the rows with a null lock.box (t=0.00, the two LOST rows, t=1.20)
      contribute nothing. Total = 1, at t=0.40.
      Note the t=0.40 row's tracks[] entry is ALSO off-screen (x=-9999) and is deliberately no longer
      counted: that box is the tracker engine's extrapolation, not what LockCore publishes.
    - core_miss_live (on-board fix round 3, Ruling 19.6) = rows where lock.state is occluded or
      reacquiring while tracks[] holds a NON-coasting entry whose id equals lock.id, over the rows
      where such an entry exists at all. Walking the fixture's tracks[] column: the 8 CONFIRMED rows
      (0.10, 0.20, 0.50, 0.60, 1.30, 1.50, 1.60, 1.80) each carry exactly one live entry with that
      row's lock.id; t=0.80 (REACQUIRING id 6) and t=1.70 (REACQUIRING id 9) do too -- the two rows
      the fixture added for this metric. t=0.40's only entry is COASTING, t=0.30/0.70/0.90/1.40's
      tracks[] are empty, and the none/lost rows have lock.id null, so none of those five is in the
      denominator. Denominator 8 + 2 = 10, numerator 2 -> 2/10 = 0.20.
    - max uncertainty_px: the uncertainty_px column is
      0,5.0,5.2,9.0,20.0,6.0,6.5,11.0,22.0,30.0,30.0,30.0,0,4.0,8.0,5.0,5.5,15.0,6.0 (row order) --
      max = 30.0, first reached at t=0.90 and held through t=1.00/t=1.10 (LockCore never predicts
      again once LOST -- lock_core.cpp's LOST early-return); the new episode-4 rows (5.5/15.0/6.0)
      never approach it.
    """
    rows = lm.load(str(SYNTHETIC_GZ))
    assert len(rows) == 19

    m = lm.compute(rows)
    assert m["n"] == 19
    assert abs(m["span"] - 1.80) < 1e-9
    assert m["has_lock_core"] is True

    sf = m["state_frac"]
    assert sf["none"] == 2 / 19
    assert sf["confirmed"] == 8 / 19
    assert sf["occluded"] == 3 / 19
    assert sf["reacquiring"] == 4 / 19
    assert sf["lost"] == 2 / 19
    assert abs(sum(sf.values()) - 1.0) < 1e-9

    assert m["obs_valid_frac"] == 8 / 19
    assert m["core_miss_live_den"] == 10
    assert m["core_miss_live_num"] == 2
    assert m["core_miss_live_frac"] == 2 / 10
    assert m["has_epoch"] is True and m["has_lock_box"] is True
    assert m["relocks"] == 1
    assert m["id_churn"] == 1
    assert m["class_switches"] == 0
    assert m["false_relocks"] == 1
    assert m["lost_events"] == 1

    rd = m["reacquire_durations"]
    assert len(rd) == 3
    assert abs(rd[0] - 0.30) < 1e-9
    assert abs(rd[1] - 0.20) < 1e-9
    assert abs(rd[2] - 0.20) < 1e-9
    assert m["untimed_reacquisitions"] == 0

    assert m["off_screen_count"] == 1
    assert len(m["off_screen_ts"]) == 1
    assert abs(m["off_screen_ts"][0] - 0.40) < 1e-9

    assert abs(m["uncertainty_max"] - 30.0) < 1e-9

    row = lm.format_row("synthetic", m)
    assert "core_miss_live  20% (2/10)" in row
    assert "relocks  1 (false relocks  1)" in row
    assert "id churn  1" in row
    assert "class switches  0" in row
    assert "LOST events  1" in row
    assert "off-screen boxes    1" in row
    assert "reacq min/mean/max 0.20/0.23/0.30s (3 eps, 0 untimed)" in row
    assert "reacquire durations (s): 0.30, 0.20, 0.20" in row
    assert "[frame default" not in row   # every row of this fixture carries its own frame object


def test_synthetic_capture_via_gz_matches_plain():
    """The committed fixture is gzipped; re-reading the same text uncompressed must produce
    byte-identical parsed rows -- proves load()'s `.gz` transparency doesn't alter the data (same
    convention as compare_person_runs.py / compare_phone_runs.py's own `gzip.open` handling)."""
    with gzip.open(SYNTHETIC_GZ, "rt") as f:
        plain_text = f.read()
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(plain_text)
        rows_plain = lm.load(path)
    finally:
        os.unlink(path)
    rows_gz = lm.load(str(SYNTHETIC_GZ))
    assert rows_plain == rows_gz


def test_pre_f1_capture_reports_na_for_every_lock_core_metric():
    """A pre-F1 capture (lock.id/class/coasting only -- the exact shape every capture under
    bench/evidence/2026-09-03-tracker-engine-captures/ has, confirmed by inspection) must not crash,
    and must report n/a for every lock-core-only metric while still computing n and span. Since the
    final-fix wave (review finding I5) that includes off-screen boxes: the metric now reads
    `lock.box`, which a pre-F1 capture does not carry -- the tracks[] entries below are deliberately
    off-screen to prove the harness no longer counts them (that box is the tracker engine's, not
    LockCore's)."""
    rows = [
        (100.0, {"lock": {"id": 7, "class": "person", "coasting": False},
                 "tracks": [{"id": 7, "label": "person", "conf": 0.9,
                             "x": -50, "y": -50, "w": 10, "h": 10, "coasting": True}],
                 "frame": {"width": 1280, "height": 720}}),
        (100.1, {"lock": {"id": 7, "class": "person", "coasting": False},
                 "tracks": [{"id": 7, "label": "person", "conf": 0.9,
                             "x": 10, "y": 10, "w": 10, "h": 10, "coasting": False}],
                 "frame": {"width": 1280, "height": 720}}),
    ]
    m = lm.compute(rows)
    assert m["has_lock_core"] is False
    assert m["has_epoch"] is False
    assert m["has_lock_box"] is False
    assert m["n"] == 2
    assert abs(m["span"] - 0.1) < 1e-9
    assert m["off_screen_count"] is None
    assert "state_frac" not in m
    assert "relocks" not in m

    out = lm.format_row("pre-f1", m)
    assert "states n/a (pre-F1 capture)" in out
    assert "core_miss_live n/a" in out
    assert "relocks n/a (false relocks n/a)" in out
    assert "id churn n/a" in out
    assert "class switches n/a" in out
    assert "LOST events n/a" in out
    assert "reacq n/a (0 eps, 0 untimed)" in out
    assert "max uncertainty_px n/a" in out
    assert "off-screen boxes  n/a" in out


def test_f1_capture_without_epoch_or_box_reports_na_for_those_columns_only():
    """An F1 capture taken BEFORE the final-fix wave has the six original lock-core fields but no
    `epoch` and no `box`: re-locks / id churn / false relocks and off-screen boxes must all read
    n/a, while every other lock-core metric is still computed normally. Two hand-built rows,
    CONFIRMED then OCCLUDED, with a DIFFERENT lock.id on each -- under the old harness that pair was
    an 'identity switch'; without an epoch there is no way to tell a re-lock from id churn, so the
    honest answer is n/a rather than either number."""
    base = {"class": "person", "quality": 0.8, "obs_age_ms": 0.0, "uncertainty_px": 7.5}
    rows = [
        (10.0, {"lock": dict(base, id=3, coasting=False, state="confirmed",
                             identity_locked=True, observation_valid=True),
                "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (10.1, {"lock": dict(base, id=4, coasting=False, state="confirmed",
                             identity_locked=True, observation_valid=True),
                "tracks": [], "frame": {"width": 1280, "height": 720}}),
    ]
    m = lm.compute(rows)
    assert m["has_lock_core"] is True
    assert m["has_epoch"] is False and m["has_lock_box"] is False
    assert m["relocks"] is None and m["id_churn"] is None
    assert m["class_switches"] is None and m["false_relocks"] is None
    assert m["off_screen_count"] is None
    assert m["state_frac"]["confirmed"] == 1.0
    assert m["obs_valid_frac"] == 1.0
    assert abs(m["uncertainty_max"] - 7.5) < 1e-9

    out = lm.format_row("f1-pre-fixwave", m)
    # Both rows carry an empty tracks[], so nothing is in core_miss_live's denominator: the honest
    # answer is "no rows to measure", never a substituted 0 %.
    assert m["core_miss_live_den"] == 0 and m["core_miss_live_frac"] is None
    assert "core_miss_live n/a (0 rows)" in out
    assert "relocks n/a (false relocks n/a)" in out
    assert "id churn n/a" in out
    assert "class switches n/a" in out
    assert "off-screen boxes  n/a" in out
    assert "obs_valid 100%" in out


def test_offscreen_uses_lock_box_centre_and_states_the_default_frame():
    """The off-screen metric reads lock.box and counts a box whose CENTRE has left the frame
    (fix round 3 / Ruling 16.3 -- a box merely overhanging an edge is normal for a target at the edge
    of frame, and flagged 109 legitimate rows of run 1). Hand-built, five rows, all hand-derived:
      row 0 (t=0.0): box 1250,600,100,100, frame 1280x720 -> centre (1300, 650): cx > 1280 -> OFF.
      row 1 (t=0.1): box 10,10,50,50 -> centre (35, 35): inside -> not counted.
      row 2 (t=0.2): box 1240,300,60,200 -> x+w = 1300 overhangs the right edge, but the centre is
             (1270, 400), inside -> NOT counted. This is exactly run 1's "target exited at the right
             edge" shape, which the old any-edge rule miscounted.
      row 3 (t=0.3): no `frame` object at all -> the 1280x720 default applies, and the row must SAY
             so; box 1260,10,60,50 -> centre (1290, 35): cx > 1280 -> OFF.
      row 4 (t=0.4): null box (LOST) -> contributes nothing.
    Expected: 2 off-screen rows (t=0.0 and t=0.3) and the frame-default note in the printed row."""
    rows = [
        (0.0, {"lock": _lock(1, "confirmed", True, True, 1, box={"x": 1250, "y": 600, "w": 100, "h": 100}),
               "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (0.1, {"lock": _lock(1, "confirmed", True, True, 1, box={"x": 10, "y": 10, "w": 50, "h": 50}),
               "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (0.2, {"lock": _lock(1, "confirmed", True, True, 1, box={"x": 1240, "y": 300, "w": 60, "h": 200}),
               "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (0.3, {"lock": _lock(1, "confirmed", True, True, 1, box={"x": 1260, "y": 10, "w": 60, "h": 50}),
               "tracks": []}),
        (0.4, {"lock": _lock(None, "lost", False, False, 1, box=None), "tracks": [],
               "frame": {"width": 1280, "height": 720}}),
    ]
    m = lm.compute(rows)
    assert m["off_screen_count"] == 2
    assert [round(t, 2) for t in m["off_screen_ts"]] == [0.0, 0.3]
    assert m["frame_default_used"] is True
    out = lm.format_row("offscreen", m)
    assert "off-screen boxes    2" in out
    assert "[frame default 1280x720]" in out


def test_unknown_state_string_is_an_assertion_error_naming_it():
    """A capture carrying a lock.state this harness does not know (a renamed state, a different
    build) must fail loudly, naming the value -- not be silently admitted into fractions that are
    documented to sum to 1.0."""
    rows = [(0.0, {"lock": dict(_lock(1, "confirmed", True, True, 1), state="uncertain"),
                   "tracks": [], "frame": {"width": 1280, "height": 720}})]
    try:
        lm.compute(rows)
    except AssertionError as e:
        assert "uncertain" in str(e)
    else:
        raise AssertionError("compute() accepted an unknown lock.state")


def test_untimed_reacquisition_when_capture_starts_mid_episode():
    """Fix round 1: a capture whose very first row is already REACQUIRING (no CONFIRMED row exists
    anywhere earlier in this trace -- e.g. the SSE capture started a moment after occlusion_ms had
    already elapsed) must not fabricate a start time, and must not silently drop the episode either
    if it later recovers. Two hand-built rows:

      row 0 (t=500.0): REACQUIRING, id=42, identity_locked=true, observation_valid=false -- the
        very first row of this trace; `last_confirmed_t` is still None at this point, so entering
        this episode arms `occ_start = "unknown"`, not a fabricated timestamp.
      row 1 (t=500.1): CONFIRMED, id=42, recovers -- since `occ_start == "unknown"`, this increments
        `untimed_reacquisitions` (to 1) rather than appending a (meaningless) duration computed from
        no real anchor.

    Expected: n=2, span=0.1s, state fractions reacquiring=1/2, confirmed=1/2, none/occluded/lost=0;
    obs_valid=1/2 (only row 1); re-locks=0 and id churn=0 (both rows carry epoch 4 -- unchanged, and
    already non-zero on the first row, so the capture opening mid-lock is not itself a re-lock -- and
    the id is 42 on both); LOST events=0; reacquire_durations=[] (empty -- nothing timed);
    untimed_reacquisitions=1; off_screen_count=0 (both lock.boxes are inside 1280x720);
    max uncertainty_px=18.0 (row 0's value, row 1's 6.0 is lower).
    """
    rows = [
        (500.0, {"lock": {"id": 42, "class": "person", "coasting": True, "state": "reacquiring",
                          "identity_locked": True, "observation_valid": False,
                          "quality": 0.3, "obs_age_ms": 1200.0, "uncertainty_px": 18.0,
                          "epoch": 4, "box": {"x": 100, "y": 100, "w": 50, "h": 100}},
                 "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (500.1, {"lock": {"id": 42, "class": "person", "coasting": False, "state": "confirmed",
                          "identity_locked": True, "observation_valid": True,
                          "quality": 0.7, "obs_age_ms": 0.0, "uncertainty_px": 6.0,
                          "epoch": 4, "box": {"x": 102, "y": 100, "w": 50, "h": 100}},
                 "tracks": [{"id": 42, "label": "person", "conf": 0.8,
                             "x": 100, "y": 100, "w": 50, "h": 100, "coasting": False}],
                 "frame": {"width": 1280, "height": 720}}),
    ]
    m = lm.compute(rows)
    assert m["n"] == 2
    assert abs(m["span"] - 0.1) < 1e-9
    assert m["has_lock_core"] is True

    sf = m["state_frac"]
    assert sf["reacquiring"] == 1 / 2
    assert sf["confirmed"] == 1 / 2
    assert sf["none"] == 0
    assert sf["occluded"] == 0
    assert sf["lost"] == 0

    assert m["obs_valid_frac"] == 1 / 2
    assert m["relocks"] == 0     # epoch 4 on both rows: no change, and 4 is already non-zero at row 0
    assert m["id_churn"] == 0
    assert m["lost_events"] == 0

    assert m["reacquire_durations"] == []
    assert m["untimed_reacquisitions"] == 1

    # core_miss_live: row 0 (REACQUIRING) has an empty tracks[] -> outside the denominator; row 1
    # (CONFIRMED) carries a live id-42 entry -> in the denominator, not a miss. 0/1 = 0 %.
    assert m["core_miss_live_den"] == 1 and m["core_miss_live_num"] == 0
    assert m["core_miss_live_frac"] == 0.0

    assert m["off_screen_count"] == 0
    assert abs(m["uncertainty_max"] - 18.0) < 1e-9

    row = lm.format_row("mid-episode", m)
    assert "reacq min/mean/max  n/a / n/a / n/a (0 eps, 1 untimed)" in row


def _lock(id_, state, identity_locked, observation_valid, epoch, uncertainty_px=5.0, box=None,
          cls="person"):
    """Minimal post-final-fix-wave `lock` object (the keys lock_metrics.py reads), for hand-built rows.
    `cls` is what the node publishes as `lock.class`: since round 5 (Ruling 22.3) that is the class of
    the core's last associated observation, and it is the empty string whenever nothing is locked."""
    return {"id": id_, "class": cls if identity_locked else "",
            "coasting": identity_locked and not observation_valid,
            "state": state, "identity_locked": identity_locked, "observation_valid": observation_valid,
            "quality": 0.8 if observation_valid else 0.3, "obs_age_ms": 0.0 if observation_valid else 700.0,
            "uncertainty_px": uncertainty_px, "epoch": epoch, "box": box}


def test_class_switches_within_one_epoch_join_the_false_relock_alias():
    """On-board fix round 5 (Ruling 22.4). Run 10e's failure in miniature: the lock walked from a
    `cell phone` onto a static `suitcase` inside ONE epoch, so `relocks` stayed 0 and the F1 metrics
    table read a clean run. `class_switches` is the column that sees it, and the false-relocks alias
    is now `relocks + class_switches`.

    Nine hand-built rows; every expected value below is read off the definition (a change of
    `lock.class` between two consecutive rows that are BOTH identity_locked and carry the SAME
    epoch), not from the program's output:

      t=0.0 CONFIRMED   id=109 ep=3 'cell phone'  -- first row: nothing before it to compare
      t=0.1 CONFIRMED   id=109 ep=3 'cell phone'  -- id same, class same: neither column
      t=0.2 CONFIRMED   id=140 ep=3 'cell phone'  -- id churn #1 (class unchanged)
      t=0.3 CONFIRMED   id=147 ep=3 'remote'      -- id churn #2 AND class switch #1
      t=0.4 REACQUIRING id=147 ep=3 'remote'      -- still locked, id and class unchanged: neither
      t=0.5 CONFIRMED   id=163 ep=3 'suitcase'    -- id churn #3 AND class switch #2
      t=0.6 CONFIRMED   id=163 ep=3 'suitcase'    -- neither
      t=0.7 NONE        id=None ep=3 ''           -- not identity_locked: the 'suitcase' -> ''
                                                     transition is excluded by the same guard that
                                                     excludes it from id churn
      t=0.8 CONFIRMED   id=200 ep=4 'person'      -- prev row not locked AND the epoch changed: this
                                                     is a RE-LOCK, counted once in `relocks`, and not
                                                     a class switch

    Expected: relocks 1 (the 3 -> 4 change; epoch 3 is already non-zero on row 0, so the capture
    opening mid-lock is not itself a re-lock), id_churn 3, class_switches 2, false_relocks = 1 + 2 =
    3. The point of the fixture is the contrast: `relocks` alone would report 1 for a capture in
    which the lock also silently changed what it claimed to be holding, twice.
    """
    F = {"width": 1280, "height": 720}

    def row(t, id_, state, locked, obs_valid, epoch, cls):
        return (t, {"lock": _lock(id_, state, locked, obs_valid, epoch, cls=cls),
                    "tracks": [], "frame": F})

    rows = [
        row(0.0, 109, "confirmed", True, True, 3, "cell phone"),
        row(0.1, 109, "confirmed", True, True, 3, "cell phone"),
        row(0.2, 140, "confirmed", True, True, 3, "cell phone"),
        row(0.3, 147, "confirmed", True, True, 3, "remote"),
        row(0.4, 147, "reacquiring", True, False, 3, "remote"),
        row(0.5, 163, "confirmed", True, True, 3, "suitcase"),
        row(0.6, 163, "confirmed", True, True, 3, "suitcase"),
        row(0.7, None, "none", False, False, 3, "suitcase"),
        row(0.8, 200, "confirmed", True, True, 4, "person"),
    ]
    m = lm.compute(rows)
    assert m["relocks"] == 1
    assert m["id_churn"] == 3
    assert m["class_switches"] == 2
    assert m["false_relocks"] == 3

    out = lm.format_row("class-switch", m)
    assert "relocks  1 (false relocks  3)" in out
    assert "id churn  3" in out
    assert "class switches  2" in out


def test_lost_or_none_clears_the_reacquire_anchor():
    """Fix round 2 (review finding I1): a LOST/NONE row must clear `last_confirmed_t`, not just
    `occ_start`. Otherwise a later episode that opens with no CONFIRMED row after the reset anchors on
    a CONFIRMED row from BEFORE it and reports a fabricated duration.

    The review's own five-row case (realistic at 10 Hz SSE sampling -- a re-lock that misses on its
    next frame is sampled as NONE -> OCCLUDED with no CONFIRMED row in between):

      t=0.0  CONFIRMED  -- the only CONFIRMED row before the reset; sets last_confirmed_t = 0.0
      t=20.0 LOST       -- reset: identity gone
      t=20.1 NONE       -- reset
      t=20.2 OCCLUDED   -- a NEW episode opens with no CONFIRMED row after the reset to anchor on
      t=20.5 CONFIRMED  -- it recovers

    Correct: durations [] and untimed_reacquisitions 1 -- we do not know when this episode started.
    Pre-fix the harness reported durations [20.5] (0.0 -> 20.5), a 20-second "time to reacquire" that
    never happened and would have been written into the benchlog as a real number.
    """
    rows = [
        (0.0, {"lock": _lock(7, "confirmed", True, True, 1), "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (20.0, {"lock": _lock(7, "lost", False, False, 1), "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (20.1, {"lock": _lock(None, "none", False, False, 1), "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (20.2, {"lock": _lock(9, "occluded", True, False, 2), "tracks": [], "frame": {"width": 1280, "height": 720}}),
        (20.5, {"lock": _lock(9, "confirmed", True, True, 2), "tracks": [], "frame": {"width": 1280, "height": 720}}),
    ]
    m = lm.compute(rows)
    assert m["reacquire_durations"] == []
    assert m["untimed_reacquisitions"] == 1
    assert m["lost_events"] == 1


def test_core_miss_live_counts_only_live_engine_boxes_for_the_locked_id():
    """On-board fix round 3 (Ruling 19.6). The column answers one question -- "did the CORE fail to
    associate a box the ENGINE still had?" -- so every way a row can fail to be evidence of that must
    be excluded from the denominator, not counted as a success. Seven hand-built rows, each covering
    one branch (expected values derived by reading the definition, not from the program's output):

      t=0.0 CONFIRMED  id=7, tracks: id 7 live      -> denominator, NOT a miss (the healthy case)
      t=0.1 OCCLUDED   id=7, tracks: id 7 live      -> denominator AND a miss  (run 5's M-A shape)
      t=0.2 REACQUIRING id=7, tracks: id 7 live     -> denominator AND a miss  (run 5's M-B shape)
      t=0.3 REACQUIRING id=7, tracks: id 7 COASTING -> NOT in the denominator: the engine had no live
                                                       box either, so this is a detector/engine miss
      t=0.4 OCCLUDED   id=7, tracks: []             -> NOT in the denominator: nothing to associate
      t=0.5 OCCLUDED   id=7, tracks: id 8 live      -> NOT in the denominator: a live box for some
                                                       OTHER object is not evidence about this lock
      t=0.6 LOST       id=None, tracks: id 7 live   -> NOT in the denominator: a null lock.id can
                                                       never match, and LOST is not an association
                                                       failure -- it is the terminal state

    Expected: denominator 3 (t=0.0, 0.1, 0.2), numerator 2 (t=0.1, 0.2) -> 2/3 = 0.6666..., printed
    as "core_miss_live  66% (2/3)" (int() truncation, matching every other percentage this harness
    prints).
    """
    def tr(id_, coasting):
        return {"id": id_, "label": "person", "conf": 0.8, "x": 10, "y": 10, "w": 50, "h": 100,
                "coasting": coasting}

    F = {"width": 1280, "height": 720}
    rows = [
        (0.0, {"lock": _lock(7, "confirmed", True, True, 1), "tracks": [tr(7, False)], "frame": F}),
        (0.1, {"lock": _lock(7, "occluded", True, False, 1), "tracks": [tr(7, False)], "frame": F}),
        (0.2, {"lock": _lock(7, "reacquiring", True, False, 1), "tracks": [tr(7, False)], "frame": F}),
        (0.3, {"lock": _lock(7, "reacquiring", True, False, 1), "tracks": [tr(7, True)], "frame": F}),
        (0.4, {"lock": _lock(7, "occluded", True, False, 1), "tracks": [], "frame": F}),
        (0.5, {"lock": _lock(7, "occluded", True, False, 1), "tracks": [tr(8, False)], "frame": F}),
        (0.6, {"lock": None, "tracks": [tr(7, False)], "frame": F}),
    ]
    rows[6][1]["lock"] = _lock(None, "lost", False, False, 1)

    m = lm.compute(rows)
    assert m["core_miss_live_den"] == 3
    assert m["core_miss_live_num"] == 2
    assert abs(m["core_miss_live_frac"] - 2 / 3) < 1e-12
    assert "core_miss_live  66% (2/3)" in lm.format_row("core-miss-live", m)


def test_empty_capture_reports_placeholder_not_a_crash():
    """load() on a zero-line file returns []; compute() must never be called on that (the caller,
    report(), guards it) -- format_row(name, None) is the empty-capture contract."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        rows = lm.load(path)
        assert rows == []
    finally:
        os.unlink(path)
    out = lm.format_row("empty", None)
    assert out == "%-40s EMPTY CAPTURE (n/a all metrics)" % "empty"


def test_real_pre_f1_capture_does_not_crash():
    """Sanity: run against a real committed pre-F1 capture (not a hand-built fixture) end to end.
    Only checks it doesn't crash and reports the n/a shape -- the exact off-screen count for this
    file is real bench data, not a hand-derived expectation, so it is not asserted here (it is
    reported in bench/benchlog.md's F1 section as a real number, not invented in this test)."""
    real = HERE.parent / "2026-09-03-tracker-engine-captures" / "phone.txt"
    if not real.exists():
        return  # evidence layout changed; this is a bonus sanity check, not the primary coverage
    rows = lm.load(str(real))
    assert len(rows) > 0
    m = lm.compute(rows)
    assert m["has_lock_core"] is False
    out = lm.format_row("phone.txt", m)
    assert "states n/a (pre-F1 capture)" in out


if __name__ == "__main__":
    import traceback
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception:
            failures += 1
            print("FAIL", name)
            traceback.print_exc()
    if failures:
        sys.exit("%d/%d test(s) failed" % (failures, len(tests)))
    print("all %d tests passed" % len(tests))
