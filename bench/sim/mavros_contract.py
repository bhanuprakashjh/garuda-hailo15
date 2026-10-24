"""Pure bench boundary: monotonic leases and MAVROS ENU message conversion."""
import math


def conservative_offset(t0, remote, t1):
    if not all(type(t) is int for t in (t0, remote, t1)) or not 0 <= t1-t0 <= 100_000_000:
        raise ValueError('clock handshake exceeds 100 ms bound')
    # Remote sample occurred between host t0 and t1. Use the oldest possible
    # source time, with 2 ms drift margin. No symmetric-network assumption.
    return remote-t1-2_000_000


def enu_setpoint(sp):
    values = [sp[k] for k in ('vn','ve','z_ned','yaw_rate')]
    if not all(type(v) in (int,float) and math.isfinite(v) for v in values):
        raise ValueError('nonfinite setpoint')
    if math.hypot(sp['vn'],sp['ve'])>1.001 or abs(sp['yaw_rate'])>.8 or not -3<=sp['z_ned']<=-.5:
        raise ValueError('outside bench envelope')
    # MAVROS setpoint_raw/local transforms ROS ENU to MAVLink NED itself.
    # Supplying NED numbers here would swap N/E and invert altitude/yaw twice.
    return dict(x=sp['ve'],y=sp['vn'],z=-sp['z_ned'],yaw_rate=-sp['yaw_rate'],type_mask=1507)


class Lease:
    def __init__(self, session):
        if not session: raise ValueError('session required')
        self.session, self.sequence, self.packet = session, 0, None

    def accept(self, packet, now):
        try:
            if packet['session']!=self.session or type(packet['sequence']) is not int or packet['sequence']<=self.sequence:
                raise ValueError('wrong session or reordered request')
            self.sequence=packet['sequence']
            end=packet['expires_ns']
            if type(end) is not int or not now<end<=now+150_000_000:
                raise ValueError('expired or excessive lease')
            enu_setpoint(packet['sp'])
            if type(packet['enabled']) is not bool:
                raise ValueError('enabled must be boolean')
            self.packet=packet
            return True
        except (KeyError,TypeError,ValueError):
            self.packet=None
            return False

    def current(self, now):
        return self.packet if self.packet and now<self.packet['expires_ns'] else None


class WirePublications:
    """One-shot binding of an actual MAVROS packet to its originating lease.

    time_boot_ms is MAVROS' uint32 truncation of PositionTarget.header.stamp.
    Unknown, repeated or expired publications cannot inherit a newer lease.
    """
    def __init__(self):
        self.requests = {}
        self.publications = {}
        self.identity = None

    def context(self, identity):
        if identity != self.identity:
            self.requests.clear();self.publications.clear()
            self.identity = identity

    def request(self, sequence, deadline, now):
        self.requests = {k:v for k,v in self.requests.items() if v > now}
        self.requests[sequence] = deadline

    def published(self, event, now):
        self.publications = {k:v for k,v in self.publications.items() if v[0] > now}
        deadline = self.requests.get(event.get('request_sequence'), 0)
        if deadline > now and type(event.get('wire_stamp_ms')) is int:
            self.publications[event['wire_stamp_ms']] = (deadline, event['sp'])

    def consume(self, stamp, values, now):
        publication = self.publications.pop(stamp, None)
        if not publication or now >= publication[0]:
            return False
        sp = publication[1]
        return not sp['hover'] and all(abs(values[k]-sp[k]) < 1e-5 for k in ('vn','ve','z_ned','yaw_rate'))


def motion_gate_reason(publication, bound, latest, deadline, values, now):
    """Explain the existing independent wire checks; do not relax any limit."""
    if publication is None:return 'unknown_or_consumed_publication'
    if now>=publication[0]:return 'origin_lease_expired'
    if not bound:return 'publication_value_mismatch'
    if now>=deadline:return 'latest_lease_expired'
    if latest is None or latest['hover']:return 'pc_hold'
    if any(abs(values[k]-latest[k])>=.08 for k in ('vn','ve','yaw_rate')):
        return 'pc_board_setpoint_disagreement'
    return 'forwarded'
