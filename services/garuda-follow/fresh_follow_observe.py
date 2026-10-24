#!/usr/bin/env python3
"""Read-only board-to-follow demonstration. Emits decisions; never connects to a vehicle.

The HTTP worker is separate from the control tick so a blocked request cannot keep
an old command alive. The selected source/stream/epoch is explicitly pinned once.
"""
import argparse
import json
import queue
import threading
import time
import urllib.request
from fresh_target_adapter import from_fresh
from fresh_follow import FreshFollow


def poll(url, stop, messages):
    while not stop.is_set():
        started = time.monotonic_ns()
        try:
            separator = '&' if '?' in url else '?'
            request = urllib.request.Request(url+separator+'fresh_nonce='+str(started),
                                             headers={'Cache-Control':'no-cache, no-store'})
            with urllib.request.urlopen(request, timeout=.3) as response:
                raw = response.read(512*1024+1)
            if len(raw) > 512*1024:
                raise ValueError('oversize snapshot')
            value = from_fresh(json.loads(raw))
            item = (value,started,time.monotonic_ns(),None)
        except Exception as error:
            item = (None,started,time.monotonic_ns(),type(error).__name__)
        try:
            messages.put_nowait(item)
        except queue.Full:
            try:messages.get_nowait()
            except queue.Empty:pass
            messages.put_nowait(item)
        stop.wait(.025)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://10.0.0.1:8099/api/state')
    parser.add_argument('--source-id',required=True)
    parser.add_argument('--stream-id',required=True)
    parser.add_argument('--epoch',type=int,required=True)
    parser.add_argument('--duration',type=float,default=30)
    args = parser.parse_args()
    if not 0 < args.duration <= 600:
        parser.error('duration must be in (0,600] seconds')
    follow = FreshFollow(args.source_id,args.stream_id,args.epoch)
    stop,messages = threading.Event(),queue.Queue(maxsize=1)
    worker = threading.Thread(target=poll,args=(args.url,stop,messages),daemon=True)
    worker.start()
    end = time.monotonic()+args.duration
    try:
        while time.monotonic() < end:
            try:
                observation,started,received,error = messages.get_nowait()
                if error:follow.reject('transport_'+error)
                else:follow.ingest(observation,started,received)
            except queue.Empty:
                pass
            print(json.dumps(follow.tick(time.monotonic_ns()).to_dict(),allow_nan=False),flush=True)
            stop.wait(.05)
    finally:
        stop.set();worker.join(timeout=.5)


if __name__ == '__main__':
    main()
