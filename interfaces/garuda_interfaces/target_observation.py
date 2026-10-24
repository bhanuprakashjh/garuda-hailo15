"""Selected image target, with explicit producer clock and identity lifetime.

Source timestamps are never subtracted from a receiver's clock. A receiver must
add a measured transport upper bound and expire observations on its own clock.
This contract supplies image geometry, not range or flight authorization.
"""
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class TargetObservation:
    source_id: str
    stream_id: str                 # unique for every producer process
    clock_domain: str              # identifies the producer monotonic clock/boot
    sequence: int
    capture_ns: int
    publish_ns: int
    sample_ns: int                 # instant at which ages/remaining validity were evaluated
    freshness_ns: int
    valid_for_ns: int
    observation_age_ns: int
    epoch: int                     # increases on new selection; unlock invalidates the observation
    track_id: int | None
    label: str
    bbox: tuple | None             # x,y,w,h normalized to full source FOV
    confidence: float
    position_std_fraction: float   # std / max(source width, source height)
    timestamp_valid: bool
    observation_valid: bool
    control_valid: bool
    state: str
    reason: str
    schema: str = "garuda.target_observation.v1"

    def __post_init__(self):
        if self.schema != "garuda.target_observation.v1":
            raise ValueError("unsupported target schema")
        for name in ("source_id", "stream_id", "clock_domain", "state", "reason", "label"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 256 or (not value and name not in ("label", "reason")):
                raise ValueError(f"invalid {name}")
        for name in ("sequence", "capture_ns", "publish_ns", "sample_ns", "freshness_ns",
                     "valid_for_ns", "observation_age_ns", "epoch"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value < 2**63:
                raise ValueError(f"invalid {name}")
        if self.track_id is not None and (type(self.track_id) is not int or not 0 < self.track_id < 2**63):
            raise ValueError("invalid track_id")
        for name in ("timestamp_valid", "observation_valid", "control_valid"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"invalid {name}")
        if not 0 < self.freshness_ns <= 5_000_000_000 or not 0 <= self.valid_for_ns <= self.freshness_ns:
            raise ValueError("invalid freshness budget")
        if not 0 <= self.capture_ns <= self.publish_ns <= self.sample_ns:
            raise ValueError("source clock order")
        for name in ("confidence", "position_std_fraction"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"invalid {name}")
        if self.bbox is not None:
            if not isinstance(self.bbox, (tuple, list)) or len(self.bbox) != 4:
                raise ValueError("invalid bbox")
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in self.bbox):
                raise ValueError("invalid bbox value")
            x, y, w, h = self.bbox
            if min(x, y) < 0 or min(w, h) <= 0 or x+w > 1.000001 or y+h > 1.000001:
                raise ValueError("bbox outside source FOV")
            object.__setattr__(self, "bbox", tuple(self.bbox))
        if self.control_valid and not (self.timestamp_valid and self.observation_valid and
                self.state == "tracking" and self.epoch > 0 and self.sequence > 0 and
                self.track_id is not None and self.bbox is not None and self.label):
            raise ValueError("contradictory target validity")

    @property
    def identity(self):
        return self.source_id, self.stream_id, self.epoch

    def to_dict(self):
        value = asdict(self)
        if self.bbox is not None:
            value["bbox"] = list(self.bbox)
        return value

    @classmethod
    def from_dict(cls, value):
        if value.get("schema") != "garuda.target_observation.v1":
            raise ValueError("target schema required")
        return cls(**value)
