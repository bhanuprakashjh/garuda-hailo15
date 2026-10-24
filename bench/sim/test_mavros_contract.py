import math
import pathlib
import sys
import unittest
import queue
from unittest.mock import Mock, patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from mavros_contract import conservative_offset, enu_setpoint, Lease, WirePublications, motion_gate_reason


class ContractTests(unittest.TestCase):
    def packet(self,**kw):
        return dict(session='run',sequence=1,expires_ns=1_100_000_000,enabled=True,
                    sp=dict(vn=1.,ve=0.,z_ned=-2.,yaw_rate=.3,hover=False),**kw)

    def test_north_is_enu_y(self):
        p=enu_setpoint(self.packet()['sp'])
        self.assertEqual((p['x'],p['y'],p['z'],p['yaw_rate']),(0.,1.,2.,-.3))
        self.assertEqual(p['type_mask'],1|2|32|64|128|256|1024)

    def test_east_is_enu_x(self):
        p=enu_setpoint(dict(vn=0.,ve=1.,z_ned=-2.,yaw_rate=-.3))
        self.assertEqual((p['x'],p['y'],p['yaw_rate']),(1.,0.,.3))

    def test_nonfinite_and_limit_rejected(self):
        for key,value in [('vn',float('nan')),('ve',2.),('yaw_rate',1.),('z_ned',2.)]:
            p=self.packet()['sp'];p[key]=value
            with self.assertRaises(ValueError):enu_setpoint(p)

    def test_clock_bound_never_extends_deadline(self):
        for asymmetric_delay in (0,2_000_000,9_000_000):
            t0=1_000_000_000;true_offset=500_000_000
            remote=t0+asymmetric_delay+true_offset;t1=t0+10_000_000
            estimated=conservative_offset(t0,remote,t1)
            self.assertLessEqual(estimated,true_offset)
        with self.assertRaises(ValueError):conservative_offset(0,1,101_000_000)

    def test_expiry_and_duplicate_do_not_renew(self):
        gate=Lease('run');p=self.packet()
        self.assertTrue(gate.accept(p,1_000_000_000))
        self.assertIsNone(gate.current(1_100_000_000))
        self.assertFalse(gate.accept(p,1_050_000_000))
        self.assertIsNone(gate.current(1_050_000_000))

    def test_bad_session_future_and_expired_fail_closed(self):
        for field,value in [('session','other'),('expires_ns',2_000_000_000),('expires_ns',999_000_000),('sequence',True),('enabled','yes')]:
            p=self.packet();p[field]=value
            self.assertFalse(Lease('run').accept(p,1_000_000_000))

    def test_wire_exact_publication_once(self):
        w=WirePublications();sp=self.packet()['sp']
        w.request(1,100,0)
        w.published(dict(request_sequence=1,wire_stamp_ms=42,sp=sp),1)
        self.assertFalse(w.consume(43,sp,2))
        self.assertTrue(w.consume(42,sp,2))
        self.assertFalse(w.consume(42,sp,3))

    def test_motion_reasons_preserve_each_gate(self):
        sp=self.packet()['sp'];pub=(100,sp)
        def reason(**kw):
            args=dict(publication=pub,bound=True,latest=sp,deadline=100,values=sp,now=2)
            args.update(kw);return motion_gate_reason(**args)
        self.assertEqual(reason(),'forwarded')
        self.assertEqual(reason(publication=None),'unknown_or_consumed_publication')
        self.assertEqual(reason(now=100),'origin_lease_expired')
        self.assertEqual(reason(bound=False),'publication_value_mismatch')
        self.assertEqual(reason(deadline=2),'latest_lease_expired')
        self.assertEqual(reason(latest=dict(sp,hover=True)),'pc_hold')
        self.assertEqual(reason(latest=dict(sp,yaw_rate=.5)),'pc_board_setpoint_disagreement')

    def test_dispatch_rechecks_after_ownership_check_and_logs_after_write(self):
        from remote_mavros import RemoteMavrosVehicle, Setpoint
        for verification_delay in (0,101_000_000):
            now=[1_000_000_000];writes=[];events=[]
            v=object.__new__(RemoteMavrosVehicle)
            v.responses=queue.Queue();v.rx=queue.Queue();v.rx.put((now[0],b'wire'))
            v.pending_wire=[]
            v.remote_ready=False;v.latest_deadline=now[0]+100_000_000
            v.latest_sp=Setpoint(1.,0.,-2.,.3,False)
            v.motion_forwarded=v.motion_rejected=v.last_wire=v.first_wire=v.wire_count=0
            v.publications=WirePublications();v.publications.request(1,v.latest_deadline,now[0])
            v.publications.published(dict(request_sequence=1,wire_stamp_ms=42,sp=vars(v.latest_sp)),now[0])
            msg=Mock(vx=1.,vy=0.,z=-2.,yaw_rate=.3,type_mask=1507,coordinate_frame=1,time_boot_ms=42)
            msg.get_type.return_value='SET_POSITION_TARGET_LOCAL_NED';msg.get_msgbuf.return_value=b'wire'
            v.decoder=Mock();v.decoder.parse_buffer.return_value=[msg]
            def verify():now[0]+=verification_delay
            def record(data,**kw):events.append(data);now[0]+=500_000_000
            v._verify_simulator=verify;v.record=record;v.m=Mock()
            v.m.write.side_effect=lambda packet:writes.append(now[0])
            with patch('remote_mavros.MavlinkVehicle.poll'),patch('remote_mavros.time.monotonic_ns',side_effect=lambda:now[0]):
                v.poll()
            self.assertEqual(len(writes),0 if verification_delay else 1)
            self.assertTrue(all(t<v.latest_deadline for t in writes))
            self.assertEqual(events[0]['reason'],'lease_expired_before_dispatch' if verification_delay else 'forwarded')

    def test_cross_channel_metadata_wait_is_bounded_and_cannot_override_hold(self):
        from remote_mavros import RemoteMavrosVehicle, Setpoint
        for scenario in ('arrives','missing','expired','hold','duplicate','overflow'):
            now=[1_000_000_000];events=[]
            v=object.__new__(RemoteMavrosVehicle)
            v.responses=queue.Queue();v.rx=queue.Queue();v.rx.put((now[0],b'wire'))
            v.pending_wire=[];v.remote_ready=False;v.latest_deadline=now[0]+100_000_000
            v.latest_sp=Setpoint(1.,0.,-2.,.3,False)
            v.motion_forwarded=v.motion_rejected=v.last_wire=v.first_wire=v.wire_count=0
            v.publications=WirePublications();v.publications.request(1,v.latest_deadline,now[0])
            msg=Mock(vx=1.,vy=0.,z=-2.,yaw_rate=.3,type_mask=1507,coordinate_frame=1,time_boot_ms=42)
            msg.get_type.return_value='SET_POSITION_TARGET_LOCAL_NED';msg.get_msgbuf.return_value=b'wire'
            v.decoder=Mock();v.decoder.parse_buffer.return_value=[msg,msg] if scenario=='duplicate' else [msg]
            if scenario=='overflow':v.decoder.parse_buffer.return_value=[msg]*20
            v._verify_simulator=Mock();v.record=lambda data,**kw:events.append(data);v.m=Mock()
            with patch('remote_mavros.MavlinkVehicle.poll'),patch('remote_mavros.time.monotonic_ns',side_effect=lambda:now[0]):
                v.poll();self.assertFalse(v.m.write.called);self.assertTrue(v.pending_wire)
                self.assertLessEqual(len(v.pending_wire),16)
                now[0]+=101_000_000 if scenario=='expired' else 2_000_000
                if scenario not in ('missing','overflow'):v.publications.published(dict(request_sequence=1,wire_stamp_ms=42,sp=vars(v.latest_sp)),now[0])
                if scenario=='hold':v.latest_sp=Setpoint(0.,0.,-2.,0.,True)
                v.poll()
                now[0]+=11_000_000;v.poll()
            self.assertEqual(v.m.write.call_count,1 if scenario in ('arrives','duplicate') else 0)
            self.assertFalse(v.pending_wire)

    def test_wire_expiry_cannot_inherit_new_lease(self):
        w=WirePublications();sp=self.packet()['sp']
        w.request(1,100,0)
        w.published(dict(request_sequence=1,wire_stamp_ms=42,sp=sp),1)
        w.request(2,200,101)
        self.assertFalse(w.consume(42,sp,102))
        w.published(dict(request_sequence=1,wire_stamp_ms=43,sp=sp),103)
        self.assertFalse(w.consume(43,sp,104))

    def test_wire_mismatched_values_rejected(self):
        w=WirePublications();sp=self.packet()['sp']
        w.request(1,100,0)
        w.published(dict(request_sequence=1,wire_stamp_ms=42,sp=sp),1)
        self.assertFalse(w.consume(42,dict(sp,vn=0.),2))

    def test_board_asset_cannot_escape_staging(self):
        from gazebo_vision import board_asset_path
        self.assertEqual(board_asset_path('/opt/garuda-sim/profile-fullview.json'),'/opt/garuda-sim/profile-fullview.json')
        for value in ('/opt/garuda-sim/../../bin/sh','/opt/garuda-sim/../x','/tmp/profile',
                      '/opt/garuda-sim/a;reboot','/opt/garuda-sim/a\nb'):
            with self.assertRaises(ValueError):board_asset_path(value)

    def test_wire_identity_change_revokes_old_publication(self):
        w=WirePublications();sp=self.packet()['sp']
        w.context(('source','stream',1,4));w.request(1,100,0)
        w.published(dict(request_sequence=1,wire_stamp_ms=42,sp=sp),1)
        w.context(('source','stream',2,5));w.request(2,100,2)
        self.assertFalse(w.consume(42,sp,3))
        w.published(dict(request_sequence=1,wire_stamp_ms=43,sp=sp),4)
        self.assertFalse(w.consume(43,sp,5))


if __name__=='__main__':unittest.main()
