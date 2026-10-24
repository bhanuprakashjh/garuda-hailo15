#!/usr/bin/env python3
"""Local rendered-camera/Hailo/PX4 bench. Never connects to a physical FC.

Run with GARUDA_SIM=1. Default: disarmed, no automatic follow. --auto-demo is
explicit simulator takeoff, sole detected person selection, follow, stall, land.
"""
import argparse
from collections import OrderedDict, deque
from dataclasses import replace
import json
import hashlib
import math
import os
import pathlib
import queue
import signal
import shlex
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
for path in ('services/garuda-follow', 'services/garuda-bridge', 'interfaces'):
    sys.path.insert(0, str(ROOT/path))
from perception_authority import PerceptionAuthority
from follow_controller import FollowConfig
import sim_offboard_bridge as bridge
from gazebo_vision import GazeboPixels, BoardVision, jpeg
from gazebo_console import serve


def guarded_intent(intent, result, clock, now_ns, follow):
    """The final sim-only gate also checks progress of the rendering clock.

    This is PC-ingress freshness, not a proof of exposure-to-command latency.
    Depth from the same RGBD sensor and exact sim stamp is required to translate.
    """
    if not follow or intent is None or not result or not clock:
        return None
    if result.get('live_camera'):
        age=result['age_ms']+(now_ns-result['received_ns'])/1e6
        if not math.isfinite(age) or not 0 <= age < 200:return None
    if (not 0 <= now_ns-result['ingress_ns'] < 200_000_000 or
            not 0 <= now_ns-clock[1] < 200_000_000 or
            (not result.get('live_camera') and not -50_000_000 <= clock[0]-result['sim_ns'] < 200_000_000)):
        return None
    if not intent.command_eligible or intent.expired(now_ns):
        return None
    distance = result.get('range_m')
    speed = 0.
    if not result.get('live_camera') and result.get('depth_paired') and isinstance(distance, (int, float)) and math.isfinite(distance) and .3 < distance < 30:
        speed = max(-.5, min(1., (distance-6.)*.5))
        if abs(intent.yaw_rate) > .2 or abs(distance-6.) < .3:
            speed = 0.
    return replace(intent, forward_vel=speed)


class Runtime:
    def __init__(self, pixels, event_log=None):
        self.pixels, self.vision = pixels, None
        self.lock = threading.Lock()
        self.events = deque(maxlen=100)
        self.event_log = event_log
        self.frames = OrderedDict()
        self.requests = queue.Queue(maxsize=8)
        self.result = None
        self.flight, self.reason, self.command = 'Starting', 'Waiting for simulator', 'HOLD'
        self.altitude = None
        self.transport='mavlink'
        self.pixel_source='Gazebo RGBD'
        self.heading=self.requested_heading=None
        self.mavros_status=None
        self.requested_setpoint=None
        self.relative_framing=None
        self.gui_running=False
        self.board_profile=None
        self.follow_enabled=False
        self.control_deadline_ns=0

    def event(self, kind, detail):
        with self.lock:
            event = dict(time=time.strftime('%H:%M:%S'), monotonic_ns=time.monotonic_ns(), kind=kind, detail=detail)
            self.events.append(event)
            if self.event_log:
                self.event_log.write(json.dumps(event)+'\n')
                self.event_log.flush()

    def accept(self, result):
        with self.lock:
            if self.result and self.result['output']['stream_id'] != result['output']['stream_id']:
                self.frames.clear()
            self.result = result
            self.frames[result['sequence']] = result['jpeg']
            while len(self.frames) > 6:
                self.frames.popitem(last=False)

    def state(self):
        frame, _, clock, rtf = self.pixels.snapshot()
        with self.lock:
            r = self.result
            fresh_request=self.command=='FOLLOW' and time.monotonic_ns()<self.control_deadline_ns
            out = dict(flight=self.flight, reason=self.reason, command='FOLLOW' if fresh_request else 'HOLD',
                follow_enabled=self.follow_enabled,control_request_fresh=fresh_request,
                control_request_remaining_ms=max(0.,(self.control_deadline_ns-time.monotonic_ns())/1e6) if fresh_request else 0.,
                identity_retained=bool(r and r['output']['lock'].get('identity_retained')),
                altitude_m=self.altitude, output=r['output'] if r else None,
                receiver_age_ms=(r['age_ms']+(time.monotonic_ns()-r['received_ns'])/1e6
                    if r.get('live_camera') else (time.monotonic_ns()-r['ingress_ns'])/1e6) if r else None,
                inference_ms=r['age_ms'] if r and not r.get('live_camera') else None, range_m=r['range_m'] if r else None,
                depth_paired=r['depth_paired'] if r else False,
                vision=self.vision is not None and not self.vision.stop.is_set(), rtf=rtf,
                events=list(self.events), preview_sequence=frame[0] if frame else None,
                frame_url=f"/frame.jpg?sequence={r['sequence']}" if r else '/frame.jpg' if frame else None,
                overview_ns=self.pixels.overview[0] if self.pixels.overview else None,
                timing_scope='Original board capture age + transport bound' if r and r.get('live_camera') else 'PC ingress bounded; simulation exposure age not certified',
                real_hardware_commands=False)
            out.update(transport=self.transport,pixel_source=self.pixel_source,heading_deg=self.heading,
                       requested_heading_deg=self.requested_heading,raw_detections=r.get('raw_detections',[]) if r else [],
                       detector_passes=r.get('detector_passes') if r else None,
                       board_profile=self.board_profile,replay_loops=getattr(self.pixels,'loops',None),
                       replay_paused=getattr(self.pixels,'paused',None),
                       board_schedule=dict(mode=r.get('schedule'),global_pass=r.get('global'),roi=r.get('roi') is not None,
                                           roi_reason=r.get('roi_reason'),verified_local=r.get('verified_local')) if r and r.get('schedule') else None,
                       compute_stage_ms=r.get('stage_ms') if r else None,mavros=self.mavros_status,
                       overlay_matched=r.get('overlay_matched',True) if r else False,
                       preview_age_ms=(time.monotonic_ns()-r['preview_received_ns'])/1e6 if r and r.get('preview_received_ns') else None,
                       requested_setpoint=self.requested_setpoint,relative_framing=self.relative_framing,
                       gazebo_gui_running=self.gui_running)
            return out

    def image(self, path, sequence):
        if path == '/overview.jpg':
            with self.pixels.lock:
                return self.pixels.overview[1] if self.pixels.overview else None
        if sequence >= 0:
            with self.lock:
                return self.frames.get(sequence)
        if self.pixel_source.startswith('Physical'):
            with self.lock:
                return self.result['jpeg'] if self.result else None
        frame, _, _, _ = self.pixels.snapshot()
        return jpeg(frame[3]) if frame else None

    def action(self, body):
        action = body['action']
        if action not in ('takeoff', 'follow', 'hold', 'land', 'release', 'select', 'select_id', 'video_stall', 'stop', 'framing_reference',
                          'pause', 'resume'):
            raise ValueError('unknown action')
        if action in ('pause', 'resume') and not hasattr(self.pixels, 'pause'):
            raise ValueError('only a recorded clip can be paused')
        if action in ('select', 'select_id', 'release', 'follow', 'video_stall') and (not self.vision or self.vision.stop.is_set()):
            raise ValueError('live Hailo stream is not connected')
        if action in ('select', 'select_id'):
            if type(body['sequence']) is not int or body['sequence'] < 1:
                raise ValueError('displayed frame sequence required')
            if action == 'select':
                if any(type(body[k]) not in (int, float) or not math.isfinite(body[k]) or not 0 <= body[k] <= limit
                       for k, limit in (('x', 1280), ('y', 720))):
                    raise ValueError('invalid image point')
            elif type(body['id']) is not int or body['id'] < 1:
                raise ValueError('invalid track ID')
        if action in ('hold', 'land', 'stop'):
            # Urgent operator requests supersede queued selections/follow requests.
            while True:
                try:
                    self.requests.get_nowait()
                except queue.Empty:
                    break
        self.requests.put_nowait(body)
        return 'Simulator request queued: '+action


def launch(args, env, directory):
    if subprocess.run(['pgrep', '-x', 'px4'], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('another PX4 instance is running; do not share its MAVLink ports')
    px4 = pathlib.Path(args.px4).resolve()
    build = px4/'build/px4_sitl_default'
    # A separate rootfs avoids modifying the user's previous SIH parameters/logs.
    rootfs = directory/'rootfs'
    rootfs.mkdir()
    (rootfs/'etc').symlink_to(build/'etc', target_is_directory=True)
    models = px4/'Tools/simulation/gz/models'
    env.update(GZ_SIM_RESOURCE_PATH=str(models),
        GZ_SIM_SYSTEM_PLUGIN_PATH=str(build/'src/modules/simulation/gz_plugins'),
        GZ_SIM_SERVER_CONFIG_PATH=str(px4/'src/modules/simulation/gz_bridge/server.config'),
        PX4_GZ_STANDALONE='1', PX4_GZ_WORLD='garuda_follow',
        PX4_GZ_MODEL_NAME='garuda_x500', PX4_SIM_MODEL='gz_x500',
        PX4_GZ_NO_FOLLOW='1', HEADLESS='1')
    logs = [open(directory/name, 'xb') for name in ('gazebo.log', 'px4.log')]
    gz = subprocess.Popen(['gz', 'sim', '-r', '-s', str(pathlib.Path(__file__).with_name('gazebo_follow.sdf'))],
        env=env, stdout=logs[0], stderr=subprocess.STDOUT, start_new_session=True)
    try:
        proc = subprocess.Popen([str(build/'bin/px4'), '-d', '-s', 'etc/init.d-posix/rcS'],
            cwd=rootfs, env=env, stdout=logs[1], stderr=subprocess.STDOUT, start_new_session=True)
    except Exception:
        os.killpg(gz.pid, signal.SIGTERM)
        raise
    return proc, gz, logs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--px4', default='/media/bhanu1234/Development/PX4-Autopilot')
    parser.add_argument('--out', type=pathlib.Path, required=True)
    parser.add_argument('--port', type=int, default=8100)
    parser.add_argument('--board-binary', help='staged /opt/garuda-sim executable; omit for render-only preview')
    parser.add_argument('--board-profile',default='/opt/garuda-sim/profile.json',help='explicit staged bench profile; desk config remains unchanged')
    parser.add_argument('--auto-demo', action='store_true')
    parser.add_argument('--duration', type=float, default=60, help='auto-demo follow duration, seconds')
    parser.add_argument('--transport', choices=('mavlink','mavros-15l'), default='mavlink')
    parser.add_argument('--live-camera', action='store_true', help='keep desk camera running; fixed-camera heading response')
    parser.add_argument('--gui', action='store_true', help='open actual Gazebo desktop client in the owned partition')
    parser.add_argument('--replay',type=pathlib.Path,help='verified prepared NV12 sequence; response demo, not closed-loop')
    parser.add_argument('--replay-fps',type=float,default=20,help='declared playback assumption, not measured source FPS')
    parser.add_argument('--replay-hfov',type=float,default=1.2,help='assumed horizontal FOV in radians')
    parser.add_argument('--replay-loop',action='store_true',help='restart the clip when it ends (loop count shown); '
                        'default plays once and lets vision expire at EOF')
    parser.add_argument('--initial-point',type=float,nargs=2,help='one fixed initial selection point in 1280x720 pixels')
    parser.add_argument('--select-retry-s',type=float,default=0.,help='auto-demo: repeat the initial click on later frames for this long '
                        'until a lock exists (0 = the frozen one-click protocol); mirrors the campaigns\' labelled retry variant')
    args = parser.parse_args()
    if os.environ.get('GARUDA_SIM') != '1':
        raise PermissionError('GARUDA_SIM=1 required; simulation only')
    if not 10 <= args.duration <= 600 or not 1024 <= args.port <= 65535:
        raise ValueError('invalid bounded duration or port')
    if args.live_camera and (args.replay or args.board_binary or args.transport!='mavros-15l'):
        raise ValueError('live camera requires MAVROS-15L and cannot share a replay/board stream')
    if args.auto_demo and not (args.board_binary or args.live_camera):
        raise ValueError('auto-demo requires actual board inference')
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    adapter_source = pathlib.Path(__file__).with_name('rgb_nv12.cpp')
    if 'GARUDA_RGB_NV12_LIB' not in os.environ:
        adapter = args.out/'librgb_nv12.so'
        subprocess.run(['c++', '-O3', '-shared', '-fPIC', '-std=c++17', str(adapter_source), '-o', str(adapter)],
                       check=True, timeout=30)
        os.environ['GARUDA_RGB_NV12_LIB'] = str(adapter)
    tracked = [pathlib.Path(__file__), adapter_source,
               pathlib.Path(__file__).with_name('gazebo_vision.py'),
               pathlib.Path(__file__).with_name('gazebo_console.py'),
               pathlib.Path(__file__).with_name('follow_console.js'),
               pathlib.Path(__file__).with_name('gazebo_follow.sdf'),
               pathlib.Path(__file__).with_name('follow_console.html'), ROOT/'hosts/hailo15l/causal_replay.cpp']
    versions = dict(git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked},
        native_pixels_sha256=hashlib.sha256(pathlib.Path(os.environ['GARUDA_RGB_NV12_LIB']).read_bytes()).hexdigest(),
        px4_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.px4, text=True).strip(),
        gazebo=subprocess.check_output(['gz', 'sim', '--versions'], text=True).strip(),
        command=sys.argv,pixel_conversion=os.environ.get('GARUDA_PIXEL_CONVERSION','sdk_full'),
        timing_scope='PC ingress; ROS command deadlines use conservative bounded handshake when enabled')
    board_profile=None
    if args.board_binary:
        versions['board_hashes'] = subprocess.check_output(['ssh', '-oBatchMode=yes', '-oConnectTimeout=5',
            'root@10.0.0.1', 'sha256sum '+shlex.quote(args.board_binary)+' '+shlex.quote(args.board_profile)+' '
            '/opt/garuda-fresh/models/yolov11s_hailo15l_v5.3.0.hef /opt/garuda-fresh/models/osnet_x1_0_hailo15l_v5.3.0.hef'], text=True)
        # What the board will actually run, read from the staged profile and hashed there: the
        # console shows it, and versions.json keeps it, so a recorded-footage demo names its model.
        staged = json.loads(subprocess.check_output(['ssh', '-oBatchMode=yes', '-oConnectTimeout=5', 'root@10.0.0.1',
            'cat '+shlex.quote(args.board_profile)], text=True))
        hef_sha = subprocess.check_output(['ssh', '-oBatchMode=yes', '-oConnectTimeout=5', 'root@10.0.0.1',
            'sha256sum '+shlex.quote(staged['hef'])], text=True).split()[0]
        board_profile = dict(path=args.board_profile, hef=staged['hef'], hef_sha256=hef_sha,
                             schedule=staged.get('bench_schedule', 'adaptive'),
                             follow_local_gap_ms=staged.get('follow_local_gap_ms', 500),
                             follow_global_period_ms=staged.get('follow_global_period_ms', 800),
                             max_detections=staged.get('tracking', {}).get('max_detections'),
                             low_confidence=staged.get('tracking', {}).get('low_confidence'))
        versions['board_profile'] = board_profile
    (args.out/'versions.json').write_text(json.dumps(versions, indent=2)+'\n')
    if args.replay:
        manifest=json.loads((args.replay/'manifest.json').read_text())
        (args.out/'replay-source.json').write_text(json.dumps(dict(
            source_sha256=manifest['source_sha256'],frames=manifest['frames'],canvas=manifest['canvas'],
            fps_assumption=args.replay_fps,hfov_assumption_radians=args.replay_hfov,
            initial_point=args.initial_point,mode='bounded heading response, NOT closed loop'),indent=2)+'\n')
    if args.transport=='mavros-15l':
        from mavros_evidence import snapshot
        (args.out/'ros-versions.json').write_text(json.dumps(snapshot(ROOT),indent=2)+'\n')
    os.environ['GARUDA_PX4_BUILD'] = str(pathlib.Path(args.px4).resolve()/'build/px4_sitl_default')
    os.environ['GZ_PARTITION'] = f'garuda-follow-{os.getpid()}'
    pixels = GazeboPixels()
    heading_response=None
    if args.live_camera:
        from recorded_pixels import HeadingResponse
        heading_response=HeadingResponse(args.replay_hfov)
    if args.replay:
        from recorded_pixels import ReplayPixels,HeadingResponse
        pixels=ReplayPixels(args.replay,pixels,args.replay_fps,loop=args.replay_loop)
        heading_response=HeadingResponse(args.replay_hfov)
    event_log = open(args.out/'events.jsonl', 'x')
    rt = Runtime(pixels, event_log)
    if args.replay:rt.pixel_source='Recorded aerial video · heading response · assumed FOV'
    if args.live_camera:rt.pixel_source='Physical IMX678 · heading response · assumed FOV'
    rt.board_profile=board_profile
    from relative_framing import RelativeFraming
    framing=RelativeFraming()
    server = serve(rt, args.port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Follow Console: http://127.0.0.1:{args.port}/', flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    proc = gz = vehicle = gui = None
    logs = []
    board_log = open(args.out/'board.log', 'xb')
    evidence = open(args.out/'ticks.jsonl', 'x')
    pipeline = None
    takeoff = following = landing = selected_once = stalled = False
    prime = ready_at = land_at = takeoff_at = None
    heartbeat_at = 0.
    started = time.monotonic()
    previous_command = None
    finish_after_tick = False
    auto_follow_started = False
    try:
        proc, gz, logs = launch(args, dict(os.environ), args.out)
        if args.gui:
            gui_log=open(args.out/'gazebo-gui.log','xb');logs.append(gui_log)
            gui_env=dict(os.environ,GZ_SIM_RESOURCE_PATH=str(pathlib.Path(args.px4)/'Tools/simulation/gz/models'))
            gui=subprocess.Popen(['gz','sim','-g'],env=gui_env,stdout=gui_log,
                stderr=subprocess.STDOUT,start_new_session=True)
            rt.gui_running=True
        if args.transport=='mavros-15l':
            from remote_mavros import RemoteMavrosVehicle
            vehicle=RemoteMavrosVehicle(sim_pid=proc.pid,directory=args.out,camera=args.live_camera)
        else:
            vehicle = bridge.MavlinkVehicle(sim_pid=proc.pid)
        rt.transport=args.transport
        rt.flight = 'Disarmed'
        rt.event('simulator', 'Local PX4 heartbeat verified; disarmed')
        if args.board_binary:
            rt.vision = BoardVision(pixels, args.board_binary, board_log, rt.event,args.board_profile)
        if args.live_camera:
            from live_camera import LiveCameraVision
            rt.vision=LiveCameraVision(pixels,board_log,rt.event)
        next_tick = time.monotonic()
        while not stop.is_set():
            now = time.monotonic()
            if now < next_tick:
                # Transport is not a 20Hz control task: draining MAVROS only at
                # control ticks adds avoidable half-cycle delays in both directions.
                if args.transport=='mavros-15l':vehicle.poll()
                stop.wait(min(.005, next_tick-now))
                continue
            next_tick = max(next_tick+.05, now)
            if proc.poll() is not None or gz.poll() is not None:
                raise RuntimeError('owned simulator process exited')
            vehicle.poll()
            rt.gui_running=bool(gui and gui.poll() is None)
            if hasattr(vehicle,'status'):rt.mavros_status=vehicle.status()
            # This console is the local simulated ground station. PX4's stock
            # preflight check expects its heartbeat; do not disable that check.
            if now-heartbeat_at >= 1:
                vehicle._verify_simulator()
                vehicle.m.mav.heartbeat_send(vehicle.mavutil.mavlink.MAV_TYPE_GCS,
                    vehicle.mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                    vehicle.mavutil.mavlink.MAV_STATE_ACTIVE)
                heartbeat_at = now
            if args.transport=='mavros-15l' and vehicle.offset is None:
                # Startup waits must not swallow Stop from the operator.
                try:
                    early=rt.requests.get_nowait()
                    if early['action']=='stop':stop.set()
                    else:rt.event('rejected','ROS startup incomplete; request not executed')
                except queue.Empty:pass
                if now-started>90:raise TimeoutError('on-board ROS/MAVROS not ready')
                continue
            if vehicle.pos is None or (not takeoff and now-min(vehicle.last_position, vehicle.last_attitude) > .5):
                if now-started > 60:
                    raise TimeoutError('no fresh simulator position and attitude telemetry')
                continue
            rt.altitude = -vehicle.pos[2]
            rt.heading=math.degrees(vehicle.yaw)
            frame, _, clock, rtf = pixels.snapshot()
            if rt.vision:
                try:
                    result = rt.vision.results.get_nowait()
                    rt.accept(result)
                    out = result['output']
                    if pipeline:
                        pipeline.ingest(out, result.get('request_started_ns',result['received_ns']), time.monotonic_ns())
                    if out['lock']['id'] is not None and (pipeline is None or
                            pipeline.follow.identity != (out['source_id'],out['stream_id'],out['lock']['epoch'])):
                        following = False  # every new selection requires explicit Follow
                        pipeline = PerceptionAuthority(out['source_id'], out['stream_id'], out['lock']['epoch'],
                            execution='live', config=FollowConfig(min_height_frac=.02))
                        pipeline.ingest(out, result.get('request_started_ns',result['received_ns']), time.monotonic_ns())
                except queue.Empty:
                    pass
            if args.auto_demo and not takeoff and prime is None:
                rt.requests.put_nowait(dict(action='takeoff'))
            try:
                request = rt.requests.get_nowait()
                action = request['action']
                if action == 'takeoff' and not takeoff and not landing:
                    takeoff, prime, takeoff_at = True, now, now
                    rt.event('takeoff', 'Priming simulator setpoints')
                elif action == 'land':
                    landing, following, land_at = True, False, now
                    vehicle.land()
                elif action == 'follow':
                    if pipeline and takeoff and not landing and ready_at is not None:
                        following = True
                        if heading_response:heading_response.reset()
                    else:
                        rt.event('rejected', 'Take off and select a verified target first')
                elif action == 'hold':
                    following = False
                    auto_follow_started = True  # auto-demo must never undo operator Hold
                elif action == 'framing_reference':
                    fresh=bool(pipeline and pipeline.follow.current and time.monotonic_ns()<pipeline.follow.deadline)
                    rt.relative_framing=framing.sample(rt.result['output'] if rt.result and fresh else None,set_reference=True)
                    rt.event('framing_reference',rt.relative_framing)
                elif action == 'stop':
                    following = False
                    auto_follow_started = True
                    stop.set()  # finally lands, closes vision, then launcher restores desk
                elif action in ('pause', 'resume'):
                    # Recorded clip only: hold / continue the pixels; the clock and the board keep running.
                    getattr(rt.pixels, action)()
                elif action in ('select', 'select_id', 'release'):
                    following = False
                    if rt.vision:
                        cmd = {'select': dict(cmd='lock_point', x=request.get('x'), y=request.get('y'), sequence=request.get('sequence')),
                               'select_id': dict(cmd='select', id=request.get('id'), sequence=request.get('sequence')),
                               'release': dict(cmd='unlock')}[action]
                        rt.vision.command(cmd)
                elif action == 'video_stall' and rt.vision:
                    rt.vision.pause_until = now+2
                rt.event('operator', action)
            except queue.Empty:
                pass
            except queue.Full:
                following = False
                rt.event('rejected', 'selection queue busy; holding')
            if takeoff and not landing:
                # The stock Gazebo estimator needs a heading reference first.
                # Wait for this owned PX4 instance's health-ready report; never
                # force-arm or weaken a preflight parameter to make a demo pass.
                health_ready = prime is not None and b'Ready for takeoff!' in (args.out/'px4.log').read_bytes()
                if prime is not None and now-prime >= 2 and health_ready and getattr(vehicle,'ready_to_arm',True):
                    vehicle.arm()
                    vehicle.set_offboard()
                    prime = None
                if vehicle.armed and vehicle.mode == bridge.PX4_MAIN_MODE_OFFBOARD and abs(vehicle.pos[2]+2) < .3:
                    if ready_at is None:
                        ready_at = now
                        if args.replay:pixels.start()
                        rt.event('takeoff', 'Telemetry confirms offboard hover')
                    rt.flight = 'Hover / offboard'
                else:
                    rt.flight = 'Taking off'
                    if now-takeoff_at > 45 and ready_at is None:
                        raise TimeoutError('takeoff not confirmed')
            if args.auto_demo and ready_at is not None and not landing:
                elapsed = now-ready_at
                if not selected_once and rt.result:
                    candidates = [t for t in rt.result['output']['tracks'] if t['label'] == 'person' and not t['coasting'] and not t['ambiguous']]
                    if args.initial_point and elapsed>=.8:
                        rt.action(dict(action='select',x=args.initial_point[0],y=args.initial_point[1],sequence=rt.result['sequence']))
                        selected_once=True;select_at=now;select_sequence=rt.result['sequence']
                    elif not args.initial_point and len(candidates) == 1:
                        rt.action(dict(action='select_id', id=candidates[0]['id'], sequence=rt.result['sequence']))
                        selected_once = True
                elif (selected_once and args.initial_point and args.select_retry_s>0 and rt.result and now-select_at<=args.select_retry_s
                      and rt.result['output']['lock'].get('id') is None and rt.result['sequence']!=select_sequence):
                    # Labelled retry: a refused click (no descriptor yet, no confirmed track yet) is repeated
                    # on later frames within the window, as a person would click again. Off by default.
                    rt.action(dict(action='select',x=args.initial_point[0],y=args.initial_point[1],sequence=rt.result['sequence']))
                    select_sequence=rt.result['sequence']
                if not auto_follow_started and pipeline and pipeline.follow.current is not None:
                    following = True
                    auto_follow_started = True
                if elapsed >= 20 and not stalled:
                    rt.action(dict(action='video_stall'))
                    stalled = True
                if elapsed >= args.duration:
                    landing, following, land_at = True, False, now
                    vehicle.land()
                    rt.event('land', 'Automatic trial complete; simulator landing')
            now_ns = time.monotonic_ns()
            intent = pipeline.tick(now_ns) if pipeline else None
            eligible = guarded_intent(intent, rt.result, clock, now_ns, following and not landing)
            if heading_response:
                eligible=heading_response.apply(eligible,rt.result['output']['lock']['box'] if rt.result else None,vehicle.yaw)
                rt.requested_heading=math.degrees(heading_response.desired) if heading_response.desired is not None else None
                if rt.result:rt.result['heading_response_ned']=heading_response.desired
                if args.live_camera and rt.result:
                    rt.result['heading_reference_ned']=heading_response.reference
                    rt.result['camera_hfov']=args.replay_hfov
            sp = bridge.setpoint_from_intent(eligible, vehicle.yaw, -2., now_ns)
            rt.requested_setpoint=vars(sp)
            rt.relative_framing=framing.sample(rt.result['output'] if rt.result and intent and intent.command_eligible and not intent.expired(now_ns) else None)
            rt.reason = intent.reason if intent else 'Select a target to establish an identity-bound session'
            if following and eligible is None:
                rt.reason = 'Holding: '+rt.reason+' / ingress or simulation-clock gate'
            rt.command = 'FOLLOW' if not sp.hover else 'HOLD'
            rt.follow_enabled=following and not landing
            rt.control_deadline_ns=eligible.t_ns+eligible.ttl_ns if eligible else 0
            if rt.command != previous_command:
                rt.event('command', dict(mode=rt.command, reason=rt.reason))
                previous_command = rt.command
            if takeoff and not landing:
                vehicle.send_setpoint(sp, int((now-started)*1000),
                    expires_ns=eligible.t_ns+eligible.ttl_ns if eligible else None,
                    source={k:rt.result.get(k) for k in ('output','range_m','depth_paired','heading_response_ned','heading_reference_ned','camera_hfov')} if rt.result else None)
            if landing:
                rt.flight = 'Landing' if vehicle.armed else 'Landed / disarmed'
                if not vehicle.armed and now-land_at > 2:
                    takeoff = False
                    if args.auto_demo:
                        finish_after_tick = True
                    else:
                        landing, ready_at, land_at = False, None, None
                elif now-land_at > 30:
                    raise TimeoutError('simulator did not confirm disarm')
            row = dict(t_ns=now_ns, elapsed_s=now-started, armed=vehicle.armed, mode=vehicle.mode,
                position_ned=vehicle.pos, yaw=vehicle.yaw, rtf=rtf,
                source_sim_lag_ms=(clock[0]-rt.result['sim_ns'])/1e6 if clock and rt.result else None,
                flight=rt.flight, following=following, setpoint=vars(sp),
                intent=intent.to_dict() if intent else None,
                # Compact board summary per tick. The full board result (raw detections, every
                # track) is ~80 KB and ticks run at 20 Hz: an interactive session wrote 100 GB
                # overnight (2026-09-16). Per-frame board rows belong to console_capture.py.
                source=(dict({k:rt.result.get(k) for k in ('sequence','age_ms','range_m','depth_paired','detector_passes',
                                                            'roi_reason','global','schedule','heading_response_ned','camera_hfov')},
                             lock=(rt.result.get('output') or {}).get('lock'),
                             tracks=len((rt.result.get('output') or {}).get('tracks') or []),
                             raw_detections=len(rt.result.get('raw_detections') or [])) if rt.result else None))
            if hasattr(vehicle,'status'):
                rt.mavros_status=vehicle.status()
                row['mavros']={k:v for k,v in rt.mavros_status.items() if k!='link_log'} if isinstance(rt.mavros_status,dict) else rt.mavros_status
            evidence.write(json.dumps(row, allow_nan=False)+'\n')
            evidence.flush()
            if finish_after_tick:
                rt.event('land', 'Telemetry confirms landed and disarmed')
                break
    finally:
        if vehicle and proc and proc.poll() is None:
            try:
                vehicle.poll()
                if vehicle.armed:
                    vehicle.land()
                    until = time.monotonic()+20
                    while vehicle.armed and time.monotonic() < until:
                        time.sleep(.1)
                        vehicle.poll()
            except Exception as error:
                rt.event('cleanup_error', str(error))
                if hasattr(vehicle,'emergency_land'):
                    vehicle.emergency_land()
                    until=time.monotonic()+20
                    while vehicle.armed and time.monotonic()<until:
                        time.sleep(.1);vehicle.poll()
        if vehicle:
            rt.event('cleanup_vehicle', dict(armed=vehicle.armed, mode=vehicle.mode,
                telemetry_age_ms=(time.monotonic()-vehicle.last_heartbeat)*1000))
        if rt.vision:
            rt.vision.close()
        if hasattr(vehicle,'close'):
            vehicle.close()
        for child in (gui, proc, gz):
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        (args.out/'events.json').write_text(json.dumps(list(rt.events), indent=2)+'\n')
        server.shutdown()
        for handle in logs+[board_log, evidence, event_log]:
            handle.close()


if __name__ == '__main__':
    main()
