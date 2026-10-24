#!/usr/bin/env python3
"""Controlled core replay of paired capture metadata; NOT end-to-end replay.

Warm up from the first recorded input, then select at an explicitly chosen
recorded observed lock. Missing pre-capture state prevents exact startup parity.
Recorded detector inputs/scheduling stay fixed even when tracker outputs change.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    paths = sorted(args.capture.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))
    records = [json.loads(p.read_text()) for p in paths]
    if not 0 <= args.select_index < len(records):
        raise ValueError("selection index outside capture")
    for previous, current in zip(records, records[1:]):
        if current["frame"]["sequence"] != previous["frame"]["sequence"] + 1:
            raise ValueError("non-contiguous tracker updates")
    selected = records[args.select_index]
    lock = selected["output"]["lock"]
    if not lock["observation_valid"] or not lock["control_valid"]:
        raise ValueError("selection must reference a recorded valid observation")
    box = lock["box"]
    cfg = json.loads(args.profile.read_text())["tracking"]
    cfg["recovery_diagnostics"] = not args.no_diagnostics
    for override in args.set:
        key, value = override.split("=", 1)
        cfg[key] = json.loads(value)
    lines = []
    for index, record in enumerate(records):
        lines.append(json.dumps(record["frame"]))
        if index == args.select_index:
            lines.append(json.dumps({"cmd": "lock_point", "x": box["x"] + box["w"] / 2,
                                     "y": box["y"] + box["h"] / 2,
                                     "sequence": record["frame"]["sequence"],
                                     "now_ms": record["frame"]["now_ms"]}))
    with tempfile.TemporaryDirectory(prefix="garuda-core-replay-") as tmp:
        config_path = Path(tmp) / "tracking.json"
        config_path.write_text(json.dumps(cfg))
        proc = subprocess.run([str(args.binary.resolve()), "-", str(config_path)],
                              input="\n".join(lines) + "\n", text=True,
                              capture_output=True, check=True, timeout=60)
    outputs = [json.loads(line) for line in proc.stdout.splitlines()]
    if len(outputs) != len(records) + 1:
        raise ValueError("unexpected replay output count")
    ack = outputs.pop(args.select_index + 1)
    if ack != {"ok": True}:
        raise ValueError(f"selection failed: {ack}")
    if any(not out["accepted"] for out in outputs):
        raise ValueError("replay rejected an input frame")
    rows = [{"index": i, "sequence": r["frame"]["sequence"],
             "live_lock": r["output"]["lock"], "output": o}
            for i, (r, o) in enumerate(zip(records, outputs))]
    evaluated = rows[args.select_index + 1:]
    observed = [r for r in evaluated if r["output"]["lock"]["reason"] == "observed"]
    summary = {
        "scope": "fixed-input core replay, explicit selection after warmup; not live accuracy",
        "capture": str(args.capture.resolve()), "frames": len(rows),
        "select_index": args.select_index, "evaluated_frames": len(evaluated),
        "binary_sha256": sha(args.binary), "profile_sha256": sha(args.profile),
        "metadata_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in paths)).hexdigest(),
        "config": cfg,
        "reasons": dict(Counter(r["output"]["lock"]["reason"] for r in evaluated)),
        "live_reasons": dict(Counter(r["live_lock"]["reason"] for r in evaluated)),
        "reason_parity_frames": sum(r["output"]["lock"]["reason"] == r["live_lock"]["reason"] for r in evaluated),
        "observed_indices": [r["index"] for r in observed],
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "replay.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--select-index", type=int, required=True)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=JSON")
    parser.add_argument("--no-diagnostics", action="store_true")
    run(parser.parse_args())
