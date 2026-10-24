"""Convert a MOT17 or VisDrone-MOT sequence into garuda-track-replay input JSONL.

Ground-truth mode uses annotated boxes with their per-box visibility as
detection confidence, so occlusions become low-confidence or dropped
detections exactly where the annotators marked them. A lock command can be
emitted at a chosen frame on a chosen ground-truth identity, and a sidecar
records which ground-truth box held the lock target each frame so a scorer
can judge identity persistence and re-acquire correctness.

MOT17 (`--format mot17`, default): pedestrians only, continuous visibility
from gt.txt, frame rate from seqinfo.ini.
VisDrone-MOT (`--format visdrone`): the sequence directory is
`.../sequences/<name>` with `.../annotations/<name>.txt` beside it; rows are
frame,id,x,y,w,h,score,category,truncation,occlusion. Categories map to the
detector's COCO labels (pedestrian+people → person, car+van → car, truck,
bus, motor → motorcycle, bicycle; tricycles/others/score-0 dropped) and the
3-level occlusion flag becomes visibility 1.0 / 0.6 / 0.2. VisDrone ships no
frame-rate metadata, so `--rate` is required and sets the ms scale of every
coast/re-acquire window — an explicit replay parameter, not a measurement.
"""
import argparse
import configparser
import json
import pathlib

VISDRONE_LABELS = {1: 'person', 2: 'person', 3: 'bicycle', 4: 'car', 5: 'car',
                   6: 'truck', 9: 'bus', 10: 'motorcycle'}
VISDRONE_VISIBILITY = {0: 1.0, 1: 0.6, 2: 0.2}


def read_seqinfo(seq):
    ini = configparser.ConfigParser()
    ini.read(seq/'seqinfo.ini')
    s = ini['Sequence']
    return dict(width=int(s['imWidth']), height=int(s['imHeight']),
                rate=float(s['frameRate']), length=int(s['seqLength']))


def read_gt(seq):
    """MOT gt rows: frame,id,x,y,w,h,consider,class,visibility (1-based pixels)."""
    rows = {}
    for line in (seq/'gt'/'gt.txt').read_text().splitlines():
        f = line.split(',')
        frame, gid = int(f[0]), int(f[1])
        consider, cls, visibility = int(f[6]), int(f[7]), float(f[8])
        if consider != 1 or cls != 1:
            continue
        rows.setdefault(frame, []).append(dict(gid=gid, label='person',
            x=float(f[2]), y=float(f[3]), w=float(f[4]), h=float(f[5]),
            visibility=max(0.0, min(1.0, visibility))))
    return rows


def read_visdrone_seqinfo(seq, rate):
    from PIL import Image
    frames = sorted(seq.glob('*.jpg'))
    if not frames:
        raise ValueError('no frames in VisDrone sequence directory')
    width, height = Image.open(frames[0]).size
    return dict(width=width, height=height, rate=rate, length=len(frames))


def read_visdrone_gt(seq):
    """VisDrone rows: frame,id,x,y,w,h,score,category,truncation,occlusion."""
    rows = {}
    annotation = seq.parent.parent/'annotations'/(seq.name+'.txt')
    for line in annotation.read_text().splitlines():
        if not line.strip():
            continue
        f = [int(v) for v in line.strip().rstrip(',').split(',')]
        frame, gid, score, category, occlusion = f[0], f[1], f[6], f[7], f[9]
        label = VISDRONE_LABELS.get(category)
        if score == 0 or label is None:
            continue
        rows.setdefault(frame, []).append(dict(gid=gid, label=label,
            x=float(f[2]), y=float(f[3]), w=float(f[4]), h=float(f[5]),
            visibility=VISDRONE_VISIBILITY[occlusion]))
    return rows


def identity_appearance(gid):
    """Deterministic idealized 72-bin appearance per identity.

    A stand-in for a real appearance descriptor so the appearance-verified
    re-acquire path can be exercised on MOT data (which has none). NOT a claim
    that detectors produce perfect per-identity histograms — the live board
    carries measured, imperfect ones; this is a mechanism test only.
    """
    hist = [1e-3]*72
    hist[gid % 72] = 1.0
    hist[(gid*7+3) % 72] += 0.5
    return hist


def to_detection(box, info, min_visibility, with_appearance=False):
    if box['visibility'] < min_visibility or box['w'] <= 0 or box['h'] <= 0:
        return None
    d = dict(box=dict(x=box['x']/info['width'], y=box['y']/info['height'],
                      w=box['w']/info['width'], h=box['h']/info['height']),
             label=box['label'], confidence=box['visibility'])
    if with_appearance:
        d['appearance'] = identity_appearance(box['gid'])
    return d


def in_window(t_s, windows):
    return any(a <= t_s < b for a, b in windows)


def camera_motion(previous, current, info, exclude_gid=None, minimum=3):
    """Ground-truth camera motion proxy for one frame step.

    Median normalized shift of every annotated object present in both frames
    (the locked target excluded, so its own walk does not count as camera
    motion). Stands in for the board's camera-motion estimator, which the
    replay path otherwise lacks; a moving drone makes every remembered
    position wrong without it. Returns None when too few objects overlap.
    """
    prev = {b['gid']: b for b in previous}
    dx, dy = [], []
    for b in current:
        p = prev.get(b['gid'])
        if p is None or b['gid'] == exclude_gid:
            continue
        dx.append(((b['x']+b['w']/2)-(p['x']+p['w']/2))/info['width'])
        dy.append(((b['y']+b['h']/2)-(p['y']+p['h']/2))/info['height'])
    if len(dx) < minimum:
        return None
    dx.sort(), dy.sort()
    return dict(dx=dx[len(dx)//2], dy=dy[len(dy)//2], valid=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('sequence', type=pathlib.Path,
                   help='MOT17 sequence directory (gt/, seqinfo.ini) or VisDrone sequences/<name>')
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--format', choices=('mot17', 'visdrone'), default='mot17')
    p.add_argument('--rate', type=float, help='Replay frame rate (fps); required for --format visdrone')
    p.add_argument('--min-visibility', type=float, default=0.25,
                   help='Below this the annotated box is not "detected" at all')
    p.add_argument('--lock-gid', type=int, help='Ground-truth identity to lock via lock_point')
    p.add_argument('--lock-frame', type=int, default=15, help='Frame at which the lock command fires')
    p.add_argument('--drop', action='append', default=[],
                   help='start_s,end_s window where ALL detections vanish (repeatable)')
    p.add_argument('--drop-target', action='append', default=[],
                   help='start_s,end_s window where only the LOCKED identity vanishes while '
                        'bystanders stay detected — the follow-me occlusion/exit case (repeatable)')
    p.add_argument('--latency-ms', type=float, default=10.0)
    p.add_argument('--appearance', action='store_true',
                   help='Emit an idealized per-identity appearance descriptor (mechanism test)')
    p.add_argument('--camera-motion', choices=('none', 'gt'), default='none',
                   help='gt: per-frame median shift of the other annotated objects as the '
                        'camera-motion input (what the board estimates live)')
    a = p.parse_args()
    if a.format == 'visdrone':
        if not a.rate or a.rate <= 0:
            raise ValueError('--format visdrone needs an explicit --rate')
        info = read_visdrone_seqinfo(a.sequence, a.rate)
        gt = read_visdrone_gt(a.sequence)
    else:
        info = read_seqinfo(a.sequence)
        gt = read_gt(a.sequence)
    def parse_windows(specs):
        out = []
        for w in specs:
            start, end = (float(v) for v in w.split(','))
            if end <= start:
                raise ValueError('empty drop window')
            out.append((start, end))
        return out
    windows = parse_windows(a.drop)
    target_windows = parse_windows(a.drop_target)
    if target_windows and a.lock_gid is None:
        raise ValueError('--drop-target needs --lock-gid')
    if a.lock_gid is not None and a.lock_gid not in {b['gid'] for b in gt.get(a.lock_frame, [])}:
        raise ValueError('lock identity is not present in the lock frame')
    period_ms = 1000.0/info['rate']
    truth = []
    with a.output.open('x') as out:
        for frame in range(1, info['length']+1):
            capture_ms = frame*period_ms
            t_s = capture_ms/1000.0
            boxes = gt.get(frame, [])
            target_gone = in_window(t_s, target_windows)
            visible_boxes = [b for b in boxes if not (target_gone and b['gid'] == a.lock_gid)]
            dets = [] if in_window(t_s, windows) else \
                [d for d in (to_detection(b, info, a.min_visibility, a.appearance) for b in visible_boxes) if d]
            row = dict(sequence=frame, capture_ms=capture_ms,
                       now_ms=capture_ms+a.latency_ms, timestamp_valid=True, detections=dets)
            if a.camera_motion == 'gt':
                motion = camera_motion(gt.get(frame-1, []), boxes, info, a.lock_gid)
                if motion:
                    row['motion'] = motion
            out.write(json.dumps(row)+'\n')
            # A target-only drop is recorded as the target being absent so outages
            # are scored, while bystanders remain for wrong-identity judgement.
            target = None if target_gone else \
                next((b for b in boxes if a.lock_gid is not None and b['gid'] == a.lock_gid), None)
            truth.append(dict(sequence=frame, capture_ms=capture_ms,
                target=None if target is None else dict(
                    x=target['x']/info['width'], y=target['y']/info['height'],
                    w=target['w']/info['width'], h=target['h']/info['height'],
                    visibility=target['visibility']),
                others=[dict(x=b['x']/info['width'], y=b['y']/info['height'],
                             w=b['w']/info['width'], h=b['h']/info['height'])
                        for b in boxes if a.lock_gid is None or b['gid'] != a.lock_gid],
                dropped=in_window(t_s, windows)))
            if a.lock_gid is not None and frame == a.lock_frame and target is not None:
                out.write(json.dumps(dict(cmd='lock_point',
                    x=(target['x']+target['w']/2)/info['width']*1280,
                    y=(target['y']+target['h']/2)/info['height']*720,
                    sequence=frame, now_ms=capture_ms+a.latency_ms+1))+'\n')
    a.output.with_suffix('.truth.jsonl').write_text(
        ''.join(json.dumps(r)+'\n' for r in truth))
    print(json.dumps(dict(format=a.format, frames=info['length'], rate=info['rate'],
        width=info['width'], height=info['height'], camera_motion=a.camera_motion,
        lock_gid=a.lock_gid, drop_windows=windows, drop_target_windows=target_windows,
        gt_frames_with_target=sum(1 for r in truth if r['target']))))


if __name__ == '__main__':
    main()
