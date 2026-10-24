#!/usr/bin/env python3
"""Classify every row of a lock capture by `lock.state` x what the tracker engine had for the locked
id on that same row, and print the histogram.

The question it answers -- and the one `obs_valid` alone cannot -- is *whose* failure a
non-CONFIRMED row is:

  <state>/engine-live      the engine has a NON-coasting tracks[] entry with id == lock.id, so a real
                           box was on offer and the CORE did not associate it (a core failure)
  <state>/engine-coasting  the engine's own entry for that id is coasting: it had nothing fresh
                           either (a detector/engine miss the core is correctly riding through)
  <state>/track-gone       no tracks[] entry with that id at all (the engine dropped it)
  none / lost              no identity to compare against; reported as-is

Run 5 (routine 1, build 83b600c) is the capture this was written for -- it produced

    confirmed/engine-live            742   62.0%
    reacquiring/engine-live          187   15.6%
    occluded/engine-live             119    9.9%
    reacquiring/track-gone            74    6.2%
    reacquiring/engine-coasting       40    3.3%
    occluded/engine-coasting          32    2.7%
    lost                               2    0.2%

i.e. 306 of the 1048 engine-live rows (29 %) were core association failures, which is what Ruling 19
fixes. `lock_metrics.py`'s `core_miss_live` column is exactly that 306/1048 as a single number; this
script is the breakdown behind it, and `rows.py` is the per-row view underneath both.

Input format is `lock_metrics.py`'s: `"<unix_time> <json>"` per line. Plain text only -- unlike
`lock_metrics.py` this does not read `.gz`; `zcat run5_routine1_walk.txt.gz > /tmp/r5.txt` first.
The `first at` column carries the earliest row of each class as
`(t_seconds, obs_age_ms, uncertainty_px, quality)`, so a class can be looked up directly in
`rows.py`.

usage: classify_rows.py <capture>
"""
import gzip
import json
import sys
from collections import Counter


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = sys.argv[1]

    counts = Counter()
    examples = {}
    first = None
    for line in (gzip.open(path, "rt") if path.endswith(".gz") else open(path)):
        ts, sep, js = line.partition(" ")
        if not sep:
            continue
        ts = float(ts)
        if first is None:
            first = ts
        d = json.loads(js)
        lock = d.get("lock", {})
        state = lock.get("state")
        lock_id = lock.get("id")
        by_id = {t["id"]: t for t in d.get("tracks", [])}
        if state in ("none", "lost"):
            key = state
        else:
            entry = by_id.get(lock_id)
            if entry is None:
                key = state + "/track-gone"
            elif entry.get("coasting"):
                key = state + "/engine-coasting"
            else:
                key = state + "/engine-live"
        counts[key] += 1
        if key not in examples:
            examples[key] = (round(ts - first, 2), lock.get("obs_age_ms"),
                             lock.get("uncertainty_px"), lock.get("quality"))

    n = sum(counts.values())
    if not n:
        sys.exit("empty capture: %s" % path)
    for key, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("%-30s %5d  %5.1f%%   first at %s" % (key, count, 100.0 * count / n, examples[key]))


if __name__ == "__main__":
    main()
