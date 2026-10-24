#!/usr/bin/env python3
"""Generates a synthetic timestamped SSE capture (lock_metrics.py's input format) that exercises
every metric lock_metrics.py computes, by hand-picked construction rather than a real routine --
this is a fixture, not evidence. Byte-identical output is committed as
`synthetic_capture.txt.gz` (gzip -9, deterministic given this script and this Python's json.dumps)
and is what test_lock_metrics.py's expected numbers are computed against by hand in its own
comments; re-run this script and re-gzip only if the fixture's shape ever needs to change, and
update test_lock_metrics.py's by-hand numbers in the same commit.

Nineteen rows, frame 1280x720, minimal per-row schema (only the keys lock_metrics.py reads: `lock`,
`tracks`, `frame` -- a real node snapshot carries more, see snapshot.cpp, but nothing else here is
read by the harness). Every row carries `lock.epoch` and `lock.box`, the two fields the final-fix
wave added (review findings I2/I5). Narrative (see test_lock_metrics.py for the hand-computed
numbers this produces):

  t=0.00  NONE, epoch 0, box null                 -- never locked yet
  t=0.10  CONFIRMED id=5, epoch 1 (lock() on a person) -- fresh lock, in-frame box
  t=0.20  CONFIRMED id=5, epoch 1                 -- steady (this row's t is episode 1's reacquire-
          duration anchor -- see below)
  t=0.30  OCCLUDED  id=5, epoch 1                 -- miss begins (episode 1 starts); box frozen at
          the last confirmed one
  t=0.40  REACQUIRING id=5, epoch 1, lock.box CENTRE OFF-SCREEN (-60,101 50x100 -> centre -35,151) --
          exercises the off-screen-boxes
          counter: 1 occurrence, deliberately. NOTE this is not something LockCore can actually
          publish today (its OCCLUDED/REACQUIRING box is the last confirmed box, bit-exact, and
          therefore in-frame); the row exists to prove the counter fires. A real bench run's bar is
          0 -- see lock_metrics.py's own docstring. The tracks[] entry is kept off-screen too, as a
          reminder that the ENGINE's coasting extrapolation really does run away like this
          (phone.txt id 35, x=-9092) -- the harness no longer reads it.
  t=0.50  CONFIRMED id=5, epoch 1 (recovered)     -- episode 1 succeeds; duration is measured from
          the PREVIOUS CONFIRMED row (t=0.20, fix round 1's chosen anchor -- see lock_metrics.py's
          docstring), not the first OCCLUDED row (t=0.30): 0.50-0.20=0.30s
  t=0.60  CONFIRMED id=6, epoch 1                 -- TRACKER ID CHURN (5->6, both rows locked, SAME
          epoch): the multi-object tracker renumbered the same person and LockCore rode through it.
          Counts as id churn: 1; NOT a re-lock. (Also episode 2's reacquire-duration anchor, below.)
  t=0.70  OCCLUDED  id=6, epoch 1                 -- miss begins (episode 2 starts)
  t=0.80  REACQUIRING id=6, epoch 1, tracks[] HAS a live id-6 box -- core_miss_live row #1 (on-board
          fix round 3, Ruling 19.6): the engine still sees the target, the core does not associate it
  t=0.90  REACQUIRING id=6, epoch 1                 -- no tracks[] entry: a genuine engine miss, so
          this row is OUTSIDE core_miss_live's denominator, not a failure charged to the core
  t=1.00  LOST id=6 -> published id null, epoch 1 -- episode 2 fails to recover (dropped entirely --
          not a timed OR untimed reacquisition); LOST events: 1. The node publishes a null id
          whenever identity_locked is false (review finding M5), and no box.
  t=1.10  LOST, epoch 1                           -- still lost, NOT a second LOST event (sticky)
  t=1.20  NONE, epoch 1                           -- explicit unlock (e.g. a target/click change).
          The epoch is NOT reset by unlock() -- it still names the lock that just ended.
  t=1.30  CONFIRMED id=9, epoch 2 (lock() on a phone) -- the explicit RE-LOCK: epoch 1 -> 2, the one
          re-lock in this fixture (episode 3's anchor)
  t=1.40  OCCLUDED  id=9, epoch 2                 -- miss begins (episode 3 starts)
  t=1.50  CONFIRMED id=9, epoch 2 (recovered)     -- episode 3 succeeds: 1.50-1.30=0.20s
  t=1.60  CONFIRMED id=9, epoch 2                 -- steady (episode 4's anchor)
  t=1.70  REACQUIRING id=9, epoch 2               -- FIX ROUND 1 REGRESSION CASE: direct
          CONFIRMED->REACQUIRING jump, OCCLUDED never observed in this trace (a dropped SSE sample,
          or a gap wide enough that occlusion_ms had already elapsed by the next poll) -- the bug
          this fixture row exists to catch: the original harness only armed the reacquire timer on a
          CONFIRMED->OCCLUDED transition, so this episode's later recovery would have been silently
          dropped from both the duration list and the episode count, with no trace anywhere in the
          output that it had ever happened. Also core_miss_live row #2: tracks[] carries a live id-9
          box here, so the core missed an observation the engine had
  t=1.80  CONFIRMED id=9, epoch 2 (recovered)     -- episode 4 succeeds despite skipping OCCLUDED:
          1.80-1.60=0.20s (anchored on t=1.60, the previous CONFIRMED row, same rule as every other
          episode -- proving the fix handles the direct jump identically to the ordinary path)

Expected (hand-computed, mirrored in test_lock_metrics.py):
  n=19, span=1.80s, state fractions none=2/19 confirmed=8/19 occluded=3/19 reacquiring=4/19
  lost=2/19, obs_valid=8/19, re-locks=1 (the epoch 1->2 change at t=1.30; the 0->1 change at t=0.10
  is this capture's first lock and is excluded), id churn=1 (5->6 at t=0.60, within epoch 1),
  LOST events=1, reacquire durations=[0.30, 0.20, 0.20] (min .20 mean .23333... max .30, 3
  episodes), untimed reacquisitions=0 (this fixture never opens mid-episode and never re-locks
  without a CONFIRMED row in between -- see test_lock_metrics.py's separate
  test_untimed_reacquisition_when_capture_starts_mid_episode and
  test_lost_or_none_clears_the_reacquire_anchor for those cases), off-screen boxes=1,
  max uncertainty_px=30.0, core_miss_live=2/10=20% (denominator: the 8 CONFIRMED rows, each of which
  carries a live tracks[] entry with the locked id, plus t=0.80 and t=1.70; numerator: those two.
  t=0.40's tracks[] entry is COASTING and t=0.90's tracks[] is empty, so neither is in the
  denominator; the none/lost rows have a null lock.id and can never match).

usage: synth_capture.py <outfile>  (write plain text; gzip it yourself to refresh the committed
fixture, e.g. `python3 synth_capture.py /tmp/x.txt && gzip -9 -n -c /tmp/x.txt >
synthetic_capture.txt.gz`)
"""
import json
import sys

FRAME = {"width": 1280, "height": 720}


def track(id_, label, x, y, w, h, coasting, conf=0.8):
    return {"id": id_, "label": label, "conf": conf, "x": x, "y": y, "w": w, "h": h, "coasting": coasting}


def box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def lock(id_, cls_, state, identity_locked, observation_valid, quality, obs_age_ms, uncertainty_px,
         epoch, lock_box):
    coasting = identity_locked and not observation_valid
    return {
        "id": id_, "class": cls_, "coasting": coasting, "state": state,
        "identity_locked": identity_locked, "observation_valid": observation_valid,
        "quality": quality, "obs_age_ms": obs_age_ms, "uncertainty_px": uncertainty_px,
        "epoch": epoch, "box": lock_box,
    }


ROWS = [
    (0.00, lock(None, "", "none", False, False, 0.0, 0.0, 0.0, 0, None), []),
    (0.10, lock(5, "person", "confirmed", True, True, 1.0, 0.0, 5.0, 1, box(100, 100, 50, 100)), [track(5, "person", 100, 100, 50, 100, False)]),
    (0.20, lock(5, "person", "confirmed", True, True, 0.85, 0.0, 5.2, 1, box(104, 101, 50, 100)), [track(5, "person", 104, 101, 50, 100, False)]),
    (0.30, lock(5, "person", "occluded", True, False, 0.45, 100.0, 9.0, 1, box(104, 101, 50, 100)), []),
    # The one deliberately off-screen lock.box in this fixture: centre (-35, 151), cx < 0 (the metric
    # is centre-based since fix round 3 / Ruling 16.3). See the module docstring.
    (0.40, lock(5, "person", "reacquiring", True, False, 0.30, 600.0, 20.0, 1, box(-60, 101, 50, 100)), [track(5, "person", -9999, -9999, 50, 50, True)]),
    (0.50, lock(5, "person", "confirmed", True, True, 0.88, 0.0, 6.0, 1, box(130, 105, 50, 100)), [track(5, "person", 130, 105, 50, 100, False)]),
    (0.60, lock(6, "person", "confirmed", True, True, 0.75, 0.0, 6.5, 1, box(400, 200, 55, 105)), [track(6, "person", 400, 200, 55, 105, False)]),
    (0.70, lock(6, "person", "occluded", True, False, 0.40, 150.0, 11.0, 1, box(400, 200, 55, 105)), []),
    # core_miss_live row #1 (on-board fix round 3, Ruling 19.6): the engine HAS a live (non-coasting)
    # box for the locked id 6 on this row, yet the core reports reacquiring -- a core association
    # failure, not a detector miss. Only the tracks[] entry differs from the pre-round-3 fixture; no
    # other metric reads it, so every other hand-derived number below is unchanged.
    (0.80, lock(6, "person", "reacquiring", True, False, 0.28, 700.0, 22.0, 1, box(400, 200, 55, 105)), [track(6, "person", 402, 201, 55, 105, False)]),
    (0.90, lock(6, "person", "reacquiring", True, False, 0.15, 1300.0, 30.0, 1, box(400, 200, 55, 105)), []),
    (1.00, lock(None, "", "lost", False, False, 0.0, 2000.0, 30.0, 1, None), []),
    (1.10, lock(None, "", "lost", False, False, 0.0, 2100.0, 30.0, 1, None), []),
    (1.20, lock(None, "", "none", False, False, 0.0, 0.0, 0.0, 1, None), []),
    (1.30, lock(9, "cell phone", "confirmed", True, True, 0.95, 0.0, 4.0, 2, box(600, 300, 40, 60)), [track(9, "cell phone", 600, 300, 40, 60, False)]),
    (1.40, lock(9, "cell phone", "occluded", True, False, 0.40, 80.0, 8.0, 2, box(600, 300, 40, 60)), []),
    (1.50, lock(9, "cell phone", "confirmed", True, True, 0.90, 0.0, 5.0, 2, box(610, 302, 40, 60)), [track(9, "cell phone", 610, 302, 40, 60, False)]),
    (1.60, lock(9, "cell phone", "confirmed", True, True, 0.87, 0.0, 5.5, 2, box(612, 303, 40, 60)), [track(9, "cell phone", 612, 303, 40, 60, False)]),
    # core_miss_live row #2: same shape on the phone lock, so the metric's denominator/numerator are
    # exercised across two different epochs and both non-CONFIRMED states.
    (1.70, lock(9, "cell phone", "reacquiring", True, False, 0.20, 600.0, 15.0, 2, box(612, 303, 40, 60)), [track(9, "cell phone", 613, 303, 40, 60, False)]),
    (1.80, lock(9, "cell phone", "confirmed", True, True, 0.80, 0.0, 6.0, 2, box(615, 305, 40, 60)), [track(9, "cell phone", 615, 305, 40, 60, False)]),
]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1], "w") as f:
        for t, lock_obj, tracks in ROWS:
            snap = {"v": 2, "lock": lock_obj, "tracks": tracks, "frame": FRAME}
            f.write("%.3f %s\n" % (t, json.dumps(snap)))
    print("wrote", len(ROWS), "rows ->", sys.argv[1])


if __name__ == "__main__":
    main()
