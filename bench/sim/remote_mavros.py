"""Owned PX4 loopback <-> SSH TCP tunnel <-> actual MAVROS on Hailo-15L.

Nominal arm/mode/setpoints go through ROS/MAVROS. The inherited direct LAND is
reserved for teardown if the remote path has failed, and explicitly logged.
The PC relay rechecks freshness on arriving MAVLink packets, after ROS queues.
"""
import json
import math
import os
import queue
import socket
import subprocess
import threading
import time
import uuid

from sim_offboard_bridge import MavlinkVehicle, Setpoint
from mavros_contract import conservative_offset, WirePublications, motion_gate_reason
from link_log import LinkLog, px4_mode_name


class RemoteMavrosVehicle(MavlinkVehicle):
    def __init__(self, *, sim_pid, directory, axis_test=False, camera=False):
        super().__init__(sim_pid=sim_pid)
        self.session=uuid.uuid4().hex
        self.sequence=0
        self.axis_test=axis_test
        self.offset=None
        self.offset_at=0
        self.pings={}
        self.last_ping=0
        self.latest_sp=None
        self.latest_deadline=0
        self.publications=WirePublications()
        self.pending_wire=[]
        self.remote_ready=False
        self.remote_last=None
        self.native_last=None
        self.last_forwarded=None
        self.last_wire_event=None
        self.first_wire=self.last_wire=0
        self.wire_count=0
        self.motion_forwarded=self.motion_rejected=0
        self._link_log=LinkLog()   # console terminal: transitions only, served with status()
        self.stop=threading.Event()
        self.rx=queue.Queue(maxsize=128)
        self.tx=queue.Queue(maxsize=128)
        self.responses=queue.Queue(maxsize=256)
        self.log=open(directory/'mavros-events.jsonl','x')
        self.stderr=open(directory/'mavros-board.log','xb')
        self.listener=socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        self.listener.bind(('127.0.0.1',5761));self.listener.listen(1);self.listener.settimeout(.2)
        mode=' axis-test' if axis_test else ''
        if camera:
            import uuid as uuid_module
            boot=subprocess.check_output(['ssh','-oBatchMode=yes','-oConnectTimeout=5','root@10.0.0.1',
                'cat /proc/sys/kernel/random/boot_id'],text=True).strip()
            boot=str(uuid_module.UUID(boot))
            mode=' camera linux.monotonic:'+boot
        self.child=subprocess.Popen(['ssh','-T','-oBatchMode=yes','-oExitOnForwardFailure=yes',
            '-oServerAliveInterval=2','-oServerAliveCountMax=2','-R','127.0.0.1:5760:127.0.0.1:5761',
            'root@10.0.0.1','exec chroot /opt/garuda-ros-jazzy /usr/bin/env GARUDA_SIM=1 /bin/bash /opt/garuda/run_board.sh '+self.session+mode],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,bufsize=0)
        self.writer=queue.Queue(maxsize=8)
        for method in (self.tunnel,self.read_responses,self.write_requests):
            threading.Thread(target=method,daemon=True).start()
        self.decoder=self.mavutil.mavlink.MAVLink(None)
        self.decoder.robust_parsing=True

    @property
    def link_log(self):
        # Contract tests build this object without __init__; the log must exist regardless.
        log=self.__dict__.get('_link_log')
        if log is None:log=self.__dict__['_link_log']=LinkLog()
        return log

    def record(self,data,*,at_ns=None):
        self.log.write(json.dumps(dict(host_ns=time.monotonic_ns() if at_ns is None else at_ns,**data),allow_nan=False)+'\n');self.log.flush()

    def tunnel(self):
        client=None
        try:
            while not self.stop.is_set() and client is None:
                try: client,_=self.listener.accept()
                except socket.timeout: pass
            if client is None:return
            client.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            client.settimeout(.005)
            while not self.stop.is_set():
                chunks=[]
                try:
                    for _ in range(128):
                        stamp,data=self.tx.get_nowait()
                        if time.monotonic_ns()-stamp<500_000_000:chunks.append(data)
                except queue.Empty: pass
                if chunks:client.sendall(b''.join(chunks))
                try:
                    data=client.recv(65536)
                    if not data:break
                    self.rx.put_nowait((time.monotonic_ns(),data))
                except socket.timeout:pass
        except (OSError,queue.Full):pass
        finally:
            if client:client.close()

    def read_responses(self):
        try:
            while not self.stop.is_set():
                line=self.child.stdout.readline(512*1024+1)
                if not line:break
                if len(line)>512*1024:break
                try:
                    response=json.loads(line)
                    response['host_received_ns']=time.monotonic_ns()
                    self.responses.put_nowait(response)
                except ValueError:continue
                except queue.Full:break
        finally:self.remote_ready=False

    def write_requests(self):
        try:
            while not self.stop.is_set():
                try:data=self.writer.get(timeout=.1)
                except queue.Empty:continue
                self.child.stdin.write(data)
        except (BrokenPipeError,OSError):self.remote_ready=False

    def on_message(self,msg):
        # PX4 -> MAVROS direction: note what the autopilot says before relaying it.
        t=msg.get_type()
        try:
            if t=='STATUSTEXT':
                text=msg.text if isinstance(msg.text,str) else bytes(msg.text).split(b'\0',1)[0].decode(errors='replace')
                self.link_log.px4_text(text.rstrip('\0'),msg.severity)
            elif t=='COMMAND_ACK':
                enums=self.mavutil.mavlink.enums
                name=lambda table,value:enums[table][value].name if value in enums[table] else str(value)
                self.link_log.px4_ack(name('MAV_CMD',msg.command),name('MAV_RESULT',msg.result))
            elif t=='HEARTBEAT':
                self.link_log.px4_heartbeat(bool(msg.base_mode&self.mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),msg.custom_mode)
        except (AttributeError,KeyError,TypeError,ValueError):pass
        data=(time.monotonic_ns(),msg.get_msgbuf())
        try:self.tx.put_nowait(data)
        except queue.Full:
            try:self.tx.get_nowait()
            except queue.Empty:pass
            self.tx.put_nowait(data)

    def request(self,data):
        data=dict(data,session=self.session)
        try:self.writer.put_nowait(json.dumps(data,allow_nan=False).encode()+b'\n')
        except queue.Full:raise OSError('ROS request queue full')

    def poll(self,max_msgs=200):
        super().poll(max_msgs)
        now=time.monotonic_ns()
        while True:
            try:r=self.responses.get_nowait()
            except queue.Empty:break
            self.record(r)
            self.link_log.response(r)
            if r.get('kind')=='ready':self.remote_ready=True
            if r.get('kind')=='native_camera':self.native_last=r
            if r.get('kind')=='setpoint':
                self.remote_last=r
                self.publications.published(r,now)
            if r.get('kind')=='pong':
                t0=self.pings.pop(r['id'],None)
                if t0 is not None:
                    try:self.offset=conservative_offset(t0,r['remote_ns'],r['host_received_ns']);self.offset_at=r['host_received_ns']
                    except ValueError:pass
        if self.remote_ready and now-self.last_ping>1_000_000_000:
            self.last_ping=now;self.pings={str(now):now}
            self.request(dict(action='ping',id=str(now)))
        packets=self.pending_wire;self.pending_wire=[]
        while True:
            try:received,data=self.rx.get_nowait()
            except queue.Empty:break
            for msg in self.decoder.parse_buffer(data) or []:
                if msg.get_type()!='BAD_DATA':packets.append((received,msg))
        for received,msg in packets:
            now=time.monotonic_ns()
            allowed=True
            if msg.get_type()=='SET_POSITION_TARGET_LOCAL_NED':
                moving=any(abs(v)>1e-6 for v in (msg.vx,msg.vy,msg.yaw_rate))
                finite=all(math.isfinite(v) for v in (msg.vx,msg.vy,msg.z,msg.yaw_rate))
                allowed=finite and now-received<150_000_000 and msg.type_mask==1507 and msg.coordinate_frame==1 and abs(msg.z+2)<.01
                allowed=allowed and math.hypot(msg.vx,msg.vy)<=1.001 and abs(msg.yaw_rate)<=.801
                reason='forwarded' if allowed else 'invalid_or_stale_wire_envelope'
                if moving:
                    publication=self.publications.publications.get(msg.time_boot_ms)
                    # The publication record and MAVLink packet use separate
                    # SSH channels. Await missing metadata for at most 10ms;
                    # never forward unbound, extend a lease or wait through HOLD.
                    if (allowed and publication is None and now-received<10_000_000
                        and self.latest_sp is not None and not self.latest_sp.hover
                        and now<self.latest_deadline and len(self.pending_wire)<16):
                        self.pending_wire.append((received,msg));continue
                    bound=self.publications.consume(msg.time_boot_ms,
                        dict(vn=msg.vx,ve=msg.vy,z_ned=msg.z,yaw_rate=msg.yaw_rate),now)
                    sp=self.latest_sp
                    if allowed:
                        reason=motion_gate_reason(publication,bound,vars(sp) if sp else None,self.latest_deadline,
                            dict(vn=msg.vx,ve=msg.vy,yaw_rate=msg.yaw_rate),now)
                        allowed=reason=='forwarded'
                if allowed:
                    self._verify_simulator()
                    packet=msg.get_msgbuf()
                    # Logging and process-ownership checks may block. Charge
                    # that time BEFORE the final write, never after a permit.
                    now=time.monotonic_ns()
                    if now-received>=150_000_000:
                        allowed=False;reason='wire_expired_before_dispatch'
                    elif moving and (now>=self.latest_deadline or now>=publication[0]):
                        allowed=False;reason='lease_expired_before_dispatch'
                    if allowed:self.m.write(packet)
                self.record(dict(kind='wire',allowed=allowed,moving=moving,vn=msg.vx,ve=msg.vy,yaw_rate=msg.yaw_rate,
                                 reason=reason,received_ns=received,relay_queue_ms=(now-received)/1e6,
                                 deadline_ns=self.latest_deadline,wire_stamp_ms=msg.time_boot_ms,
                                 origin_deadline_ns=publication[0] if moving and publication else None),at_ns=now)
                self.last_wire_event=dict(host_ns=now,allowed=allowed,moving=moving,
                    reason=reason,relay_queue_ms=(now-received)/1e6,
                    vn=msg.vx,ve=msg.vy,z_ned=msg.z,yaw_rate=msg.yaw_rate,wire_stamp_ms=msg.time_boot_ms)
                self.link_log.wire(allowed,moving,reason,msg.vx,msg.vy,msg.yaw_rate,(now-received)/1e6)
                if moving:
                    if allowed:self.motion_forwarded+=1
                    else:self.motion_rejected+=1
                if allowed:
                    self.last_forwarded=self.last_wire_event
                    if now-self.last_wire>200_000_000:self.first_wire=now;self.wire_count=0
                    self.last_wire=now;self.wire_count+=1
            if allowed and msg.get_type()!='SET_POSITION_TARGET_LOCAL_NED':
                self._verify_simulator()
                self.m.write(msg.get_msgbuf())
                t=msg.get_type()
                if t=='COMMAND_LONG':
                    enums=self.mavutil.mavlink.enums['MAV_CMD']
                    self.link_log.mavlink_out(t,f"{enums[msg.command].name if msg.command in enums else msg.command} "
                                                f"p1 {msg.param1:g} p2 {msg.param2:g}")
                elif t=='SET_MODE':
                    self.link_log.mavlink_out(t,f"custom_mode {px4_mode_name(msg.custom_mode)}")

    def send_setpoint(self,sp,boot_ms,*,expires_ns=None,source=None,**_):
        self._verify_simulator()
        now=time.monotonic_ns()
        if self.offset is None or now-self.offset_at>3_000_000_000:
            raise OSError('no fresh bounded ROS clock handshake')
        if now-int(min(self.last_position,self.last_attitude)*1e9)>500_000_000:
            raise OSError('PX4 telemetry stale')
        end=min(expires_ns or now+100_000_000,now+100_000_000)
        self.latest_sp,self.latest_deadline=sp,end
        out=(source or {}).get('output') or {}
        lock=out.get('lock') or {}
        identity=(out.get('source_id'),out.get('stream_id'),lock.get('epoch'),lock.get('id'))
        if sp.hover or identity!=self.publications.identity:
            if self.pending_wire:self.record(dict(kind='pending_wire_revoked',count=len(self.pending_wire),reason='hold_or_identity_change'))
            self.pending_wire.clear()
        self.publications.context(identity)
        self.sequence+=1
        self.publications.request(self.sequence,end,now)
        self.record(dict(kind='request',sequence=self.sequence,deadline_ns=end,identity=identity,sp=vars(sp),
                         offset_ns=self.offset,source_sequence=out.get('sequence')))
        self.link_log.request('setpoint',self.sequence,sp)
        self.request(dict(action='setpoint',sequence=self.sequence,expires_ns=end+self.offset,offset_ns=self.offset,
                          enabled=True,sp=vars(sp),source=source,axis_test=self.axis_test))

    def command(self,action):
        self._verify_simulator()
        now=time.monotonic_ns()
        if self.offset is None or now-self.offset_at>3_000_000_000:raise OSError('ROS clock unavailable')
        self.sequence+=1
        self.link_log.request(action,self.sequence)
        self.request(dict(action=action,sequence=self.sequence,expires_ns=now+100_000_000+self.offset,
                          enabled=True,sp=vars(Setpoint(0.,0.,-2.,0.,True))))

    def arm(self):self.command('arm')
    def set_offboard(self):self.command('offboard')
    def land(self):self.command('land')

    @property
    def ready_to_arm(self):
        now=time.monotonic_ns()
        return self.wire_count>=35 and now-self.first_wire>=2_000_000_000 and now-self.last_wire<200_000_000

    def status(self):
        return dict(motion_forwarded=self.motion_forwarded,motion_rejected=self.motion_rejected,
                    board_publication=self.remote_last,native_camera=self.native_last,
                    native_report_age_ms=(time.monotonic_ns()-self.native_last['host_received_ns'])/1e6 if self.native_last else None,
                    publication_report_age_ms=(time.monotonic_ns()-self.remote_last['host_received_ns'])/1e6 if self.remote_last else None,
                    forwarded=self.last_forwarded,last_wire=self.last_wire_event,
                    forwarded_age_ms=(time.monotonic_ns()-self.last_forwarded['host_ns'])/1e6 if self.last_forwarded else None,
                    wire_age_ms=(time.monotonic_ns()-self.last_wire)/1e6 if self.last_wire else None,
                    reason=self.remote_last.get('reason') if self.remote_last else 'Waiting for board ROS',
                    link_log=self.link_log.tail(80))

    def emergency_land(self):
        self.record(dict(kind='emergency_direct_land',reason='remote cleanup failure'))
        super().land()

    def close(self):
        self.stop.set();self.child.terminate()
        try:self.child.wait(timeout=5)
        except subprocess.TimeoutExpired:self.child.kill();self.child.wait()
        self.listener.close();self.stderr.close();self.log.close()
