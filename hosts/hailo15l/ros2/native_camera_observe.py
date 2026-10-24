"""Bounded on-board native camera -> ROS 2 -> freshness observer. NO MAVROS I/O."""
import argparse
import json
import math
import os
import queue
import socket
import threading
import time

from native_camera import LocalCameraGate, read_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clock-domain', required=True)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--freeze-after', type=float, default=0,
                        help='stop publishing camera samples after this time; observer keeps ticking')
    args = parser.parse_args()
    if os.environ.get('GARUDA_SIM') != '1':
        raise PermissionError('explicit bench environment required')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 60:
        parser.error('duration must be 0..60 seconds')
    if not math.isfinite(args.freeze_after) or not 0 <= args.freeze_after < args.seconds:
        parser.error('freeze must precede end')
    gate = LocalCameraGate(args.clock_domain)
    import rclpy
    from rclpy.node import Node
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from std_msgs.msg import String
    rclpy.init(args=[])
    ingress = Node('garuda_native_camera_ingress')
    observer = Node('garuda_native_camera_observer')
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                     durability=DurabilityPolicy.VOLATILE)
    pub = ingress.create_publisher(String, '/garuda/camera/native_snapshot', qos)
    counts = dict(native_received=0, ros_received=0, errors=0)
    latest = queue.Queue(maxsize=1)
    stop = threading.Event()
    started = time.monotonic()

    def receive(msg):
        counts['ros_received'] += 1
        gate.ingest(json.loads(msg.data), time.monotonic_ns())

    observer.create_subscription(String, '/garuda/camera/native_snapshot', receive, qos)

    def read_native():
        while not stop.is_set():
            try:
                with socket.create_connection(('127.0.0.1', 8981), timeout=.5) as stream:
                    while not stop.is_set():
                        row = read_packet(stream)
                        if row is None:
                            continue
                        counts['native_received'] += 1
                        try:
                            latest.get_nowait()
                        except queue.Empty:
                            pass
                        latest.put_nowait(row)
            except (OSError, ValueError, EOFError):
                counts['errors'] += 1
                stop.wait(.1)

    def publish():
        if args.freeze_after and time.monotonic()-started >= args.freeze_after:
            return
        try:
            row = latest.get_nowait()
        except queue.Empty:
            return
        msg = String()
        msg.data = json.dumps(row, allow_nan=False)
        pub.publish(msg)

    def status():
        print(json.dumps(dict(gate.status(time.monotonic_ns()), **counts), allow_nan=False), flush=True)

    ingress.create_timer(.02, publish)
    observer.create_timer(.05, status)
    executor = SingleThreadedExecutor()
    executor.add_node(ingress)
    executor.add_node(observer)
    worker = threading.Thread(target=read_native, daemon=True)
    worker.start()
    try:
        while time.monotonic()-started < args.seconds:
            executor.spin_once(timeout_sec=.05)
    finally:
        stop.set()
        worker.join(timeout=1)
        executor.shutdown()
        observer.destroy_node()
        ingress.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
