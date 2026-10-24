"""Simulation perception sources. Board mode is transport-in-loop, not a rendered camera.

The native Tracker source uses synthetic detections and idealized appearance;
it tests the real tracker/transport/controller, never claims YOLO accuracy.
"""
import json
import pathlib
import queue
import subprocess
import threading
import time
import urllib.request
from perception_authority import PerceptionAuthority


class NativeTrackerSource:
    def __init__(self,binary,config):
        self.proc=subprocess.Popen([str(binary),"-"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        self.sequence=0;self.selected=False
        self.pipeline=None;self.config=config

    def exchange(self,row):
        self.proc.stdin.write(json.dumps(row)+"\n");self.proc.stdin.flush()
        # The native peer is local and processes one bounded JSON row. Poll with
        # a deadline so a hung child never stalls the simulation publisher forever.
        import select
        if not select.select([self.proc.stdout],[],[],.5)[0]:raise TimeoutError("native tracker response timed out")
        line=self.proc.stdout.readline()
        if not line:raise RuntimeError("native tracker exited")
        return json.loads(line)

    def update(self,box,now_ns):
        self.sequence+=1;capture=now_ns/1e6
        dets=[]
        if box:
            x,y,w,h=box
            dets=[dict(box=dict(x=x,y=y,w=w,h=h),label="person",confidence=.9,
                       appearance=[1.]+[0.]*71)]
        out=self.exchange(dict(sequence=self.sequence,capture_ms=capture,now_ms=capture+1,
                               timestamp_valid=True,detections=dets))
        if not self.selected and self.sequence>=5 and box:
            result=self.exchange(dict(cmd="lock_point",x=(box[0]+box[2]/2)*1280,
                y=(box[1]+box[3]/2)*720,sequence=self.sequence,now_ms=capture+2))
            self.selected=bool(result.get('ok'))
            out=self.exchange(dict(heartbeat_ms=capture+2))
        sample=out['publish_monotonic_ms']
        out.update(source_id="sil.native_tracker",stream_id=str(self.proc.pid),clock_domain="sil.monotonic",
                   sample_monotonic_ms=sample,freshness_budget_ms=200.,
                   valid_for_ms=max(0.,200-out['lock']['obs_age_ms']))
        if self.selected and self.pipeline is None:
            self.pipeline=PerceptionAuthority(out['source_id'],out['stream_id'],out['lock']['epoch'],
                execution="live",config=self.config,framing_translation=True)
        if self.pipeline:
            # Charge synthetic processing time in the source age, not future receiver time.
            self.pipeline.ingest(out,now_ns,now_ns)
        return out

    def tick(self,now_ns):
        return self.pipeline.tick(now_ns) if self.pipeline else None

    def close(self):
        self.proc.terminate()
        try:self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()


class BoardSource:
    def __init__(self,url,config):
        self.url=url;self.config=config;self.pipeline=None
        self.messages=queue.Queue(maxsize=1);self.stop=threading.Event()
        self.worker=threading.Thread(target=self.poll,daemon=True);self.worker.start()
        self.samples=0;self.errors=0

    def poll(self):
        while not self.stop.is_set():
            started=time.monotonic_ns()
            try:
                with urllib.request.urlopen(self.url,timeout=.3) as response:
                    raw=response.read(512*1024+1)
                if len(raw)>512*1024:raise ValueError("oversize board envelope")
                item=(json.loads(raw),started,time.monotonic_ns(),None)
            except Exception as e:item=(None,started,time.monotonic_ns(),str(e))
            try:self.messages.get_nowait()
            except queue.Empty:pass
            self.messages.put_nowait(item)
            self.stop.wait(.025)

    def tick(self,now_ns):
        try:
            row,started,received,error=self.messages.get_nowait()
            if error:
                self.errors+=1
                if self.pipeline:self.pipeline.reject("board_transport_error")
            else:
                self.samples+=1
                if self.pipeline is None and row['lock'].get('id') is not None and row['lock'].get('epoch',0)>0:
                    self.pipeline=PerceptionAuthority(row['source_id'],row['stream_id'],row['lock']['epoch'],
                        execution="live",config=self.config,framing_translation=False)
                if self.pipeline:self.pipeline.ingest(row,started,received)
        except queue.Empty:pass
        except (KeyError,TypeError,ValueError,OverflowError):
            self.errors+=1
            if self.pipeline:self.pipeline.reject("invalid_board_envelope")
        return self.pipeline.tick(max(now_ns,time.monotonic_ns())) if self.pipeline else None

    def close(self):
        self.stop.set();self.worker.join(timeout=.5)
