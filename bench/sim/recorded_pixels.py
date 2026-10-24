"""Real prerecorded NV12 pixels, unchanged to Hailo; independent Gazebo overview.

Playback rate and camera FOV are declared assumptions, not recovered metadata.
No per-frame labels enter the detector/controller. EOF naturally expires vision.
"""
import hashlib
import json
import math
import pathlib
import threading
import time
from dataclasses import replace
import numpy as np


def full_nv12_rgb(raw):
    p=np.frombuffer(raw,dtype=np.uint8).astype(np.float32)
    y=p[:1280*720].reshape(720,1280)
    uv=p[1280*720:].reshape(360,1280)
    u=uv[:,::2].repeat(2,0).repeat(2,1)-128;v=uv[:,1::2].repeat(2,0).repeat(2,1)-128
    return np.stack([y+1.4*v,y-.343*u-.711*v,y+1.765*u],-1).round().clip(0,255).astype(np.uint8)


class ReplayPixels:
    """loop=False: the clip plays once and its last frame is held, so vision expires at EOF (the
    frozen evidence protocol). loop=True: the clip restarts from its first frame when it ends,
    with the sequence and the declared clock continuing, so an operator can take off, click and
    watch at their own pace; the loop count is reported and shown, because a loop boundary is
    a cut the tracker must survive, not footage."""
    def __init__(self, directory, overview, fps, loop=False):
        self.directory=pathlib.Path(directory)
        self.world=overview
        if not 1<=fps<=60:raise ValueError('bounded declared replay FPS required')
        self.period=1/fps;self.loop=bool(loop);self.loops=0
        self.manifest=json.loads((self.directory/'manifest.json').read_text())
        self.path=self.directory/'source.nv12'
        self.size=1280*720*3//2
        digest=hashlib.sha256()
        with self.path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        if (self.manifest['canvas']!=[1280,720] or self.path.stat().st_size!=self.size*self.manifest['frames']
                or digest.hexdigest()!=self.manifest['source_sha256']):raise ValueError('replay geometry/hash mismatch')
        self.memory=np.memmap(self.path,dtype=np.uint8,mode='r',shape=(self.manifest['frames'],self.size))
        self.lock=threading.RLock();self.depths={}
        self.started=None;self.latest=None;self.index=-1;self.played=-1;self.sequence=0
        self.raw_indices={}
        # Operator pause (looping clips only): the pixels hold on one frame while the declared
        # clock keeps running and fresh frames keep being released, so the board keeps detecting
        # on a still picture and a selection can be made at leisure; resume continues from the
        # held frame (the pause is taken out of the clip position, never out of the clock).
        self.pinned=None;self.offset=0
        self.snapshot()

    @property
    def overview(self):return self.world.overview

    @property
    def paused(self):return self.pinned is not None

    def start(self):
        with self.lock:
            if self.started is None:self.started=time.monotonic();self.index=-1;self.played=-1

    def pause(self):
        with self.lock:
            if self.loop and self.started is not None and self.pinned is None:self.pinned=self.played-self.offset

    def resume(self):
        with self.lock:
            if self.pinned is not None:self.offset=self.played-self.pinned;self.pinned=None

    def snapshot(self):
        with self.lock:
            now=time.monotonic_ns()
            elapsed=max(0.,now/1e9-self.started) if self.started else 0.
            played=int(elapsed/self.period);frames=self.manifest['frames']
            # The declared clock (sim_ns) always runs on the played count; only the pixels wrap.
            position=self.pinned if self.pinned is not None else played-self.offset
            index=position%frames if self.loop else min(position,frames-1)
            if self.loop:self.loops=position//frames
            if self.index!=index or (self.loop and self.played!=played):
                self.index=index;self.played=played;self.sequence+=1
                # Declared time of the released frame: the played count when looping (it keeps
                # growing across wraps); the clip's own frame time otherwise (held at EOF).
                stamp=played if self.loop else index
                capture=now-int((elapsed-stamp*self.period)*1e9) if self.started else now
                self.latest=(self.sequence,int(stamp*self.period*1e9),capture,full_nv12_rgb(self.memory[index]))
                self.raw_indices[self.sequence]=index
                while len(self.raw_indices)>8:self.raw_indices.pop(next(iter(self.raw_indices)))
            return self.latest,None,(int(elapsed*1e9),now),1.

    def raw(self,sequence):
        with self.lock:
            if sequence not in self.raw_indices:raise ValueError('replay frame expired before read')
            return self.memory[self.raw_indices[sequence]].tobytes()


class HeadingResponse:
    def __init__(self,hfov):
        if not math.isfinite(hfov) or not .2<hfov<2.8:raise ValueError('invalid declared HFOV')
        self.hfov=hfov;self.reference=None;self.desired=None

    def reset(self):self.reference=self.desired=None

    def apply(self,intent,box,yaw):
        if intent is None or not intent.command_eligible or box is None:return intent
        if self.reference is None:self.reference=yaw
        cx=(box['x']+box['w']/2)/1280
        bearing=math.atan((2*cx-1)*math.tan(self.hfov/2))
        self.desired=self.reference+max(-math.pi/6,min(math.pi/6,bearing))
        error=math.atan2(math.sin(self.desired-yaw),math.cos(self.desired-yaw))
        return replace(intent,forward_vel=0.,yaw_rate=max(-.8,min(.8,error*2)))
