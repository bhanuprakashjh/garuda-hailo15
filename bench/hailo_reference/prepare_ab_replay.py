"""Prepare a full-sequence five-tile replay: each decodable source frame once,
its four corner tiles and full view expressed as reuse_source regions.

Every 2nd decodable frame is selected by default, matching the live pipeline's
every-other-frame detector cadence. Decoded H264 is not original NV12; the
via-1080p first resize approximates the frontend with bilinear DSP.
"""
import argparse
import hashlib
import json
import pathlib
import threading
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

TILES = [(x, y, 2304, 1296) for y in (0, 864) for x in (0, 1536)] + [(0, 0, 3840, 2160)]

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('recording', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
p.add_argument('--first-frame', type=int, default=35, help='First decodable index (after SPS/IDR)')
p.add_argument('--step', type=int, default=2, help='Frame stride; 2 matches live detector cadence')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
rows = [json.loads(s) for s in (a.recording/'frames.jsonl').read_text().splitlines()]
rows = [r for r in rows if 'frame' in r]
base = int(rows[0]['source_timestamp_ns'])
by_pts = {int(r['source_timestamp_ns'])-base: r for r in rows}
wanted = set(range(a.first_frame, rows[-1]['frame']+1, a.step))
regions, errors = [], []
digest = hashlib.sha256()
out = (a.output/'source.nv12').open('xb')
last_written = [-1]
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
        if row['frame'] not in wanted:
            return Gst.FlowReturn.OK
        # Stream-write requires decode order == presentation order; refuse reordering.
        if row['frame'] <= last_written[0]:
            raise ValueError('Non-monotonic decoded frame order')
        data = b.extract_dup(0, b.get_size())
        if len(data) != 3840*2160*3//2:
            raise ValueError('Unexpected NV12 layout')
        out.write(data)
        digest.update(data)
        last_written[0] = row['frame']
        for index, (x, y, w, h) in enumerate(TILES):
            regions.append(dict(source_w=3840, source_h=2160, x=x, y=y, w=w, h=h,
                full_frame=(w == 3840), via_1080p=True, reuse_source=index > 0,
                method='via1080', source_frame=row['frame'],
                source_timestamp_ns=row['source_timestamp_ns']))
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
    msg = pipeline.get_bus().timed_pop_filtered(600*Gst.SECOND, Gst.MessageType.EOS|Gst.MessageType.ERROR)
    if msg is None or msg.type == Gst.MessageType.ERROR or errors:
        raise RuntimeError(str(errors or (msg.parse_error() if msg else 'Decode timeout')))
finally:
    pipeline.set_state(Gst.State.NULL)
    thread.join(timeout=3)
    out.close()
frames = sorted({r['source_frame'] for r in regions})
if not frames or len(regions) != len(frames)*len(TILES):
    raise ValueError('Incomplete tile coverage')
(a.output/'regions.json').write_text(json.dumps(regions, indent=2))
(a.output/'manifest.json').write_text(json.dumps(dict(source_sha256=digest.hexdigest(),
    recording=str(a.recording.resolve()), first_frame=a.first_frame, step=a.step,
    frames=len(frames), frame_min=frames[0], frame_max=frames[-1], inputs=len(regions),
    caveat='Decoded H264, not original NV12. Via1080 uses bilinear DSP approximation of '
           'frontend resize. Detector-only sequence replay: no tracker, no live FPS.'), indent=2))
print(json.dumps(dict(frames=len(frames), frame_min=frames[0], frame_max=frames[-1],
    inputs=len(regions), source_sha256=digest.hexdigest())))
