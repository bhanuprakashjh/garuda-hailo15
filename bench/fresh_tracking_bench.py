#!/usr/bin/env python3
"""Capture fresh-node HTTP observations and report measured transport/validity statistics."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import pathlib
import statistics
import time
import urllib.error
import urllib.request

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://10.0.0.1:8099")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--output", type=pathlib.Path, required=True)
    args = ap.parse_args()
    if not 0 < args.seconds <= 3600: ap.error("seconds must be in (0, 3600]")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    utc = datetime.now(timezone.utc).isoformat()
    observations, errors = [], []
    with args.output.open("w") as out:
        while time.monotonic() - start < args.seconds:
            tick = time.monotonic()
            try:
                with urllib.request.urlopen(args.url + "/api/state", timeout=2) as r:
                    snap = json.load(r)
                row = {"elapsed_s": time.monotonic()-start, "state": snap}
                out.write(json.dumps(row, allow_nan=False) + "\n"); out.flush()
                observations.append(row)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
            time.sleep(max(0, .04 - (time.monotonic()-tick)))
    ages = [r["state"]["age_ms"] for r in observations if isinstance(r["state"].get("age_ms"), (int, float))]
    states = Counter(r["state"].get("lock", {}).get("state", "missing") for r in observations)
    invalid = []
    for r in observations:
        s = r["state"]; lock = s.get("lock", {})
        if lock.get("control_valid") and (not lock.get("observation_valid") or not s.get("timestamp_valid") or
                s.get("age_ms") is None or s["age_ms"] > s["freshness_budget_ms"] or
                lock.get("id") is None or lock.get("obs_age_ms", 1e9) > s["freshness_budget_ms"]):
            invalid.append(r["elapsed_s"])
    def percentile(values, q):
        return sorted(values)[min(len(values)-1, int((len(values)-1)*q))] if values else None
    report = {"utc_start": utc, "url": args.url, "requested_seconds": args.seconds,
              "elapsed_seconds": time.monotonic()-start, "http_samples": len(observations),
              "http_errors": errors, "lock_states_samples": dict(states),
              "age_ms": {"median": statistics.median(ages) if ages else None,
                         "p95": percentile(ages, .95), "max": max(ages) if ages else None},
              "validity_invariant_violations": invalid,
              "labels_samples": dict(Counter(t["label"] for r in observations for t in r["state"].get("tracks", []))),
              "epochs_observed": sorted(set(r["state"].get("lock", {}).get("epoch", 0) for r in observations))}
    if len(observations) >= 2:
        first, last = observations[0], observations[-1]
        elapsed = last["elapsed_s"] - first["elapsed_s"]
        report["processed_frames_per_second"] = (
            last["state"]["diag"]["frames"]-first["state"]["diag"]["frames"])/elapsed
        report["rejected_frames_delta"] = last["state"]["diag"]["rejected_frames"]-first["state"]["diag"]["rejected_frames"]
        report["record_failed"] = last["state"]["diag"].get("record_failed")
    path = args.output.with_suffix(".summary.json")
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(bool(invalid) or not observations)

if __name__ == "__main__":
    raise SystemExit(main())
