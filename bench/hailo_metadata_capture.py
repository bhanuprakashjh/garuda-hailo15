"""Record every native diagnostic message, not polling samples. No board mutations."""
import argparse
import json
import pathlib
import sys
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('stage',type=pathlib.Path)
parser.add_argument('output',type=pathlib.Path)
parser.add_argument('--seconds',type=float,default=15)
parser.add_argument('--source',default='ws://10.0.0.1:8765')
args=parser.parse_args()
sys.path[:0]=[str(args.stage),str(args.stage/'vendor')]
import websocket
import hailo_adapter as adapter
Frame=adapter.load_frame_type(args.stage/'analytics_metadata.desc')
counts=dict(frames=0,detector_frames=0,empty_track_frames=0,raw_phone_frames=0,tracked_phone_frames=0,
            alignment_mismatches=0,timeouts=0,repeated_timestamps=0)
previous=None;last_arrival=None;max_gap=0
with args.output.open('x') as output:
    ws=websocket.create_connection(args.source,timeout=2,suppress_origin=True)
    start=time.monotonic()
    try:
        while time.monotonic()-start<args.seconds:
            try: payload=ws.recv()
            except websocket.WebSocketTimeoutException:
                counts['timeouts']+=1;continue
            now=time.monotonic();f=Frame.FromString(payload)
            _,tracks=adapter.decode_tracks(f,'all');d=adapter.decode_diagnostics(f)
            counts['frames']+=1;counts['empty_track_frames']+=not tracks
            counts['tracked_phone_frames']+=any(t['label']=='cell phone' for t in tracks)
            if d:
                counts['detector_frames']+=d['detector_ran']
                counts['raw_phone_frames']+=d['detector_ran'] and any(t['label']=='cell phone' for t in d['raw'])
                counts['alignment_mismatches']+=not d['aligned']
            counts['repeated_timestamps']+=previous==f.isp_timestamp_ns
            if last_arrival is not None:max_gap=max(max_gap,now-last_arrival)
            last_arrival=now;previous=f.isp_timestamp_ns
            output.write(json.dumps(dict(arrival_elapsed_ms=(now-start)*1000,
                source_timestamp_ns=str(f.isp_timestamp_ns),frame=dict(width=f.frame_width,height=f.frame_height),
                tracks=tracks,diagnostics=d),allow_nan=False)+'\n')
    finally:ws.close()
summary=dict(**counts,elapsed_seconds=time.monotonic()-start,max_arrival_gap_ms=max_gap*1000,
             note='Counts are metadata/marked detector frames, not independently measured NPU throughput or accuracy.')
with args.output.with_suffix('.summary.json').open('x') as output:json.dump(summary,output,indent=2)
print(json.dumps(summary,indent=2))
