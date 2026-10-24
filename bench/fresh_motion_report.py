#!/usr/bin/env python3
"""Summarize offline garuda-motion-probe output; never infer unlabelled accuracy."""
import argparse
import collections
import gzip
import json
import pathlib
import statistics


def summarize(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows:
        raise ValueError(f"empty probe output: {path}")
    result = {
        "file": path.name,
        "rows": len(rows),
        "reasons": dict(collections.Counter(row["reason"] for row in rows)),
        "similarity_mean_ms": statistics.mean(row["similarity_ms"] for row in rows),
        "translation_mean_ms": statistics.mean(row["translation"]["elapsed_ms"] for row in rows),
        "mask_scope": sorted({row["mask_scope"] for row in rows}),
    }
    warped = [row for row in rows if "warp" in row]
    if warped:
        if len(warped) != len(rows):
            raise ValueError("mixed labelled and unlabelled probe rows")
        result["known_warps"] = {}
        for backend in ("similarity", "translation"):
            errors = [row["warp"][backend + "_grid_max_error_px"] for row in rows]
            accepted = [error for error in errors if error is not None]
            result["known_warps"][backend] = {
                "accepted": len(accepted),
                "rejected": len(rows) - len(accepted),
                "max_accepted_grid_error_px": max(accepted) if accepted else None,
            }
        result["accuracy_scope"] = "known synthetic transforms; error at a 3x3 grid in source content pixels"
    else:
        result["accuracy_scope"] = "unknown physical camera motion; validity is not accuracy"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps([summarize(path) for path in args.inputs], indent=2))
