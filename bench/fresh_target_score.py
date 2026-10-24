#!/usr/bin/env python3
"""Score exact-input recordings against reviewed physical-target annotations.

These are explicitly defined selected-target metrics, not MOTChallenge IDF1/MOTA.
Unknown annotations and discontinuous sampling cannot become successful tracking time.
"""
import argparse
import collections
import copy
import hashlib
import json
import math
import pathlib
import statistics
from fresh_stream_capture import source_descriptor


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def box(value, clipped=False):
    if not isinstance(value, list) or len(value) != 4 or not all(finite(v) for v in value):
        raise ValueError("box must be finite normalized [x,y,w,h]")
    x, y, w, h = value
    if w <= 0 or h <= 0 or (clipped and (x < 0 or y < 0 or x+w > 1.000001 or y+h > 1.000001)):
        raise ValueError("invalid box extent")
    return value


def iou(a, b):
    def edges(v):
        x, y, w, h = v
        return max(0, x), max(0, y), min(1, x+w), min(1, y+h)
    ax, ay, ar, ab = edges(a); bx, by, br, bb = edges(b)
    area = max(0, min(ar, br)-max(ax, bx))*max(0, min(ab, bb)-max(ay, by))
    union = max(0, ar-ax)*max(0, ab-ay)+max(0, br-bx)*max(0, bb-by)-area
    return area/union if union > 0 else 0


def read_recording(directory):
    """Require completion, exact pixels, monotonic producer identity and output pairing."""
    summary = json.loads((directory/"summary.json").read_text())
    end = json.loads((directory/"end.json").read_text())
    request = json.loads((directory/"request.json").read_text())
    count = summary["frames"]
    if (summary.get("complete") is not True or end.get("complete") is not True or
            type(count) is not int or not 1 <= count <= 1200 or
            count != end["sent"] or count != request["frames"] or
            end["recording_id"] != request["recording_id"]):
        raise ValueError("recording is incomplete or inconsistent")
    rows = []; previous = None; paired_count = 0
    for index in range(count):
        stem = directory/f"{index:06d}"
        row = json.loads(stem.with_suffix(".json").read_text())
        f, out = row["frame"], row["output"]
        identity = [row[k] for k in ("source_id", "stream_id", "clock_domain")]
        if (row["recording_id"] != request["recording_id"] or row["sample_index"] != index or
                identity != summary["producer"] or type(f["sequence"]) is not int or f["sequence"] < 1 or
                not finite(f["capture_ms"]) or f["timestamp_valid"] is not True or
                f["sequence"] != out["sequence"] or f["capture_ms"] != out["capture_monotonic_ms"]):
            raise ValueError("recording frame/output/producer mismatch")
        if previous and (f["sequence"] <= previous["sequence"] or f["capture_ms"] <= previous["capture_ms"]):
            raise ValueError("recording sequence/time regression")
        w, h = row["input_w"], row["input_h"]
        if (any(type(v) is not int or v < 2 or v > 8192 or v % 2 for v in (w,h)) or
                row["pixel_format"] != "NV12" or row["packed_stride"] != w):
            raise ValueError("unsupported image packing")
        raw = stem.with_suffix(".nv12")
        if raw.stat().st_size != w*h*3//2 or raw.stat().st_size > 2*1024*1024:
            raise ValueError("image size mismatch")
        if hashlib.sha256(raw.read_bytes()).hexdigest() != row["nv12_sha256"]:
            raise ValueError("image hash mismatch")
        if "source_image" in row:
            paired_raw=stem.with_suffix(".source.nv12")
            source=source_descriptor(row,raw.stat().st_size,raw.stat().st_size+paired_raw.stat().st_size)
            if hashlib.sha256(paired_raw.read_bytes()).hexdigest()!=source["sha256"]:
                raise ValueError("paired source hash mismatch")
            paired_count+=1
        rows.append(row);previous = f
    if paired_count not in (0,count) or paired_count!=summary.get("paired_frames",0):
        raise ValueError("recording source-pair coverage mismatch")
    return rows


def annotation_template(rows, label):
    return {"schema": "garuda.target_truth.v1", "recording_id": rows[0]["recording_id"],
            "label": label, "target_id": "target-1", "annotator": "UNREVIEWED",
            "selection": None,
            "frames": [{"sequence": r["frame"]["sequence"], "capture_ms": r["frame"]["capture_ms"],
                        "nv12_sha256": r["nv12_sha256"],
                        **({"source_nv12_sha256":r["source_image"]["sha256"]} if "source_image" in r else {}),
                        "visibility": "unknown", "box": None,
                        "distractors": []} for r in rows]}


def validate_truth(rows, truth):
    if truth.get("schema") != "garuda.target_truth.v1" or truth["recording_id"] != rows[0]["recording_id"]:
        raise ValueError("annotation schema/recording mismatch")
    if (any(not isinstance(truth[k],str) or not truth[k] for k in ("label","target_id")) or
            len(truth["frames"]) != len(rows)):
        raise ValueError("annotation label/identity/coverage missing")
    for row, gt in zip(rows, truth["frames"]):
        if (gt["sequence"] != row["frame"]["sequence"] or gt["capture_ms"] != row["frame"]["capture_ms"] or
                gt["nv12_sha256"] != row["nv12_sha256"]):
            raise ValueError("annotation/image correspondence mismatch")
        if gt.get("source_nv12_sha256")!=row.get("source_image",{}).get("sha256"):
            raise ValueError("annotation/source image correspondence mismatch")
        if gt["visibility"] not in ("visible", "occluded", "out_of_view", "unknown"):
            raise ValueError("unknown visibility value")
        if gt["visibility"] == "visible": box(gt["box"], clipped=True)
        elif gt["box"] is not None: raise ValueError("non-visible target must not have an invented box")
        ids = {truth["target_id"]}
        for d in gt["distractors"]:
            if not isinstance(d["id"], str) or not d["id"] or d["id"] in ids:
                raise ValueError("duplicate or empty physical identity")
            ids.add(d["id"]);box(d["box"], clipped=True)
    if any(g["visibility"] != "unknown" for g in truth["frames"]) and truth.get("annotator") in (None,"","UNREVIEWED"):
        raise ValueError("reviewed annotations need annotator provenance")
    selection = truth["selection"]
    if selection is not None:
        if (type(selection["epoch"]) is not int or selection["epoch"] < 1 or
                type(selection["start_sequence"]) is not int or
                selection["start_sequence"] not in {r["frame"]["sequence"] for r in rows}):
            raise ValueError("selection must name an observed frame and positive expected epoch")


def evaluate(rows, truth, threshold=.5, confidence=.4, max_gap_ms=100):
    if not rows or not 0 < threshold <= 1 or not 0 <= confidence <= 1 or not 0 < max_gap_ms <= 250:
        raise ValueError("invalid evaluation parameters")
    validate_truth(rows, truth)
    count = collections.Counter(); details = []; episodes = []
    selection = truth["selection"]; pending = None; previous = None; last_identity = None; last_correct_id = None
    ages = []; overlaps = []; visible_ms = lost_ms = control_unavailable_ms = 0.; intervals = 0

    def close_episode(reason, at):
        nonlocal pending
        if pending is not None:
            episodes.append(dict(pending, recovered=False, censored_reason=reason, observed_until_ms=at))
            pending = None

    for row, gt in zip(rows, truth["frames"]):
        f, out = row["frame"], row["output"]; seq, now = f["sequence"], f["capture_ms"]
        lock = out["lock"]; visibility = gt["visibility"]
        if out["sequence"] != seq or out["capture_monotonic_ms"] != now:
            raise ValueError("prediction/frame mismatch")
        age = out["publish_monotonic_ms"]-now
        if not finite(age) or age < 0: raise ValueError("invalid source latency")
        ages.append(age)
        for flag in ("observation_valid", "control_valid"):
            if type(lock[flag]) is not bool: raise ValueError("invalid lock validity")
        active = selection is not None and seq >= selection["start_sequence"]
        known = visibility != "unknown"; visible = visibility == "visible"
        count[visibility+"_frames"] += 1
        candidates = []
        for d in f["detections"]:
            if not finite(d["confidence"]): raise ValueError("nonfinite detector confidence")
            db = box([d["box"][k] for k in ("x","y","w","h")])
            if visible and d["label"] == truth["label"] and d["confidence"] >= confidence:
                candidates.append(iou(db, gt["box"]))
        if visible: count["detected_target_frames"] += max(candidates, default=0) >= threshold
        predicted = None
        if lock["box"] is not None:
            w, h = out["frame"]["width"], out["frame"]["height"]
            if not finite(w) or not finite(h) or w <= 0 or h <= 0: raise ValueError("invalid output geometry")
            predicted = box([lock["box"][k]/(w if k in ("x","w") else h) for k in ("x","y","w","h")])
        target_iou = iou(predicted, gt["box"]) if predicted is not None and visible else None
        matches = []
        if predicted is not None:
            if visible and target_iou >= threshold: matches.append(truth["target_id"])
            matches.extend(d["id"] for d in gt["distractors"] if iou(predicted,d["box"]) >= threshold)
        identity = matches[0] if len(matches) == 1 else None
        correct = (active and visible and lock["observation_valid"] and identity == truth["target_id"] and
                   lock["epoch"] == selection["epoch"] and lock["class"] == truth["label"])
        current = dict(sequence=seq, capture_ms=now, visibility=visibility, active=active,
                       correct_observation=correct if active and known else None,
                       correct_control=correct and lock["control_valid"] if active and known else None,
                       matched_identity=identity, overlapping_identities=matches,
                       target_iou=target_iou, observation_valid=lock["observation_valid"], epoch=lock["epoch"])
        contiguous = (previous is not None and seq == previous["sequence"]+1 and
                      0 < now-previous["capture_ms"] <= max_gap_ms and known and
                      previous["visibility"] != "unknown" and active and previous["active"])
        if previous is not None:
            if seq <= previous["sequence"] or now <= previous["capture_ms"]:
                raise ValueError("evaluation source order regression")
            count["sequence_gap_intervals"] += seq != previous["sequence"]+1
            count["long_time_gap_intervals"] += now-previous["capture_ms"] > max_gap_ms
        same_epoch = previous is not None and lock["epoch"] == previous["epoch"]
        if not contiguous:
            close_episode("recording_gap_or_unknown_truth", previous["capture_ms"] if previous else now)
            last_identity = None;last_correct_id = None
        else:
            dt = now-previous["capture_ms"]
            if previous["visibility"] == "visible":
                visible_ms += dt;lost_ms += dt if not previous["correct_observation"] else 0;intervals += 1
                control_unavailable_ms += dt if not previous["correct_control"] else 0
        if not same_epoch:
            last_identity = None;last_correct_id = None
        if active and known:
            count["scored_selection_frames"] += 1
            count["epoch_mismatch_frames"] += lock["epoch"] != selection["epoch"]
            count["overlap_ambiguous_frames"] += len(matches) > 1 and lock["observation_valid"]
            if visible:
                count["visible_selection_frames"] += 1;count["correct_observation_frames"] += correct
                count["correct_control_frames"] += correct and lock["control_valid"]
                if lock["observation_valid"]: overlaps.append(target_iou if target_iou is not None else 0.)
                if pending is None and (not correct or not contiguous or previous["visibility"] != "visible"):
                    kind = "visible_loss" if contiguous and previous["visibility"] == "visible" else "visible_entry"
                    pending = dict(start_sequence=seq, start_ms=now, kind=kind)
                if correct and pending is not None:
                    episodes.append(dict(pending, recovered=True, recovery_sequence=seq, delay_ms=now-pending["start_ms"]))
                    pending = None
            else:
                close_episode("target_not_visible", now)
            if lock["control_valid"] and not correct:
                count["incorrect_or_unverified_control_frames"] += 1
            if lock["observation_valid"] and identity is not None:
                if last_identity is not None and last_identity != identity:
                    count["physical_identity_switches"] += 1
                last_identity = identity
                if identity != truth["target_id"]:
                    count["wrong_object_observation_frames"] += 1
                    if contiguous and same_epoch and not previous["observation_valid"]:
                        count["false_reacquisition_events"] += 1
            if correct:
                # The MOT track id lives in lock.track_id since the stable lock id
                # landed; older recordings carry it in lock.id.
                mot_id = lock.get("track_id", lock["id"])
                if last_correct_id is not None and last_correct_id != mot_id:
                    count["correct_target_mot_id_changes"] += 1
                last_correct_id = mot_id
        details.append(current);previous = current
    close_episode("end_of_recording", rows[-1]["frame"]["capture_ms"])
    visible = count["visible_frames"]; selected_visible = count["visible_selection_frames"]
    keys = ("scored_selection_frames", "visible_selection_frames", "correct_observation_frames", "correct_control_frames",
            "epoch_mismatch_frames", "overlap_ambiguous_frames", "incorrect_or_unverified_control_frames",
            "physical_identity_switches", "wrong_object_observation_frames", "false_reacquisition_events",
            "correct_target_mot_id_changes")
    return {"schema": "garuda.target_score.v1", "recording_id": truth["recording_id"],
            "scope": "source-frame selected-target metrics; no flight or detector-population accuracy claim",
            "parameters": dict(iou_threshold=threshold, confidence_threshold=confidence, max_gap_ms=max_gap_ms),
            "annotation_coverage": {k: count[k+"_frames"] for k in ("visible","occluded","out_of_view","unknown")},
            "sampling": {k: count[k] for k in ("sequence_gap_intervals","long_time_gap_intervals")},
            "detector": {"visible_frames": visible, "matched_frames": count["detected_target_frames"],
                         "target_recall": count["detected_target_frames"]/visible if visible else None},
            "selection": {**{k: count[k] if count["scored_selection_frames"] else None for k in keys},
                          "correct_visible_fraction": count["correct_observation_frames"]/selected_visible if selected_visible else None,
                          "correct_visible_control_fraction": count["correct_control_frames"]/selected_visible if selected_visible else None,
                          "observable_intervals": intervals, "visible_time_ms": visible_ms if intervals else None,
                          "visible_lost_time_ms": lost_ms if intervals else None,
                          "visible_control_unavailable_ms": control_unavailable_ms if intervals else None,
                          "observed_box_iou_median": statistics.median(overlaps) if overlaps else None,
                          "recovery_episodes": episodes},
            "recorded_capture_to_output_ms": {"median": statistics.median(ages), "max": max(ages)},
            "frames": details}


def apply_predictions(rows, path):
    """Join alternate replay/model results by exact source identities, never row proximity."""
    predictions = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(predictions) != len(rows): raise ValueError("prediction coverage mismatch")
    result = copy.deepcopy(rows)
    provenance = set()
    for row, pred in zip(result, predictions):
        for key in ("recording_id", "source_id", "stream_id", "clock_domain", "nv12_sha256"):
            if pred[key] != row[key]: raise ValueError("prediction source mismatch")
        if pred["sequence"] != row["frame"]["sequence"] or pred["capture_ms"] != row["frame"]["capture_ms"]:
            raise ValueError("prediction sequence/time mismatch")
        if not pred.get("provenance"): raise ValueError("prediction provenance missing")
        if pred.get("source_nv12_sha256")!=row.get("source_image",{}).get("sha256"):
            raise ValueError("prediction paired-source mismatch")
        if pred["output"]["frame"] != row["output"]["frame"]:
            raise ValueError("prediction full-FOV geometry mismatch")
        provenance.add(json.dumps(pred["provenance"],sort_keys=True))
        row["output"] = pred["output"]
        row["frame"]["detections"] = pred["detections"]
    if len(provenance) != 1: raise ValueError("mixed prediction provenance")
    return result, json.loads(provenance.pop())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=pathlib.Path)
    parser.add_argument("--annotations", type=pathlib.Path)
    parser.add_argument("--init-label", choices=("person", "cell phone"))
    parser.add_argument("--predictions", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--iou", type=float, default=.5)
    parser.add_argument("--confidence", type=float, default=.4)
    args = parser.parse_args()
    if bool(args.annotations) == bool(args.init_label): parser.error("choose annotations or init-label")
    if args.init_label and args.predictions: parser.error("initial annotations use the original recording")
    rows = read_recording(args.recording)
    provenance = {"kind": "same_callback_live_output", "latency_scope": "source capture to tracker output; excludes HTTP/control delivery"}
    if args.predictions: rows, provenance = apply_predictions(rows,args.predictions)
    result = annotation_template(rows,args.init_label) if args.init_label else evaluate(
        rows,json.loads(args.annotations.read_text()),args.iou,args.confidence)
    if not args.init_label: result["prediction_provenance"] = provenance
    with args.output.open("x") as file: file.write(json.dumps(result,allow_nan=False,indent=2)+"\n")


if __name__ == "__main__": main()
