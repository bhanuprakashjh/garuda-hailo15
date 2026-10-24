"""Same-board native feed and freshness gate. No vehicle or camera command I/O."""
import json
import math
import socket
import struct
import time

from fresh_follow import FreshFollow
from fresh_target_adapter import from_fresh
from follow_controller import FollowConfig


def camera_request_bound(local, requested):
    def identity(row):
        lock=row.get('lock') or {}
        return (row.get('source_id'),row.get('stream_id'),lock.get('epoch'),lock.get('id'))
    return bool(local and requested and local.get('lock',{}).get('id') is not None
                and identity(local)==identity(requested))


def camera_response_heading(local, source):
    """Absolute +/-30 degree response, never integrate a fixed camera error."""
    reference=source.get('heading_reference_ned')
    hfov=source.get('camera_hfov')
    box=local.get('lock',{}).get('box')
    if not (box and type(reference) in (int,float) and math.isfinite(reference)
            and type(hfov) in (int,float) and math.isfinite(hfov) and .2<hfov<2.8):
        return None
    if any(type(box.get(k)) not in (int,float) or not math.isfinite(box[k]) for k in ('x','w')):
        return None
    cx=(box['x']+box['w']/2)/1280
    bearing=math.atan((2*cx-1)*math.tan(hfov/2))
    return reference+max(-math.pi/6,min(math.pi/6,bearing))


def read_packet(stream):
    # One overall deadline, including fragmented headers and ignored JPEGs.
    deadline = time.monotonic() + .5

    def read(size):
        out = bytearray()
        while len(out) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('native packet deadline')
            stream.settimeout(remaining)
            block = stream.recv(min(65536, size-len(out)))
            if not block:
                raise EOFError('native camera disconnected')
            out.extend(block)
        return bytes(out)

    kind, size = struct.unpack('!cI', read(5))
    if kind not in (b'S', b'J') or not 0 < size <= (512*1024 if kind == b'S' else 16*1024*1024):
        raise ValueError('unknown/oversize native packet')
    if kind == b'J':
        while size:
            take = min(65536, size)
            read(take)
            size -= take
        return None
    return json.loads(read(size))


class LocalCameraGate:
    """Read-only eligibility diagnostic. Explicit boot binding; no clock rebasing.

    A selected identity change creates a new diagnostic gate, NOT a follow permit.
    An eventual controller must independently require a new operator permit.
    """
    def __init__(self, clock_domain):
        if not isinstance(clock_domain, str) or not clock_domain.startswith('linux.monotonic:'):
            raise ValueError('native board boot clock required')
        self.clock_domain = clock_domain
        self.follow = None
        self.last = None
        self.reason = 'waiting_for_camera'

    def reject(self, reason):
        self.reason = reason
        if self.follow:
            self.follow.reject(reason)

    def ingest(self, row, now_ns):
        try:
            if row['clock_domain'] != self.clock_domain or row['source_id'] != 'hailo15l.imx678':
                raise ValueError('wrong native source/boot')
            if row['tracker_contract'] != 'garuda.fresh.v1':
                raise ValueError('unsupported native contract')
            times = [row[k] for k in ('capture_monotonic_ms', 'publish_monotonic_ms', 'sample_monotonic_ms')]
            if any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
                raise ValueError('invalid native clock')
            capture, publish, sample = times
            if not capture <= publish <= sample <= now_ns/1e6:
                raise ValueError('native clock order/future timestamp')
            if type(row['sequence']) is not int or row['sequence'] < 0 or not row['stream_id']:
                raise ValueError('invalid native sequence/stream')
            self.last = dict(sequence=row['sequence'], stream_id=row['stream_id'], capture_ms=capture)
            lock = row['lock']
            if lock['id'] is None:
                self.follow = None
                self.reason = 'not_selected'
                return False
            observation = from_fresh(row)
            if self.follow is None or self.follow.identity != observation.identity:
                self.follow = FreshFollow(*observation.identity, config=FollowConfig(min_height_frac=.02))
            # Source age already includes sample-capture. Charge only the remaining
            # native/ROS transport delay, once, on this shared monotonic clock.
            accepted = self.follow.ingest(observation, observation.sample_ns, now_ns)
            self.reason = self.follow.reason
            return accepted
        except (KeyError, ValueError, TypeError, OverflowError) as error:
            self.reject('invalid_native_envelope:' + str(error))
            return False

    def status(self, now_ns):
        decision = self.follow.tick(now_ns) if self.follow else None
        age = now_ns/1e6-self.last['capture_ms'] if self.last else None
        return dict(kind='camera_ros_observation', vehicle_io=False, operator_permit=False,
                    camera_frame_fresh=bool(age is not None and 0 <= age < 200),
                    would_be_fresh=bool(decision and decision.command.valid),
                    reason=decision.command.reason if decision else self.reason,
                    sequence=self.last['sequence'] if self.last else None,
                    stream_id=self.last['stream_id'] if self.last else None,
                    capture_age_ms=age,
                    observation_age_ms=decision.observation_age_upper_ns/1e6
                        if decision and decision.observation_age_upper_ns is not None else None,
                    expires_ns=decision.expires_local_ns if decision else None,
                    clock_domain=self.clock_domain, sample_ns=now_ns)
