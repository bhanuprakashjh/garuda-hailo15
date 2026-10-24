"""Prepare timestamp-matched 4K replay inputs; never upscale a smaller recording."""
import argparse
import hashlib
import json
import pathlib
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('recording', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
group=p.add_mutually_exclusive_group()
group.add_argument('--centered-only', action='store_true', help='Exploratory oracle-centered size sweep, not automatic tracking')
group.add_argument('--baseline-with-centered', action='store_true', help='Five current-path tiles plus three oracle crops per source frame')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
rows = [json.loads(s) for s in (a.recording/'frames.jsonl').read_text().splitlines()]
rows = [r for r in rows if 'frame' in r]
base = int(rows[0]['source_timestamp_ns'])
by_pts = {int(r['source_timestamp_ns'])-base: r for r in rows}
wanted = {90, 360, 630}
decoded = {}
errors = []
Gst.init(None)
pipeline = Gst.parse_launch('appsrc name=src block=true max-bytes=4194304 format=time '
    'caps=video/x-h264,stream-format=byte-stream,alignment=au ! h264parse ! avdec_h264 ! '
    'videoconvert ! video/x-raw,format=NV12 ! appsink name=sink emit-signals=true sync=false max-buffers=2 drop=false')
src = pipeline.get_by_name('src')
def sample(sink):
    s = sink.emit('pull-sample')
    b = s.get_buffer()
    try:
        caps = s.get_caps().get_structure(0)
        if (caps.get_value('width'), caps.get_value('height')) != (3840, 2160):
            raise ValueError('Native 3840x2160 recording required')
        row = by_pts[b.pts]
        if row['frame'] in wanted:
            data = b.extract_dup(0, b.get_size())
            if len(data) != 3840*2160*3//2:
                raise ValueError('Unexpected NV12 layout')
            decoded[row['frame']] = data
        return Gst.FlowReturn.OK
    except Exception as e:
        errors.append(str(e))
        return Gst.FlowReturn.ERROR
pipeline.get_by_name('sink').connect('new-sample', sample)
def feed():
    try:
        with (a.recording/'video.h264').open('rb') as f:
            for r in rows:
                data = f.read(r['bytes'])
                if len(data) != r['bytes']:
                    raise ValueError('Truncated recording')
                b = Gst.Buffer.new_wrapped(data)
                b.pts = int(r['source_timestamp_ns'])-base
                b.dts = Gst.CLOCK_TIME_NONE
                if src.emit('push-buffer', b) != Gst.FlowReturn.OK:
                    break
        src.emit('end-of-stream')
    except Exception as e:
        errors.append(str(e))
        src.emit('end-of-stream')
pipeline.set_state(Gst.State.PLAYING)
thread = threading.Thread(target=feed, daemon=True)
thread.start()
try:
    msg = pipeline.get_bus().timed_pop_filtered(55*Gst.SECOND, Gst.MessageType.EOS|Gst.MessageType.ERROR)
    if msg is None or msg.type == Gst.MessageType.ERROR or errors:
        raise RuntimeError(str(errors or (msg.parse_error() if msg else 'Decode timeout')))
finally:
    pipeline.set_state(Gst.State.NULL)
    thread.join(timeout=3)
if set(decoded) != wanted:
    raise ValueError('Missing selected source frames')

def starts(extent):
    return sorted(set([*range(0, extent-640+1, 512), extent-640]))
regions = []
digest = hashlib.sha256()
with (a.output/'source.nv12').open('xb') as out:
    for frame, data in sorted(decoded.items()):
        layouts = [('via1080', x, y, 2304, 1296, True)
                   for y in (0, 864) for x in (0, 1536)]
        layouts += [('via1080', 0, 0, 3840, 2160, True)]
        layouts += [('native4k', x, y, 640, 640, False)
                    for y in starts(2160) for x in starts(3840)]
        if a.centered_only or a.baseline_with_centered:
            from score_4k_tiles import ANNOTATIONS
            box = ANNOTATIONS[frame]
            cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
            centered = [(f'oracle{side}', int(max(0, min(3840-side, cx-side/2))//2)*2,
                        int(max(0, min(2160-side, cy-side/2))//2)*2, side, side, False)
                       for side in (640, 960, 1280)]
            layouts = (layouts[:5] if a.baseline_with_centered else [])+centered
        for method, x, y, w, h, via in layouts:
            regions.append(dict(source_w=3840, source_h=2160, x=x, y=y, w=w, h=h,
                full_frame=(w==3840), via_1080p=via, method=method,
                source_frame=frame, source_timestamp_ns=next(r['source_timestamp_ns'] for r in rows if r['frame']==frame)))
            out.write(data)
            digest.update(data)
(a.output/'regions.json').write_text(json.dumps(regions, indent=2))
(a.output/'manifest.json').write_text(json.dumps(dict(source_sha256=digest.hexdigest(),
    recording=str(a.recording.resolve()), frames=sorted(decoded), inputs=len(regions), oracle_centered=a.centered_only or a.baseline_with_centered,
    baseline_with_centered=a.baseline_with_centered,
    caveat='Decoded H264, not original NV12. Via1080 uses bilinear DSP approximation of frontend resize. Sparse detection test, not tracking or recall.'), indent=2))
print(json.dumps(dict(frames=sorted(decoded), inputs=len(regions), source_sha256=digest.hexdigest())))
