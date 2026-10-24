#!/usr/bin/env python3
"""Compact per-row dump of a lock capture between two relative times, for reading a capture by eye.

One line per sampled row: the published `lock` object (state, id, epoch, obs_age_ms,
uncertainty_px, quality, box) on the left, that row's whole `tracks[]` array on the right
(`id:cls conf x,y wxh`, with a trailing `C` for a coasting entry). Times are seconds since the
capture's FIRST row, matching `lock_metrics.py`'s own `span`.

This is the diagnostic that made the round-3 mechanisms visible: put the core's state next to what
the tracker engine was reporting on the same frame and the disagreement reads straight off the page
(e.g. `reacquiring ... | 1309:per 0.87 854,1 428x716` -- the engine has a live, confident box for the
very id the core says it has lost). `classify_rows.py` next to this file is the same comparison
counted over a whole capture; `lock_metrics.py`'s `core_miss_live` column is that count as a metric.

Input format is `lock_metrics.py`'s: `"<unix_time> <json>"` per line (the M1 capture script's output,
bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py). Plain text only -- unlike
`lock_metrics.py` this does not read `.gz`; `zcat run5_routine1_walk.txt.gz > /tmp/r5.txt` first.

usage: rows.py <capture> <t0_seconds> <t1_seconds>
       rows.py /tmp/r5.txt 42.5 53.2
"""
import gzip
import json
import sys


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    path, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

    first = None
    for line in (gzip.open(path, "rt") if path.endswith(".gz") else open(path)):
        ts, sep, js = line.partition(" ")
        if not sep:
            continue
        ts = float(ts)
        if first is None:
            first = ts
        rel = ts - first
        if rel < t0 or rel > t1:
            continue
        d = json.loads(js)
        lock = d.get("lock", {})
        box = lock.get("box")
        box_s = "-" if not box else "%.0f,%.0f %.0fx%.0f" % (box["x"], box["y"], box["w"], box["h"])
        tracks_s = " ".join(
            "%s:%s %.2f %.0f,%.0f %.0fx%.0f%s"
            % (t["id"], t["label"][:3], t["conf"], t["x"], t["y"], t["w"], t["h"],
               "C" if t.get("coasting") else "")
            for t in d.get("tracks", [])
        )
        print("%7.2f %-11s id=%-4s ep=%s age=%6.0f unc=%7.1f q=%.2f box=%-18s | %s"
              % (rel, lock.get("state"), lock.get("id"), lock.get("epoch"),
                 lock.get("obs_age_ms", 0), lock.get("uncertainty_px", 0), lock.get("quality", 0),
                 box_s, tracks_s))


if __name__ == "__main__":
    main()
