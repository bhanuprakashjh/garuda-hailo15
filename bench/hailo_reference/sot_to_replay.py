"""Turn a VisDrone-SOT probe run into garuda-track-replay inputs.

Real detector output (the probe's per-region detections) becomes the
tracker's detection stream, in two flavours from the same run: `single`
(full-view region only) and `five` (all five tiles with the node's filters
and aggregation, via `score_visdrone_det.load_results`/`aggregate`). A
`lock_point` fires on the annotated target at the first frame where the
detector has a same-place box, and a truth sidecar carries the annotated
target per frame (no bystanders: SOT annotates one object).

Appearance: each detection gets the 72-bin descriptor `describe()` builds on
the board, recomputed here from the prepared canvas NV12 with the same
binning and central-region sampling — real pixels, not the idealized MOT
descriptor, but sampled from the 1280x720 canvas rather than the node's
AI-stream frame. Camera motion: none (SOT has no other annotated objects
to derive it from); the live board estimates it from pixels.
"""
import argparse
import json
import pathlib

import numpy as np

from score_visdrone_det import LABEL_GROUP, aggregate, cuts_object, load_results, iou

CANVAS_W, CANVAS_H = 1280, 720
FRAME_BYTES = CANVAS_W * CANVAS_H * 3 // 2


def to_network(region, box):
    """Inverse of score_4k_tiles.map_box: canvas x1,y1,x2,y2 -> letterboxed 640-square coordinates in 0..1."""
    scale = min(640 / region['w'], 640 / region['h'])
    px, py = (640 - region['w'] * scale) / 2, (640 - region['h'] * scale) / 2
    return dict(x1=(px + (box[0] - region['x']) * scale) / 640, y1=(py + (box[1] - region['y']) * scale) / 640,
                x2=(px + (box[2] - region['x']) * scale) / 640, y2=(py + (box[3] - region['y']) * scale) / 640)


def roi_merge(full_dets, roi_dets, label, region, cut_margin=.015):
    """RoiAssist::merge: only the locked label, confidence >= .15, not cut by an
    interior crop edge (network space, margin .015); a crop box overlapping a
    full-view box of the same label at IoU >= .4 replaces it when more
    confident, otherwise it is dropped; others are added."""
    kept = list(full_dets)
    if region['full_frame']:
        return kept
    for d in roi_dets:
        if d['label'] != label or d['score'] < .15:
            continue
        if cuts_object(region, to_network(region, d['box']), cut_margin):
            continue
        overlapping = next((i for i, k in enumerate(kept[:len(full_dets)])
                            if k['label'] == d['label'] and iou(k['box'], d['box']) >= .4), None)
        if overlapping is None:
            kept.append(d)
        elif d['score'] > kept[overlapping]['score']:
            kept[overlapping] = d
    return kept


def index_embeddings(rows):
    """(frame, rounded canvas box) -> {model, values} from embed_visdrone_sot.py rows."""
    return {(r['frame'], tuple(round(v, 2) for v in r['box'])): dict(model=r['model'], values=r['values']) for r in rows}


def attach_embeddings(dets, frame, index):
    out = []
    for d in dets:
        e = index.get((frame, tuple(round(v, 2) for v in d['box'])))
        out.append(dict(d, embedding=e) if e else d)
    return out


def target_label(per_image, targets, iou_min=0.5):
    """The detector's majority label on the annotated box across the sequence (SOT ships
    no class): the ROI merge and the identity path key on it. Falls back to person."""
    votes = {}
    for t in targets:
        entry = per_image.get(t['index'])
        if not entry:
            continue
        x, y, w, h = t['box']
        for d in entry['full']:
            if iou(d['box'], [x, y, x+w, y+h]) >= iou_min:
                votes[d['label']] = votes.get(d['label'], 0) + d['score']
    return max(votes, key=votes.get) if votes else 'person'


def roi_regions(results):
    """image_index -> the oracle ROI region of that frame (regions.json)."""
    out = {}
    for r in json.loads((results / 'regions.json').read_text()):
        if r.get('method') == 'oracle_roi':
            out[r['image_index']] = r
    return out


def describe(y_plane, uv_plane, box):
    """Port of garuda::fresh::describe on packed NV12 (box normalized)."""
    x, y, w, h = box
    if not all(np.isfinite([x, y, w, h])) or w <= 0 or h <= 0:
        return None
    x0, x1 = int(min(max(x+w*.2, 0), 1)*CANVAS_W), int(min(max(x+w*.8, 0), 1)*CANVAS_W)
    y0, y1 = int(min(max(y+h*.15, 0), 1)*CANVAS_H), int(min(max(y+h*.85, 0), 1)*CANVAS_H)
    if x1-x0 < 8 or y1-y0 < 8:
        return None
    step = max(1, max(x1-x0, y1-y0)//24)
    hist = np.zeros(72)
    count = 0
    for yy in range(y0, y1, step):
        for xx in range(x0, x1, step):
            u, v = uv_plane[yy//2, xx & ~1], uv_plane[yy//2, (xx & ~1)+1]
            hist[(int(u)//32)*8 + int(v)//32] += .8
            hist[64 + int(y_plane[yy, xx])//32] += .2
            count += 1
    return (hist/count).tolist()


def frame_planes(source, index):
    source.seek(index*FRAME_BYTES)
    data = np.frombuffer(source.read(FRAME_BYTES), dtype=np.uint8)
    if data.size != FRAME_BYTES:
        raise ValueError('short frame')
    return data[:CANVAS_W*CANVAS_H].reshape(CANVAS_H, CANVAS_W), data[CANVAS_W*CANVAS_H:].reshape(CANVAS_H//2, CANVAS_W)


def target_hit(dets, gt_xywh, threshold):
    """Best confidence among detections (x1,y1,x2,y2 canvas px) on the annotated
    target (x,y,w,h canvas px) at IoU >= threshold; None when nothing overlaps."""
    x, y, w, h = gt_xywh
    scores = [d['score'] for d in dets if iou(d['box'], [x, y, x+w, y+h]) >= threshold]
    return max(scores) if scores else None


def confidence_summary(values, birth=0.5):
    hits = sorted(v for v in values if v is not None)
    return dict(frames=len(values), detected=len(hits),
                conf_median=round(hits[len(hits)//2], 3) if hits else None,
                conf_max=round(hits[-1], 3) if hits else None,
                frames_at_or_above_birth=sum(v >= birth for v in hits))


def to_detection(d, appearance):
    x1, y1, x2, y2 = d['box']
    box = dict(x=x1/CANVAS_W, y=y1/CANVAS_H, w=(x2-x1)/CANVAS_W, h=(y2-y1)/CANVAS_H)
    det = dict(box=box, label=d['label'], confidence=d['score'])
    if appearance is not None:
        det['appearance'] = appearance
    if d.get('embedding'):
        det['embedding'] = d['embedding']
    return det


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('prepared', type=pathlib.Path)
    p.add_argument('results', type=pathlib.Path, help='run_visdrone_det.py output dir for this sequence')
    p.add_argument('output', type=pathlib.Path, help='output prefix; writes <prefix>-single.jsonl, -five.jsonl, .truth.jsonl')
    p.add_argument('--rate', type=float, required=True, help='assumed frame rate (VisDrone ships none)')
    p.add_argument('--latency-ms', type=float, default=10.0)
    p.add_argument('--no-appearance', action='store_true')
    p.add_argument('--embeddings', type=pathlib.Path,
                   help='embed_visdrone_sot.py output: attach real OSNet descriptors to matching detections')
    p.add_argument('--lock-iou', type=float, default=0.5, help='detector box IoU with the target needed to fire the lock')
    p.add_argument('--lock-after', type=int, default=15,
                   help='earliest frame (1-based) for the lock: tracks need min_hits and confirm_ms first')
    p.add_argument('--lock-conf', type=float, default=0.5,
                   help='detector confidence on the target the click waits for (tracker birth_confidence)')
    p.add_argument('--lock-streak', type=int, default=5,
                   help='consecutive such frames before the click (a confirmed track needs min_hits + confirm_ms)')
    a = p.parse_args()
    manifest = json.loads((a.prepared / 'manifest.json').read_text())
    per_image, stats = load_results(a.results)
    regions = roi_regions(a.results)
    label = target_label(per_image, manifest['targets'])
    embeddings = index_embeddings([json.loads(l) for l in a.embeddings.read_text().splitlines() if l.strip()]) \
        if a.embeddings else None
    names = ['single', 'five'] + (['roi'] if regions else [])
    period_ms = 1000.0/a.rate
    primary_window = int(round(0.4 * a.rate))   # RoiAssist: ROI only within 400 ms of full-view evidence
    truth, summary = [], dict(lock_frame={})
    on_target = {n: [] for n in names}
    streak = {n: 0 for n in names}
    outputs = {n: (a.output.parent / (a.output.name + f'-{n}.jsonl')).open('x') for n in names}
    last_primary = None
    with (a.prepared / 'source.nv12').open('rb') as source:
        for t in manifest['targets']:
            index = t['index']
            capture_ms = (index+1)*period_ms
            gt = t['box']
            gt_norm = dict(x=gt[0]/CANVAS_W, y=gt[1]/CANVAS_H, w=gt[2]/CANVAS_W, h=gt[3]/CANVAS_H)
            entry = per_image.get(index, {'full': [], 'corners': [], 'roi': []})
            flavours = dict(single=entry['full'], five=aggregate(entry['full'] + entry['corners']))
            if regions:
                if target_hit([d for d in entry['full'] if d['label'] == label], gt, .3) is not None:
                    last_primary = index
                recent = last_primary is not None and index - last_primary <= primary_window
                region = regions.get(index)
                flavours['roi'] = roi_merge(entry['full'], entry['roi'], label, region) \
                    if recent and region else list(entry['full'])
            planes = None if a.no_appearance else frame_planes(source, index)
            for flavour, dets in flavours.items():
                if embeddings is not None:
                    dets = attach_embeddings(dets, index, embeddings)
                rows = []
                for d in dets:
                    if d['label'] not in LABEL_GROUP:
                        continue
                    app = None if planes is None else describe(planes[0], planes[1], (
                        d['box'][0]/CANVAS_W, d['box'][1]/CANVAS_H,
                        (d['box'][2]-d['box'][0])/CANVAS_W, (d['box'][3]-d['box'][1])/CANVAS_H))
                    rows.append(to_detection(d, app))
                hit = target_hit(dets, gt, a.lock_iou)
                on_target[flavour].append(hit)
                streak[flavour] = streak[flavour]+1 if hit is not None and hit >= a.lock_conf else 0
                outputs[flavour].write(json.dumps(dict(sequence=index+1, capture_ms=capture_ms,
                    now_ms=capture_ms+a.latency_ms, timestamp_valid=True, detections=rows))+'\n')
                if streak[flavour] >= a.lock_streak and flavour not in summary['lock_frame'] and index+1 >= a.lock_after:
                    summary['lock_frame'][flavour] = index+1
                    outputs[flavour].write(json.dumps(dict(cmd='lock_point',
                        x=gt[0]+gt[2]/2, y=gt[1]+gt[3]/2, sequence=index+1,
                        now_ms=capture_ms+a.latency_ms+1))+'\n')
            truth.append(dict(sequence=index+1, capture_ms=capture_ms,
                              target=dict(gt_norm, visibility=1.0), others=[], dropped=False))
    for f in outputs.values():
        f.close()
    (a.output.parent / (a.output.name + '.truth.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in truth))
    summary.update(frames=len(truth), rate=a.rate, filter_stats=stats, appearance=not a.no_appearance, target_label=label,
                   embeddings=str(a.embeddings) if a.embeddings else None, lock_after=a.lock_after,
                   detector_on_target={flavour: confidence_summary(values) for flavour, values in on_target.items()})
    (a.output.parent / (a.output.name + '.summary.json')).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
