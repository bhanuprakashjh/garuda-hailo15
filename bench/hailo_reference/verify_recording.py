"""Validate bounded H264 access-unit recording and exact metadata timestamp joins."""
import argparse
import json
import pathlib
import re

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('video_dir',type=pathlib.Path)
p.add_argument('metadata',type=pathlib.Path)
a=p.parse_args()
index=[json.loads(s) for s in (a.video_dir/'frames.jsonl').read_text().splitlines()]
assert index[-1].get('end') and index[-1]['reason']=='frame_limit', 'incomplete capture'
frames=index[:-1]; video=(a.video_dir/'video.h264').read_bytes()
assert len(frames)==index[-1]['frames']==900
assert len(video)==index[-1]['bytes']<=64*1024*1024
rows=[json.loads(s) for s in a.metadata.read_text().splitlines()]
by_time={r['source_timestamp_ns']:r for r in rows}
assert len(by_time)==len(rows),'duplicate metadata timestamps'
offset=0;previous=-1;matches=0;first_sps=None;first_idr=None
for i,f in enumerate(frames):
    assert f['frame']==i and f['offset']==offset and f['bytes']>0
    stamp=int(f['source_timestamp_ns']);assert stamp>previous;previous=stamp
    unit=video[offset:offset+f['bytes']]
    types=[m[0]&31 for m in re.findall(b'\x00\x00(?:\x00)?\x01(.)',unit,re.DOTALL)]
    if 7 in types and first_sps is None:first_sps=i
    if 5 in types and first_idr is None:first_idr=i
    matches+=f['source_timestamp_ns'] in by_time
    offset+=f['bytes']
assert offset==len(video)
assert first_sps is not None and first_idr is not None,'no decodable keyframe headers'
print(json.dumps(dict(encoded_frames=len(frames),metadata_messages=len(rows),
    exact_timestamp_matches=matches,unmatched_encoded_frames=len(frames)-matches,
    first_sps_frame=first_sps,first_idr_frame=first_idr,
    note='Unmatched frames are explicitly missing metadata; never nearest-time substituted. '
         'Initial frames before codec headers/keyframe may not decode. Encoded video is not original NV12.'),indent=2))
