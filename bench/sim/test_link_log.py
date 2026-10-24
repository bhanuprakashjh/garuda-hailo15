import unittest

from link_log import LinkLog, px4_mode_name, short_result


class Clock:
    def __init__(self):
        self.ns = 1_000
        self.wall = 1_700_000_000.25

    def __call__(self):
        self.ns += 50_000_000
        return self.ns

    def time(self):
        self.wall += .05
        return self.wall


class LinkLogTests(unittest.TestCase):
    def log(self):
        c = Clock()
        return LinkLog(clock=c, wall=c.time)

    def test_mode_names(self):
        self.assertEqual(px4_mode_name(6 << 16), 'OFFBOARD')
        self.assertEqual(px4_mode_name((4 << 16) | (6 << 24)), 'AUTO.LAND')
        self.assertEqual(px4_mode_name((4 << 16) | (5 << 24)), 'AUTO.RTL')
        self.assertEqual(px4_mode_name(0), 'MODE0')

    def test_service_result_is_shortened_and_toned(self):
        log = self.log()
        e = log.response(dict(kind='service', action='arm', result='mavros_msgs.srv.CommandBool_Response(success=True, result=0)'))
        self.assertEqual(e['tone'], 'good'); self.assertIn('/mavros/cmd/arming: success=True, result=0', e['text'])
        e = log.response(dict(kind='service', action='offboard', result='mavros_msgs.srv.SetMode_Response(mode_sent=False)'))
        self.assertEqual(e['tone'], 'bad'); self.assertIn('/mavros/set_mode', e['text'])
        self.assertEqual(short_result('plain'), 'plain')

    def test_publications_and_wire_log_only_transitions(self):
        log = self.log()
        hover = dict(kind='setpoint', sp=dict(hover=True), ros_enu=dict(x=0., y=0., z=2., yaw_rate=0., type_mask=1507), reason='lease expired / hold', ros_topic='/mavros/setpoint_raw/local')
        move = dict(kind='setpoint', sp=dict(hover=False), ros_enu=dict(x=0., y=0., z=2., yaw_rate=-.3, type_mask=1507), reason='fresh request', ros_topic='/mavros/setpoint_raw/local')
        self.assertIsNotNone(log.response(hover))
        self.assertIsNone(log.response(hover), 'identical publication must not repeat')
        self.assertIn('move ENU vx +0.00 vy +0.00 z 2.0 yaw_rate -0.30 mask 1507 · fresh request', log.response(move)['text'])
        self.assertIsNotNone(log.wire(True, True, 'forwarded', 0., 0., -.3, 4.2))
        self.assertIsNone(log.wire(True, True, 'forwarded', 0., 0., -.31, 4.0), 'steady forwarding is not repeated')
        e = log.wire(False, True, 'lease_expired_before_dispatch', 0., 0., -.3, 160.)
        self.assertEqual(e['tone'], 'warn'); self.assertIn('rejected: lease_expired_before_dispatch (relay queue 160.0 ms)', e['text'])
        self.assertIsNotNone(log.wire(True, True, 'forwarded', 0., 0., -.3, 4.0), 'first forward after a rejection is logged')
        ids = [e['id'] for e in log.tail()]
        self.assertEqual(ids, sorted(ids)); self.assertEqual(len(ids), len(set(ids)))

    def test_requests_heartbeats_acks_and_text(self):
        log = self.log()
        self.assertIn('request #7 arm → ROS service /mavros/cmd/arming', log.request('arm', 7)['text'])
        sp = dict(vn=0., ve=0., z_ned=-2., yaw_rate=.4, hover=False)
        self.assertIn('setpoint move vn +0.00 ve +0.00 yaw_rate +0.40, lease 100 ms', log.request('setpoint', 8, sp)['text'])
        self.assertIsNone(log.request('setpoint', 9, sp))
        self.assertIsNotNone(log.request('setpoint', 10, dict(sp, hover=True)))
        self.assertIsNone(log.request('ping', 11))
        self.assertIn('OFFBOARD, armed', log.px4_heartbeat(True, 6 << 16)['text'])
        self.assertIsNone(log.px4_heartbeat(True, 6 << 16))
        self.assertIn('AUTO.LAND, armed', log.px4_heartbeat(True, (4 << 16) | (6 << 24))['text'])
        self.assertEqual(log.px4_ack('MAV_CMD_COMPONENT_ARM_DISARM', 'MAV_RESULT_ACCEPTED')['tone'], 'good')
        self.assertEqual(log.px4_ack('MAV_CMD_DO_SET_MODE', 'MAV_RESULT_TEMPORARILY_REJECTED')['tone'], 'warn')
        self.assertEqual(log.px4_text('Takeoff detected', 6)['tone'], 'info')
        self.assertEqual(log.px4_text('Failsafe enabled: no offboard', 2)['tone'], 'bad')
        self.assertTrue(all(len(e['time']) == 12 for e in log.tail()))

    def test_tail_is_bounded(self):
        log = LinkLog(maxlen=5)
        for i in range(9):
            log.add('pc', str(i))
        self.assertEqual([e['text'] for e in log.tail(3)], ['6', '7', '8'])
        self.assertEqual(log.tail()[0]['id'], 5)


if __name__ == '__main__':
    unittest.main()
