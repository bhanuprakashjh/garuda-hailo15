#!/usr/bin/env python3
"""Offline integrity gate for exact-source captures. Does not certify tracking accuracy."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from fresh_stream_capture import source_descriptor


def qualify(root):
    root = Path(root)
    request = json.loads((root/'request.json').read_text())
    summary = json.loads((root/'summary.json').read_text())
    end = json.loads((root/'end.json').read_text())
    count = request['frames']
    if type(count) is not int or not 1 <= count <= 1200:
        raise ValueError('invalid requested count')
    if ((root/'error.json').exists() or summary.get('complete') is not True or
        end.get('complete') is not True or end.get('recording_id') != request['recording_id'] or
        end.get('sent') != count or summary.get('frames') != count or summary.get('paired_frames') != count):
        raise ValueError('incomplete or unpaired recording')
    if len(list(root.glob('[0-9][0-9][0-9][0-9][0-9][0-9].json'))) != count:
        raise ValueError('frame inventory mismatch')
    previous_sequence = previous_capture = -1
    first_capture = None
    intervals = []
    unrecorded_sequence_ids = pixel_bytes = 0
    producer = None
    for index in range(count):
        stem = root/f'{index:06d}'
        meta = json.loads(stem.with_suffix('.json').read_text())
        frame, output = meta['frame'], meta['output']
        seq, capture = frame['sequence'], frame['capture_ms']
        if (meta['recording_id'] != request['recording_id'] or meta['sample_index'] != index or
            type(seq) is not int or seq <= previous_sequence or
            type(capture) not in (int,float) or not math.isfinite(capture) or capture <= previous_capture or
            output['sequence'] != seq or output['capture_monotonic_ms'] != capture):
            raise ValueError('frame correspondence/order mismatch')
        identity = [meta[k] for k in ('source_id','stream_id','clock_domain')]
        if not all(isinstance(v,str) and v for v in identity) or (producer and producer != identity):
            raise ValueError('producer changed')
        producer = identity
        w,h = meta['input_w'],meta['input_h']
        if any(type(v) is not int or v < 2 or v > 8192 or v % 2 for v in (w,h)):
            raise ValueError('invalid image geometry')
        if meta['pixel_format'] != 'NV12' or meta['packed_stride'] != w:
            raise ValueError('invalid image packing')
        primary = stem.with_suffix('.nv12').read_bytes()
        source = stem.with_suffix('.source.nv12').read_bytes()
        descriptor = source_descriptor(meta, len(primary), len(primary)+len(source))
        if (not descriptor or len(primary) != w*h*3//2 or
            hashlib.sha256(primary).hexdigest() != meta['nv12_sha256'] or
            hashlib.sha256(source).hexdigest() != descriptor['sha256']):
            raise ValueError('image bytes/hash mismatch')
        pixel_bytes += len(primary)+len(source)
        if first_capture is None:
            first_capture = capture
        else:
            intervals.append(capture-previous_capture)
            unrecorded_sequence_ids += seq-previous_sequence-1
        previous_sequence, previous_capture = seq,capture
    if producer != summary.get('producer'):
        raise ValueError('summary producer mismatch')
    return dict(integrity_pass=True, frames=count, producer=producer,
                source_elapsed_ms=previous_capture-first_capture,
                capture_interval_ms_median=statistics.median(intervals) if intervals else None,
                capture_interval_ms_max=max(intervals) if intervals else None,
                unrecorded_tracker_sequence_ids=unrecorded_sequence_ids,
                pixel_bytes=pixel_bytes,
                sampling_scope='processed samples; sequence gaps are NOT a measured sensor-drop count',
                tracking_accuracy_qualified=False,
                remaining='held-out labels, fixed selection protocol, baseline/candidate scoring')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    print(json.dumps(qualify(parser.parse_args().directory), indent=2))
