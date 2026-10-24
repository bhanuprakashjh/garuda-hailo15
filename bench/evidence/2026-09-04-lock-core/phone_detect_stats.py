#!/usr/bin/env python3
"""Detector-side statistics for one class over a capture window: how often the multi-object tracker
had a LIVE (non-coasting) box of that class at all, how confident it was, how many distinct ids it
handed out for it, and how often two live boxes of that class overlapped in one frame. Plus a
`person` reference line and the row-count breakdown of `lock.class`.

This is the companion to `lock_metrics.py`: that script measures what the LOCK CORE did, this one
measures what the DETECTOR gave it to work with. Run 10e is why it exists — the phone routine's
`obs_valid 95 %` looked like an excellent run until this script showed the detector held a live
`cell phone` box on only 5.9 % of the same rows (bench/benchlog.md, "Run 10e — phone: detector
starvation and a silent false lock"). A lock-side metric that looks healthy while the detector is
starving is the shape of a false lock, and neither column alone can say so.

Since on-board fix round 5 (Ruling 22.3) `lock.class` is the class of the core's last associated
observation rather than the class frozen at lock(), so the `lock class rows` line is now a real
readout of what the lock followed; before that fix it could only ever print one value.

Reads `.gz` transparently, same convention as `lock_metrics.py`. Input format is
`"<unix_time> <json>"` per line; times are seconds since the capture's first row, both bounds
inclusive.

usage: phone_detect_stats.py <capture[.gz]> [label="cell phone"] [t0_rel_s=0] [t1_rel_s=inf]
       phone_detect_stats.py run10e_routine5_phone.txt.gz "cell phone" 97.5 900
"""
import gzip
import json
import statistics as st
import sys

if len(sys.argv) < 2:
    sys.exit(__doc__)

path = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else "cell phone"
t0 = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
t1 = float(sys.argv[4]) if len(sys.argv) > 4 else float("inf")
opener = gzip.open if path.endswith(".gz") else open
first = None
rows = live = dup = 0
confs, ids, lock_cls = [], set(), {}
person_live, person_conf = 0, []
for line in opener(path, "rt"):
    ts, _, js = line.partition(" ")
    ts = float(ts)
    first = first if first is not None else ts
    rel = ts - first
    if rel < t0 or rel > t1:
        continue
    d = json.loads(js)
    rows += 1
    L = d.get("lock", {})
    lock_cls[L.get("class", "")] = lock_cls.get(L.get("class", ""), 0) + 1
    boxes = [t for t in d.get("tracks", []) if t["label"] == label]
    lv = [t for t in boxes if not t.get("coasting")]
    if lv:
        live += 1
        confs += [t["conf"] for t in lv]
    if len(lv) >= 2:
        # Two live boxes of the same class in one frame: usually the SAME physical object detected
        # twice (run 10e's phone was routinely both a `cell phone` and a `remote`), which is what
        # feeds the tracker's id churn.
        dup += 1
    # Ids are counted over ALL boxes of the class, coasting included: a coasting entry is still an
    # identity the tracker is holding for this class.
    ids.update(t["id"] for t in boxes)
    pl = [t for t in d.get("tracks", []) if t["label"] == "person" and not t.get("coasting")]
    if pl:
        person_live += 1
        person_conf += [t["conf"] for t in pl]
if rows == 0:
    print("no rows in window")
    sys.exit(1)
print("%s rows=%d window=[%.1f,%.1f] s" % (path, rows, t0, min(t1, rel)))
print("%-12s live-box rows %5.1f%% | live conf median %s mean %s max %s | distinct ids %d | rows with >=2 live boxes %.1f%%"
      % (label, 100.0 * live / rows,
         "%.2f" % st.median(confs) if confs else "n/a", "%.2f" % st.mean(confs) if confs else "n/a",
         "%.2f" % max(confs) if confs else "n/a", len(ids), 100.0 * dup / rows))
print("%-12s live-box rows %5.1f%% | live conf median %s" % ("person", 100.0 * person_live / rows,
      "%.2f" % st.median(person_conf) if person_conf else "n/a"))
print("lock class rows:", {k or "(none)": v for k, v in sorted(lock_cls.items(), key=lambda kv: -kv[1])})
