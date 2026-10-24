#!/usr/bin/env python3
"""Save exact detector NV12 inputs + same-frame observations, locally or over SSH.

Requires the explicit capture_stream_port bench option in the node config. SSH
forwards stdio directly to that loopback socket; no board files or persistent tunnel.
With --local, run on the board itself: loopback only, bounded raw capture, no SSH.
Local capture is first held in RAM, then saved to disk; it can be lost on power loss.
This is a diagnostic recorder, not a continuous encoded flight-video recorder.
"""
import argparse
from contextlib import contextmanager, suppress
from collections import deque
import hashlib
import json
import math
import os
import pathlib
import select
import shutil
import socket
import struct
import subprocess
import time
import uuid

LOCAL_FRAME_LIMIT=24
LOCAL_RAM_RESERVE=160*1024*1024

def read_exact(fd, count, timeout=3):
    chunks=[];remaining=count;deadline=time.monotonic()+timeout
    while remaining:
        left=deadline-time.monotonic()
        if left<=0:raise TimeoutError('capture packet timeout')
        if not select.select([fd],[],[],left)[0]:continue
        data=os.read(fd,remaining)
        if not data:raise EOFError('capture ended without complete packet/footer')
        chunks.append(data);remaining-=len(data)
    return b''.join(chunks)


def read_packet(fd):
    magic,meta_size,pixel_size=struct.unpack('!4sII',read_exact(fd,12))
    if magic!=b'GRC1' or not 0<meta_size<=128*1024 or pixel_size>2*1024*1024:
        raise ValueError('invalid capture packet header')
    meta=json.loads(read_exact(fd,meta_size))
    if not isinstance(meta,dict):raise ValueError('capture metadata is not an object')
    pixels=read_exact(fd,pixel_size)
    return meta,pixels,meta_size,pixel_size


def diagnostic_headroom(meminfo):
    # Match hosts/hailo15l/diagnostic_budget.hpp. CMA is reserved for DMA and
    # MUST NOT be counted as general Python storage on this 2 GB board.
    values={}
    for line in meminfo.splitlines():
        fields=line.split()
        if not fields or fields[0] not in ('MemAvailable:','CmaFree:'):continue
        if len(fields)!=3 or fields[2]!='kB':raise ValueError('invalid memory accounting')
        value=int(fields[1])
        if not 0<=value<=(2**64-1)//1024:raise ValueError('invalid memory accounting')
        values[fields[0]]=value*1024
    if len(values)!=2:raise RuntimeError('non-CMA headroom unavailable; local capture refused')
    return max(0,values['MemAvailable:']-values['CmaFree:'])


def memory_available_bytes():
    return diagnostic_headroom(pathlib.Path('/proc/meminfo').read_text())


def require_capture_memory(requested):
    if type(requested) is not int or not 1<=requested<=LOCAL_FRAME_LIMIT:raise ValueError('local spool limited to 1..24 samples')
    # Pixel bound + conservative JSON/copy allowance, beyond a 160 MiB non-CMA reserve.
    # This is admission control, not a guarantee against unrelated allocations.
    if memory_available_bytes()<requested*(2*1024*1024+8*128*1024+65536)+LOCAL_RAM_RESERVE:
        raise RuntimeError('insufficient RAM reserve for bounded local capture')


def spool_packets(fd,requested):
    require_capture_memory(requested)
    pending=deque()
    try:
        for index in range(requested+1):
            if memory_available_bytes()<LOCAL_RAM_RESERVE+4*1024*1024:
                raise RuntimeError('RAM reserve reached; capture incomplete')
            item=read_packet(fd)
            if index==requested and item[0].get('type')!='end':
                raise ValueError('capture exceeds requested spool bound')
            pending.append(item)
            if item[0].get('type')=='end':break
    except Exception as error:
        # Persist only the subsequently validated prefix, then report incomplete.
        pending.append(error)
    def get():
        if not pending:raise EOFError('spooled capture has no complete footer')
        item=pending.popleft()
        if isinstance(item,Exception):raise item
        return item
    return get


def source_descriptor(meta, primary_size, packet_size):
    """Validate an optional exact-exposure full-FOV image appended to the model input."""
    source=meta.get('source_image')
    if source is None:
        if packet_size!=primary_size:raise ValueError('NV12 geometry mismatch')
        return None
    w,h=source['width'],source['height'];stamp=source['isp_timestamp_ns']
    if (any(type(v) is not int or v<2 or v>8192 or v%2 for v in (w,h)) or
        source['pixel_format']!='NV12' or source['packed_stride']!=w or
        source['byte_offset']!=primary_size or source['byte_length']!=w*h*3//2 or
        packet_size!=primary_size+source['byte_length'] or packet_size>2*1024*1024):
        raise ValueError('paired source packing mismatch')
    if (type(stamp) is not int or stamp<=0 or type(meta.get('isp_timestamp_ns')) is not int or
        stamp!=meta['isp_timestamp_ns'] or abs(stamp/1e6-meta['frame']['capture_ms'])>1e-6):
        raise ValueError('paired source exposure mismatch')
    if w!=meta['output']['frame']['width'] or h!=meta['output']['frame']['height']:
        raise ValueError('paired source full-FOV geometry mismatch')
    return source


def receive(fd, output, recording_id, requested, reserve_bytes=0, spool=False):
    # Local short captures receive in bounded RAM, THEN validate and save to eMMC.
    # No unbounded queue and no eMMC writes competing with the 100 ms sender.
    # A power/process failure before saving can lose the whole capture.
    get_packet=spool_packets(fd,requested) if spool else lambda:read_packet(fd)
    return receive_packets(get_packet,output,recording_id,requested,reserve_bytes)


def receive_packets(get_packet, output, recording_id, requested, reserve_bytes=0):
    count=0;last_sequence=-1;last_capture=-1;producer=None;total=0;paired_mode=None;paired_count=0
    while True:
        meta,pixels,meta_size,pixel_size=get_packet()
        if meta['recording_id']!=recording_id:raise ValueError('recording identity mismatch')
        if meta['type']=='end':
            (output/'end.json').write_text(json.dumps(meta,indent=2)+'\n')
            if pixel_size or meta['complete'] is not True or meta['sent']!=count or count!=requested:
                raise ValueError('incomplete capture: '+json.dumps(meta))
            return dict(frames=count,pixel_bytes=total,producer=producer,complete=True,paired_frames=paired_count)
        if count>=requested or meta['type']!='frame' or meta['sample_index']!=count:
            raise ValueError('capture frame order mismatch')
        w,h=meta['input_w'],meta['input_h']
        if any(type(v) is not int or v<2 or v>8192 or v%2 for v in (w,h)):
            raise ValueError('NV12 geometry mismatch')
        if meta['pixel_format']!='NV12' or meta['packed_stride']!=w:raise ValueError('unsupported pixel packing')
        frame,result=meta['frame'],meta['output']
        sequence,capture=frame['sequence'],frame['capture_ms']
        if type(sequence) is not int or sequence<1 or type(capture) not in (int,float) or not math.isfinite(capture):
            raise ValueError('invalid capture identity/time')
        if sequence<=last_sequence or capture<=last_capture or sequence!=result['sequence'] or abs(capture-result['capture_monotonic_ms'])>1e-6:
            raise ValueError('image/frame/output correspondence mismatch')
        primary_size=w*h*3//2;source=source_descriptor(meta,primary_size,pixel_size)
        if paired_mode is not None and paired_mode!=(source is not None):raise ValueError('mixed source pairing modes')
        paired_mode=source is not None
        identity=(meta['source_id'],meta['stream_id'],meta['clock_domain'])
        if producer is not None and producer!=identity:raise ValueError('producer changed within recording')
        producer=identity;last_sequence=sequence;last_capture=capture
        # Recheck because another process may consume storage after preflight.
        # Account for added digests/JSON spacing and filesystem allocation slack.
        if reserve_bytes and shutil.disk_usage(output).free < pixel_size+2*meta_size+65536+reserve_bytes:
            raise RuntimeError('storage reserve reached; capture incomplete')
        meta['nv12_sha256']=hashlib.sha256(pixels[:primary_size]).hexdigest()
        stem=output/f'{count:06d}'
        write_start=time.monotonic()
        with stem.with_suffix('.nv12').open('xb') as file:file.write(pixels[:primary_size])
        if source is not None:
            source_pixels=pixels[primary_size:];source['sha256']=hashlib.sha256(source_pixels).hexdigest()
            with stem.with_suffix('.source.nv12').open('xb') as file:file.write(source_pixels)
            paired_count+=1
        meta['receiver_pixel_write_ms']=(time.monotonic()-write_start)*1000
        with stem.with_suffix('.json').open('x') as file:file.write(json.dumps(meta,allow_nan=False)+'\n')
        count+=1;total+=pixel_size


@contextmanager
def capture_transport(host, port, request, local=False):
    payload=(json.dumps(request)+'\n').encode()
    if local:
        # Hard-coded loopback: local mode cannot accidentally contact an FC or
        # a remote camera. No shell, forwarding process or network dependency.
        with socket.create_connection(('127.0.0.1',port),timeout=3) as connection:
            connection.sendall(payload)
            connection.setblocking(True)
            yield connection.fileno()
        return
    process=subprocess.Popen(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=3','-o','ExitOnForwardFailure=yes',
                              '-W',f'127.0.0.1:{port}',host],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        process.stdin.write(payload);process.stdin.flush()
        yield process.stdout.fileno()
    finally:
        with suppress(BrokenPipeError):process.stdin.close()
        process.stdout.close()
        try:process.wait(timeout=1)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    transport=parser.add_mutually_exclusive_group()
    transport.add_argument('--host',default='root@10.0.0.1')
    transport.add_argument('--local',action='store_true',help='on-board loopback receiver; no SSH or PC required')
    parser.add_argument('--port',type=int,default=8983)
    parser.add_argument('--frames',type=int,default=None,help='default16 locally (max24),600 over SSH; local capture requires non-CMA RAM headroom')
    parser.add_argument('--every',type=int,default=1)
    parser.add_argument('--deadline-ms',type=int,default=60000)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args()
    if args.frames is None:args.frames=16 if args.local else 600
    if not (1024<=args.port<=65535 and 1<=args.frames<=1200 and 1<=args.every<=40 and 100<=args.deadline_ms<=60000):
        parser.error('capture bounds exceeded')
    if args.local and args.frames>LOCAL_FRAME_LIMIT:parser.error('local raw capture limited to24 samples')
    args.output.mkdir(parents=True,exist_ok=False)
    reserve_bytes=(512 if args.local else 128)*1024*1024
    if shutil.disk_usage(args.output).free < args.frames*(2*1024*1024+2*128*1024+65536)+reserve_bytes:
        raise RuntimeError('insufficient destination storage for bounded worst-case capture')
    request=dict(recording_id=str(uuid.uuid4()),frames=args.frames,every=args.every,deadline_ms=args.deadline_ms)
    (args.output/'request.json').write_text(json.dumps(request,indent=2)+'\n')
    try:
        if args.local:require_capture_memory(args.frames)
        with capture_transport(args.host,args.port,request,args.local) as fd:
            summary=receive(fd,args.output,request['recording_id'],args.frames,reserve_bytes,spool=args.local)
        summary['transport']='local-loopback' if args.local else 'ssh-loopback'
        summary['ram_spooled_before_save']=args.local
        summary['storage_reserve_bytes']=reserve_bytes
        (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary))
    except Exception as error:
        (args.output/'error.json').write_text(json.dumps({'error':str(error),'complete':False})+'\n')
        raise


if __name__=='__main__':main()
