"""Human-readable link log for the follow console: what the PC asked the board's ROS 2
node to do, what MAVROS published, what the PC packet gate forwarded or rejected to the
owned PX4, and what PX4 answered (service results, command acknowledgements, status text,
mode/arming changes). Pure bookkeeping, no ROS or MAVLink imports, so it is unit-tested.

Only transitions are logged: repeated identical setpoint publications or forwarded packets
at 20 Hz would bury the lines that matter. Counters for the steady state stay on the
relay's status (motion_forwarded / motion_rejected)."""
import collections
import re
import time

PX4_MAIN = {1: 'MANUAL', 2: 'ALTCTL', 3: 'POSCTL', 4: 'AUTO', 5: 'ACRO', 6: 'OFFBOARD',
            7: 'STABILIZED', 8: 'RATTITUDE'}
PX4_AUTO_SUB = {1: 'READY', 2: 'TAKEOFF', 3: 'LOITER', 4: 'MISSION', 5: 'RTL', 6: 'LAND',
                7: 'RTGS', 8: 'FOLLOW_TARGET', 9: 'PRECLAND'}
SERVICES = {'arm': '/mavros/cmd/arming', 'offboard': '/mavros/set_mode', 'land': '/mavros/set_mode'}


def px4_mode_name(custom_mode):
    main = (int(custom_mode) >> 16) & 0xFF
    sub = (int(custom_mode) >> 24) & 0xFF
    name = PX4_MAIN.get(main, f'MODE{main}')
    if main == 4 and sub:
        name += '.' + PX4_AUTO_SUB.get(sub, str(sub))
    return name


def short_result(result):
    """'mavros_msgs.srv.CommandBool_Response(success=True, result=0)' -> 'success=True, result=0'."""
    m = re.search(r'\((.*)\)\s*$', str(result))
    return m.group(1) if m else str(result)


class LinkLog:
    def __init__(self, maxlen=400, clock=time.monotonic_ns, wall=time.time):
        self.entries = collections.deque(maxlen=maxlen)
        self.seq = 0
        self.clock, self.wall = clock, wall
        self._request_state = self._publication_state = self._wire_state = None
        self._hold_reason = None
        self._heartbeat = None

    def add(self, lane, text, tone='info'):
        self.seq += 1
        t = self.wall()
        entry = dict(id=self.seq, host_ns=self.clock(), lane=lane, tone=tone, text=text,
                     time=time.strftime('%H:%M:%S', time.localtime(t)) + '.%03d' % int((t % 1) * 1000))
        self.entries.append(entry)
        return entry

    # PC -> board ROS node (JSON request over the owned SSH channel)
    def request(self, action, sequence, sp=None):
        if action in SERVICES:
            return self.add('pc', f'request #{sequence} {action} → ROS service {SERVICES[action]}')
        if action == 'setpoint' and sp is not None:
            hover = bool(getattr(sp, 'hover', sp.get('hover') if isinstance(sp, dict) else False))
            g = (lambda k: getattr(sp, k)) if not isinstance(sp, dict) else sp.get
            state = 'hover' if hover else f'move vn {g("vn"):+.2f} ve {g("ve"):+.2f} yaw_rate {g("yaw_rate"):+.2f}'
            if state != self._request_state:
                self._request_state = state
                return self.add('pc', f'request #{sequence} setpoint {state}, lease 100 ms')
        return None

    # board ROS node -> PC (JSON responses)
    def response(self, r):
        kind = r.get('kind')
        if kind == 'ready':
            return self.add('ros', f"board ROS 2 node ready ({r.get('architecture', '?')})", 'good')
        if kind == 'service':
            text = short_result(r.get('result'))
            ok = 'success=True' in text or 'mode_sent=True' in text
            return self.add('ros', f"service {r.get('action')} → {SERVICES.get(r.get('action'), '?')}: {text}",
                            'good' if ok else 'bad')
        if kind == 'rejected':
            return self.add('ros', f"board rejected request: {r.get('reason')}", 'warn')
        if kind == 'hold':
            if r.get('reason') != self._hold_reason:
                self._hold_reason = r.get('reason')
                return self.add('ros', f"board hold: {r.get('reason')}", 'warn')
            return None
        if kind == 'setpoint':
            sp = r.get('sp') or {}
            enu = r.get('ros_enu') or {}
            hover = bool(sp.get('hover'))
            state = (hover, r.get('reason'))
            if state != self._publication_state:
                self._publication_state = state
                self._hold_reason = None
                return self.add('ros', f"publish {r.get('ros_topic', '/mavros/setpoint_raw/local')} "
                                       f"{'hover' if hover else 'move'} ENU vx {enu.get('x', 0):+.2f} vy {enu.get('y', 0):+.2f} "
                                       f"z {enu.get('z', 0):.1f} yaw_rate {enu.get('yaw_rate', 0):+.2f} mask {enu.get('type_mask', '?')}"
                                       f" · {r.get('reason')}")
            return None
        return None

    # MAVROS -> PX4 through the PC packet gate
    def wire(self, allowed, moving, reason, vn, ve, yaw_rate, queue_ms):
        if not allowed:
            self._wire_state = None
            return self.add('gate', f'SET_POSITION_TARGET_LOCAL_NED rejected: {reason} (relay queue {queue_ms:.1f} ms)', 'warn')
        state = 'move' if moving else 'hover'
        if state != self._wire_state:
            self._wire_state = state
            return self.add('gate', f'→ PX4 SET_POSITION_TARGET_LOCAL_NED {state} vn {vn:+.2f} ve {ve:+.2f} '
                                    f'yaw_rate {yaw_rate:+.2f} · forwarded')
        return None

    def mavlink_out(self, msg_type, detail):
        return self.add('gate', f'→ PX4 {msg_type} {detail}')

    # PX4 -> (relay) -> MAVROS
    def px4_text(self, text, severity):
        tone = 'bad' if severity <= 3 else 'warn' if severity == 4 else 'info'
        return self.add('px4', f'PX4: {text}', tone)

    def px4_ack(self, command_name, result_name):
        return self.add('px4', f'PX4 ack {command_name}: {result_name}', 'good' if result_name == 'MAV_RESULT_ACCEPTED' else 'warn')

    def px4_heartbeat(self, armed, custom_mode):
        key = (bool(armed), px4_mode_name(custom_mode))
        if key != self._heartbeat:
            self._heartbeat = key
            return self.add('px4', f"PX4 heartbeat: {key[1]}, {'armed' if key[0] else 'disarmed'}", 'good' if key[0] else 'info')
        return None

    def tail(self, n=80):
        return list(self.entries)[-n:]
