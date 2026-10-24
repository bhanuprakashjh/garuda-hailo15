#!/usr/bin/env python3
"""Tally cell-phone tracking stats from one or more PC-side timestamped SSE captures
(bench/evidence/2026-09-03-m1-coast-window-scripts/sse_capture.py output: "<unix_time> <json>"
per line, http://10.0.0.1:8098/api/events, shim cap 10 Hz).

Reproduces the columns of the "Three runs" block in bench/benchlog.md's
"2026-09-03 — Hailo-15L SBC: yolov8m A/B for small-object (cell phone) tracking" section:
phone ids, lock ids, no-phone states (count + %), coasting entries, x range (min/max box x,
including off-frame coasting extrapolation), live conf mean (non-coasting cell-phone entries
only), box w mean (all cell-phone entries, live + coasting — matches the published A/B table),
longest lock (s, longest run of consecutive snapshots with an unchanged non-null lock id),
age max (ms, from the snapshot's own age_ms field). Percentage and box/x figures are truncated
(int()), not rounded, to match the published A/B table's figures for the same three captures.

A capture with zero cell-phone tracks (the routine had not started yet, or the phone was never in
view) prints "n/a" for x range / live conf mean / box w mean instead of crashing on an empty-list
mean/min/max — every other column (phone ids 0, lock ids, no-phone states 100%, coasting entries 0,
age max) is still well-defined and printed normally.

usage: compare_phone_runs.py <label> <file> [<label> <file> ...]
"""
import gzip
import json
import sys

LABEL = "cell phone"


def load(path):
    rows = []
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            t, _, js = line.partition(" ")
            rows.append((float(t), json.loads(js)))
    return rows


def tally(name, path):
    rows = load(path)
    if not rows:
        print(name, "EMPTY CAPTURE")
        return
    n = len(rows)
    t0, t1 = rows[0][0], rows[-1][0]
    span = t1 - t0

    phone_ids = set()
    lock_ids = set()
    no_phone_states = 0
    coasting_entries = 0
    xs = []
    live_confs = []
    all_ws = []
    age_max = 0

    # longest run of consecutive snapshots with the same non-null lock id
    longest_run_s = 0.0
    run_start_t = None
    run_id = None

    for t, d in rows:
        age_max = max(age_max, d.get("age_ms", 0))
        lid = d["lock"]["id"]
        if lid is not None:
            lock_ids.add(lid)
        if lid != run_id:
            if run_id is not None and run_start_t is not None:
                longest_run_s = max(longest_run_s, t - run_start_t)
            run_id = lid
            run_start_t = t if lid is not None else None

        phone_tracks = [tr for tr in d["tracks"] if tr["label"] == LABEL]
        if not phone_tracks:
            no_phone_states += 1
        for tr in phone_tracks:
            phone_ids.add(tr["id"])
            xs.append(tr["x"])
            all_ws.append(tr["w"])
            if tr["coasting"]:
                coasting_entries += 1
            else:
                live_confs.append(tr["conf"])
    # close out a run still open at end of capture
    if run_id is not None and run_start_t is not None:
        longest_run_s = max(longest_run_s, rows[-1][0] - run_start_t)

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    # xs/live_confs/all_ws are all empty together iff there is not a single cell-phone track
    # entry anywhere in the capture (phone_ids is then also empty) -- print "n/a", don't crash.
    if xs:
        x_range_s = "[%7d, %7d]" % (int(min(xs)), int(max(xs)))
    else:
        x_range_s = "[    n/a,    n/a]"
    live_conf_s = "%.2f" % mean(live_confs) if live_confs else " n/a"
    box_w_s = "%3d" % int(mean(all_ws)) if all_ws else "n/a"

    print(
        "%-16s n=%-5d %5.1fs | phone ids %3d | lock ids %3d | no-phone states %4d (%2d%%) "
        "| coasting entries %4d | x range %s | live conf mean %s | "
        "box w mean %s px | longest lock %5.1fs | age max %4d"
        % (
            name,
            n,
            span,
            len(phone_ids),
            len(lock_ids),
            no_phone_states,
            int(100.0 * no_phone_states / n),
            coasting_entries,
            x_range_s,
            live_conf_s,
            box_w_s,
            longest_run_s,
            age_max,
        )
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) % 2 != 0 or not args:
        sys.exit(__doc__)
    for i in range(0, len(args), 2):
        tally(args[i], args[i + 1])
