"""Decode recorded access units with their source timestamps; sample review JPEGs."""
import argparse
import json
import pathlib
import threading
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst
from PIL import Image

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('recording',type=pathlib.Path)
p.add_argument('output',type=pathlib.Path)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
index=[json.loads(s) for s in (a.recording/'frames.jsonl').read_text().splitlines()]
frames=[r for r in index if 'frame' in r];base=int(frames[0]['source_timestamp_ns'])
by_pts={int(r['source_timestamp_ns'])-base:r for r in frames}
Gst.init(None)
pipeline=Gst.parse_launch('appsrc name=src block=true max-bytes=4194304 format=time '
    'caps=video/x-h264,stream-format=byte-stream,alignment=au ! h264parse ! avdec_h264 ! '
    'videoscale ! videoconvert ! video/x-raw,format=RGB,width=960,height=540 ! '
    'appsink name=sink emit-signals=true sync=false max-buffers=2 drop=false')
src=pipeline.get_by_name('src');sink=pipeline.get_by_name('sink')
decoded=[];errors=[]
def sample(sink):
    sample=sink.emit('pull-sample');buffer=sample.get_buffer()
    try:
        row=by_pts.get(buffer.pts)
        if row is None:raise ValueError('Decoder output timestamp not in source index')
        decoded.append(row['frame'])
        if row['frame']%90==0:
            ok,mapped=buffer.map(Gst.MapFlags.READ)
            if not ok:raise ValueError('Cannot map decoded frame')
            try:
                if len(mapped.data)!=960*540*3:raise ValueError('Unexpected RGB stride')
                Image.frombytes('RGB',(960,540),bytes(mapped.data)).save(a.output/f"frame-{row['frame']:04d}.jpg")
            finally:buffer.unmap(mapped)
        return Gst.FlowReturn.OK
    except Exception as error:
        errors.append(str(error));return Gst.FlowReturn.ERROR
sink.connect('new-sample',sample)
def feed():
    try:
        with (a.recording/'video.h264').open('rb') as video:
            for row in frames:
                data=video.read(row['bytes'])
                if len(data)!=row['bytes']:raise ValueError('Truncated access unit')
                buffer=Gst.Buffer.new_wrapped(data)
                buffer.pts=int(row['source_timestamp_ns'])-base
                buffer.dts=Gst.CLOCK_TIME_NONE
                if src.emit('push-buffer',buffer)!=Gst.FlowReturn.OK:break
        src.emit('end-of-stream')
    except Exception as error:errors.append(str(error));src.emit('end-of-stream')
pipeline.set_state(Gst.State.PLAYING)
thread=threading.Thread(target=feed,daemon=True);thread.start()
try:
    message=pipeline.get_bus().timed_pop_filtered(55*Gst.SECOND,Gst.MessageType.EOS|Gst.MessageType.ERROR)
    if message is None:raise RuntimeError('Decode timed out')
    if message.type==Gst.MessageType.ERROR:raise RuntimeError(str(message.parse_error()))
    if errors:raise RuntimeError(str(errors))
finally:
    pipeline.set_state(Gst.State.NULL);thread.join(timeout=3)
report=dict(decoded_frames=len(decoded),first_decoded_frame=min(decoded),last_decoded_frame=max(decoded),
            unique_source_frames=len(set(decoded)),review_frames=sorted(p.name for p in a.output.glob('*.jpg')))
(a.output/'decode.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
