#!/usr/bin/env python3
"""Print the lock/track timeline of a timestamped SSE capture (sse_capture.py output).
One line per change of (lock id, lock coasting, set of track ids, coasting ids); time relative to the first snapshot.
Then a summary: each coasting episode's duration and whether the id survived (same id live again) or died (new id)."""
import json, sys
rows = []
for line in open(sys.argv[1]):
    t, _, js = line.partition(" ")
    d = json.loads(js)
    ids = tuple(sorted((tr["id"], tr["label"]) for tr in d["tracks"]))
    coasting = tuple(sorted(tr["id"] for tr in d["tracks"] if tr["coasting"]))
    rows.append((float(t), d["lock"]["id"], d["lock"]["coasting"], ids, coasting))
if not rows:
    sys.exit("empty capture")
t0 = rows[0][0]
prev = None
for t, lid, lc, ids, co in rows:
    key = (lid, lc, ids, co)
    if key != prev:
        print("%7.2fs lock=%s%s tracks=%s coasting=%s" % (t - t0, lid, " (coasting)" if lc else "", list(ids), list(co)))
        prev = key
print("--- coasting episodes of the locked track:")
ep_start, ep_id = None, None
for t, lid, lc, ids, co in rows:
    if lc and ep_start is None:
        ep_start, ep_id = t, lid
    elif ep_start is not None and not lc:
        if lid == ep_id:
            outcome = "SURVIVED (same id %s live again)" % ep_id
        elif lid is None:
            outcome = "TRACK DIED (lock None)"
        else:
            outcome = "LOCK MOVED to live id %s (re-acquire rule; coasted id %s not returned)" % (lid, ep_id)
        print("  id %s coasted %.2fs -> %s" % (ep_id, t - ep_start, outcome))
        ep_start = None
if ep_start is not None:
    print("  id %s still coasting at end of capture (%.2fs)" % (ep_id, rows[-1][0] - ep_start))
print("snapshots:", len(rows), "span: %.1fs" % (rows[-1][0] - t0))
