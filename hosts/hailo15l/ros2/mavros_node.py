"""On-board ROS 2 bench authority -> MAVROS. Fixed local simulator tunnel only.

Native inference is outside this userspace. Perception envelopes arrive over
the owned PC runner, traverse an actual ROS topic, and are revalidated here.
No serial-device or arbitrary FC URL option exists.
"""
import json
import math
import os
import sys
import threading
import time
import socket
from dataclasses import replace

from mavros_contract import Lease, enu_setpoint
from perception_authority import PerceptionAuthority
from follow_controller import FollowConfig
from sim_offboard_bridge import setpoint_from_intent


def main():
    if os.environ.get('GARUDA_SIM')!='1' or len(sys.argv) not in (2,3,4):
        raise PermissionError('owned simulation session required')
    axis_test=len(sys.argv)==3 and sys.argv[2]=='axis-test'
    camera=len(sys.argv)==4 and sys.argv[2]=='camera'
    if len(sys.argv)>2 and not (axis_test or camera):raise ValueError('unknown bench mode')
    if camera:
        from native_camera import LocalCameraGate, read_packet, camera_request_bound, camera_response_heading
        camera_gate=LocalCameraGate(sys.argv[3])
    session=sys.argv[1]
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import qos_profile_sensor_data
    from std_msgs.msg import String
    from geometry_msgs.msg import PoseStamped
    from mavros_msgs.msg import PositionTarget, State
    from mavros_msgs.srv import CommandBool, SetMode
    rclpy.init(args=[])
    output_lock=threading.Lock()

    def emit(data):
        with output_lock:
            print(json.dumps(data,allow_nan=False),flush=True)

    class Authority(Node):
        def __init__(self):
            super().__init__('garuda_mavros_authority')
            self.lease=Lease(session)
            self.pipeline=None
            self.last_source=None
            self.pose_at=self.state_at=self.last_request=0
            self.yaw=0.
            self.active=False
            self.state=None
            self.camera_row=None
            self.camera_count=0
            self.camera_report_at=0
            self.publish=self.create_publisher(PositionTarget,'/mavros/setpoint_raw/local',1)
            self.create_subscription(String,'/garuda/bench_request',self.request,8)
            if camera:self.create_subscription(String,'/garuda/camera/native_snapshot',self.native,1)
            self.create_subscription(PoseStamped,'/mavros/local_position/pose',self.pose,qos_profile_sensor_data)
            self.create_subscription(State,'/mavros/state',self.status,qos_profile_sensor_data)
            self.arm_client=self.create_client(CommandBool,'/mavros/cmd/arming')
            self.mode_client=self.create_client(SetMode,'/mavros/set_mode')
            self.timer=self.create_timer(.05,self.tick)

        def native(self,msg):
            now=time.monotonic_ns()
            try:
                row=json.loads(msg.data)
                camera_gate.ingest(row,now)
                if camera_gate.reason.startswith('invalid_native_envelope'):
                    raise ValueError(camera_gate.reason)
                self.camera_row=row;self.camera_count+=1
                key=(row['source_id'],row['stream_id'],row['lock']['epoch'])
                if row['lock']['id'] is None:
                    self.pipeline=None
                else:
                    if self.pipeline is None or self.pipeline.follow.identity!=key:
                        self.pipeline=PerceptionAuthority(*key,execution='live',config=FollowConfig(min_height_frac=.02))
                    self.pipeline.ingest(row,round(row['sample_monotonic_ms']*1e6),now)
            except (ValueError,TypeError,KeyError) as error:
                self.camera_row=None
                if self.pipeline:self.pipeline.reject('native_camera_invalid')
                camera_gate.reject(str(error))

        def pose(self,msg):
            q=msg.pose.orientation
            if not all(math.isfinite(v) for v in (q.x,q.y,q.z,q.w)):
                self.pose_at=0;return
            enu=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
            self.yaw=math.pi/2-enu
            self.pose_at=time.monotonic_ns()

        def status(self,msg):
            self.state=msg;self.state_at=time.monotonic_ns()

        def request(self,msg):
            now=time.monotonic_ns()
            try:
                p=json.loads(msg.data)
                if p.get('session')!=session: return
                if p.get('action')=='ping':
                    emit(dict(kind='pong',id=p['id'],remote_ns=now));return
                if not self.lease.accept(p,now):
                    emit(dict(kind='rejected',reason='invalid lease',remote_ns=now));return
                self.last_request=now
                action=p.get('action')
                if action in ('arm','offboard','land'):
                    self.active=action!='land'
                    if action=='arm':
                        request=CommandBool.Request();request.value=True;client=self.arm_client
                    else:
                        request=SetMode.Request();request.custom_mode='OFFBOARD' if action=='offboard' else 'AUTO.LAND';client=self.mode_client
                    if not client.service_is_ready(): raise ValueError('MAVROS service unavailable')
                    future=client.call_async(request)
                    future.add_done_callback(lambda f:emit(dict(kind='service',action=action,result=str(f.result()),remote_ns=time.monotonic_ns())))
                elif action=='setpoint':
                    self.active=p['enabled']
                    source=p.get('source')
                    if source and not camera:
                        out=json.loads(json.dumps(source['output']))
                        key=(out['source_id'],out['stream_id'],out['lock']['epoch'])
                        if out['lock']['id'] is not None and (self.pipeline is None or self.pipeline.follow.identity!=key):
                            self.pipeline=PerceptionAuthority(*key,execution='live',config=FollowConfig(min_height_frac=.02))
                            self.last_source=None
                        unique=(*key,out['sequence'])
                        if self.pipeline and unique!=self.last_source:
                            self.last_source=unique
                            offset=p['offset_ns']/1e6
                            for field in ('capture_monotonic_ms','publish_monotonic_ms','sample_monotonic_ms'):
                                out[field]+=offset
                            out['clock_domain']='board.ros_monotonic_conservative'
                            # Charge ROS/SSH delay rather than renewing stale evidence.
                            self.pipeline.ingest(out,int(out['publish_monotonic_ms']*1e6),now)
                    # Publish the accepted request without waiting for an unrelated
                    # timer phase. Reset the watchdog cadence, not the original
                    # lease: silence/expiry still produces HOLD or PX4 failsafe.
                    self.tick()
                    self.timer.reset()
                else: raise ValueError('unknown action')
            except Exception as error:
                self.lease.packet=None
                emit(dict(kind='rejected',reason=str(error),remote_ns=now))

        def tick(self):
            now=time.monotonic_ns()
            p=self.lease.current(now)
            if camera and now-self.camera_report_at>200_000_000:
                self.camera_report_at=now
                emit(dict(camera_gate.status(now),kind='native_camera',ros_received=self.camera_count,
                    topic='/garuda/camera/native_snapshot',role='on-board authority input',
                    # The imported gate is itself read-only; this node can publish
                    # simulator commands only through the independent request lease.
                    authority_vehicle_io='simulator-only via MAVROS',
                    lock_id=self.camera_row['lock']['id'] if self.camera_row else None))
            # Expired source: zero motion. Total runner loss: stop setpoints after
            # 500ms so PX4's own offboard-loss failsafe remains independently tested.
            if not self.active or now-self.last_request>500_000_000: return
            sp=dict(vn=0.,ve=0.,z_ned=-2.,yaw_rate=0.,hover=True)
            reason='lease expired / hold'
            fresh_telemetry=self.state and self.state.connected and now-self.pose_at<500_000_000 and now-self.state_at<1_500_000_000
            camera_bound=True
            if camera:
                requested=((p or {}).get('source') or {}).get('output') or {}
                local=self.camera_row or {}
                camera_bound=camera_request_bound(local,requested)
            if p and fresh_telemetry and self.pipeline and not p['sp']['hover'] and camera_bound:
                intent=self.pipeline.tick(now)
                source=p.get('source') or {}
                if not camera and source.get('depth_paired') and isinstance(source.get('range_m'),(int,float)):
                    distance=source['range_m']
                    speed=max(-.5,min(1.,(distance-6.)*.5)) if math.isfinite(distance) and .3<distance<30 else 0.
                    if abs(intent.yaw_rate)>.2 or abs(distance-6.)<.3: speed=0.
                    intent=replace(intent,forward_vel=speed)
                heading=source.get('heading_response_ned')
                if camera:
                    heading=camera_response_heading(self.camera_row,source)
                    if heading is None:
                        intent=replace(intent,command_eligible=False,forward_vel=0.,yaw_rate=0.)
                if heading is not None and math.isfinite(heading):
                    error=math.atan2(math.sin(heading-self.yaw),math.cos(heading-self.yaw))
                    intent=replace(intent,forward_vel=0.,yaw_rate=max(-.8,min(.8,2*error)))
                sp=vars(setpoint_from_intent(intent,self.yaw,-2.,now))
                reason=intent.reason
            if p and fresh_telemetry and axis_test and p.get('axis_test') is True:
                sp=p['sp'];reason='EXPLICIT SIMULATOR AXIS TEST; no detector claim'
            if not fresh_telemetry:
                # No stale telemetry-driven setpoints; allow PX4 local failsafe.
                emit(dict(kind='hold',reason='MAVROS telemetry stale',remote_ns=now,
                          pose_age_ms=(now-self.pose_at)/1e6,state_age_ms=(now-self.state_at)/1e6,
                          connected=bool(self.state and self.state.connected)));return
            values=enu_setpoint(sp)
            msg=PositionTarget()
            msg.header.stamp=self.get_clock().now().to_msg()
            msg.coordinate_frame=PositionTarget.FRAME_LOCAL_NED
            msg.type_mask=values['type_mask']
            msg.position.z=values['z'];msg.velocity.x=values['x'];msg.velocity.y=values['y'];msg.yaw_rate=values['yaw_rate']
            emit(dict(kind='setpoint',remote_ns=now,sp=sp,reason=reason,request_sequence=p['sequence'] if p else None,
                      request_to_publish_ms=(now-self.last_request)/1e6,
                      source_sequence=self.camera_row['sequence'] if camera and self.camera_row else None,
                      source_capture_age_ms=(now/1e6-self.camera_row['capture_monotonic_ms']) if camera and self.camera_row else None,
                      ros_topic='/mavros/setpoint_raw/local',ros_enu=values,
                      expires_ns=p['expires_ns'] if p else None,connected=bool(self.state and self.state.connected),
                      wire_stamp_ms=((msg.header.stamp.sec*1_000_000_000+msg.header.stamp.nanosec)//1_000_000)&0xffffffff))
            self.publish.publish(msg)

    ingress=Node('garuda_bench_ingress')
    pub=ingress.create_publisher(String,'/garuda/bench_request',8)
    authority=Authority()
    executor=SingleThreadedExecutor()
    executor.add_node(ingress);executor.add_node(authority)
    done=threading.Event()
    def reader():
        try:
            while not done.is_set():
                line=sys.stdin.buffer.readline(512*1024+1)
                if not line: break
                if len(line)>512*1024 or not line.endswith(b'\n'): raise ValueError('oversize request')
                msg=String();msg.data=line.decode();pub.publish(msg)
        finally: done.set()
    threading.Thread(target=reader,daemon=True).start()
    if camera:
        camera_pub=ingress.create_publisher(String,'/garuda/camera/native_snapshot',1)
        def camera_reader():
            while not done.is_set():
                try:
                    with socket.create_connection(('127.0.0.1',8981),timeout=.5) as stream:
                        while not done.is_set():
                            row=read_packet(stream)
                            if row is not None:
                                msg=String();msg.data=json.dumps(row,allow_nan=False);camera_pub.publish(msg)
                except (OSError,ValueError,EOFError):done.wait(.1)
        threading.Thread(target=camera_reader,daemon=True).start()
    emit(dict(kind='ready',remote_ns=time.monotonic_ns(),architecture=os.uname().machine))
    try:
        while not done.is_set(): executor.spin_once(timeout_sec=.05)
    finally:
        executor.shutdown();authority.destroy_node();ingress.destroy_node();rclpy.shutdown()


if __name__=='__main__': main()
