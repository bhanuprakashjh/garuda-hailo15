"""Fresh viewer envelope -> SDK contract. No clock synchronization assumptions."""
import math
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "interfaces"))
from garuda_interfaces import TargetObservation


def ns(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 9e12:
        raise ValueError("invalid milliseconds")
    return round(value * 1_000_000)


def from_fresh(snapshot):
    if snapshot["tracker_contract"] != "garuda.fresh.v1":
        raise ValueError("unsupported fresh contract")
    lock = snapshot["lock"]
    width, height = snapshot["frame"]["width"], snapshot["frame"]["height"]
    if any(type(v) is not int or not 0 < v <= 8192 for v in (width, height)):
        raise ValueError("invalid source geometry")
    bbox = lock["box"]
    if bbox is not None:
        bbox = (bbox["x"]/width, bbox["y"]/height, bbox["w"]/width, bbox["h"]/height)
    confidence = 0.
    # lock.id is the stable lock identity; the bound MOT track is lock.track_id
    # (older recordings carried the MOT id in lock.id and have no track_id).
    mot_id = lock.get("track_id", lock["id"])
    matches = [t for t in snapshot["tracks"] if t["id"] == mot_id]
    if lock["control_valid"]:
        if len(matches) != 1 or matches[0]["label"] != lock["class"] or matches[0]["ambiguous"] or matches[0]["coasting"]:
            raise ValueError("selected observation missing or ambiguous")
        confidence = matches[0]["conf"]
        image = snapshot["image_target"]
        if image["valid"] is not True or bbox is None:
            raise ValueError("contradictory image target")
        x, y, w, h = bbox
        if any(type(image[k]) not in (float, int) or not math.isfinite(image[k]) or abs(image[k]-v) > 1e-6
               for k, v in (("u", x+w/2), ("v", y+h/2), ("width_fraction", w), ("height_fraction", h))):
            raise ValueError("image target geometry mismatch")
    sample = ns(snapshot["sample_monotonic_ms"])
    capture = ns(snapshot["capture_monotonic_ms"])
    if snapshot["timestamp_valid"] and abs(ns(snapshot["age_ms"])-(sample-capture)) > 2:
        raise ValueError("inconsistent source age")
    return TargetObservation(
        source_id=snapshot["source_id"], stream_id=snapshot["stream_id"], clock_domain=snapshot["clock_domain"],
        sequence=snapshot["sequence"], capture_ns=capture, publish_ns=ns(snapshot["publish_monotonic_ms"]),
        sample_ns=sample, freshness_ns=ns(snapshot["freshness_budget_ms"]), valid_for_ns=ns(snapshot["valid_for_ms"]),
        observation_age_ns=ns(lock["obs_age_ms"]), epoch=lock["epoch"], track_id=mot_id, label=lock["class"],
        bbox=bbox, confidence=confidence, position_std_fraction=lock["uncertainty_px"]/max(width, height),
        timestamp_valid=snapshot["timestamp_valid"], observation_valid=lock["observation_valid"],
        control_valid=lock["control_valid"], state=lock["state"], reason=lock["reason"])
