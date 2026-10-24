#!/usr/bin/env python3
"""How 'jumpy' is the published lock box in an F1 capture?

Written for on-board fix round 7 (Ruling 24), to test the owner's report that the follow display is
"all over the place" against the capture itself: is the LOCK box moving erratically, or is something
else on screen doing the moving? On run 12 the answer was the latter — the lock box's own motion is
smooth (median step 0.5 px/row, zero jumps over 80 px) and the churn is the GUI drawing every SDK
tracker track, including sub-0.2-confidence junk. See bench/benchlog.md, F1 section, "Round 7".

Input is a capture in the same one-row-per-SSE-event format the other tools in this directory read
(`<unix_ts> <json>` per line, gzipped or not — sse_capture_flush.py writes it), and only rows whose
`lock.identity_locked` is true take part. Reported, all from `lock`:

  * states            — row counts per `lock.state`, so the locked fraction is visible at a glance.
  * centre step       — distance the published `lock.box` centre moved since the previous locked row
                        (median / p90 / max, px per row). This is the "jumpiness" measure itself.
  * jumps > threshold — steps over `jump_px` (default 80), split by what happened at that row: the
                        lock's `id` changed, or the id is the same but the previous rows were a
                        detection gap (`observation_valid` false — i.e. the box had been frozen and
                        snapped on re-acquisition), or the same id was live throughout, which is the
                        only category that would mean the box itself is unstable.
  * detection gaps    — runs of consecutive `observation_valid == false` rows while locked, i.e. how
                        long the box is coasting at a time (count, median, p90, max, in rows).

A row's step is measured against the previous LOCKED row, and the counter resets whenever the lock is
dropped, so a gap in the lock itself never shows up as one enormous jump.

usage: jumpiness.py <capture[.gz]> [jump_px=80]
"""
import gzip, json, statistics as st, sys

path = sys.argv[1]
thr = float(sys.argv[2]) if len(sys.argv) > 2 else 80.0
opener = gzip.open if path.endswith(".gz") else open
prev = None
rows = 0
disp, jumps, jumps_idchange, jumps_after_gap, jumps_same_id_live = [], 0, 0, 0, 0
states = {}
gap_lengths = []
gap = 0
idch = 0
first = None
examples = []
for line in opener(path, "rt"):
    ts, _, js = line.partition(" ")
    ts = float(ts)
    first = first if first is not None else ts
    d = json.loads(js)
    L = d["lock"]
    rows += 1
    states[L["state"]] = states.get(L["state"], 0) + 1
    if not L["identity_locked"]:
        prev = None
        continue
    box = L.get("box")
    if L["observation_valid"]:
        if gap:
            gap_lengths.append(gap)
        gap = 0
    else:
        gap += 1
    if box and prev and prev[1]:
        pcx, pcy = prev[1]["x"] + prev[1]["w"] / 2, prev[1]["y"] + prev[1]["h"] / 2
        cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
        dist = ((cx - pcx) ** 2 + (cy - pcy) ** 2) ** 0.5
        disp.append(dist)
        if dist > thr:
            jumps += 1
            if L["id"] != prev[0]:
                jumps_idchange += 1
                idch += 1
            elif prev[2] > 0:
                jumps_after_gap += 1
            else:
                jumps_same_id_live += 1
            if len(examples) < 8:
                examples.append((round(ts - first, 2), round(dist), prev[0], L["id"], L["state"], prev[2]))
    prev = (L["id"], box, gap)
print("%s rows=%d states=%s" % (path, rows, states))
if disp:
    print("lock-box centre step (px/row): median %.1f  p90 %.1f  max %.0f" % (st.median(disp), sorted(disp)[int(0.9 * len(disp))], max(disp)))
    print("jumps > %.0f px: %d (%.1f%% of locked rows) — with id change %d, first row after a detection gap %d, same id while live %d"
          % (thr, jumps, 100.0 * jumps / len(disp), jumps_idchange, jumps_after_gap, jumps_same_id_live))
if gap_lengths:
    print("detection gaps while locked: %d gaps, median %d rows, p90 %d rows, max %d rows" % (len(gap_lengths), st.median(gap_lengths), sorted(gap_lengths)[int(0.9 * len(gap_lengths))], max(gap_lengths)))
print("examples (t, px, id_before, id_after, state, gap_rows_before):", examples)
