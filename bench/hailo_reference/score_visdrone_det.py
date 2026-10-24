"""Score VisDrone-DET replay results: single-tile (full view only) vs five-tile
(full + four corners, filtered and aggregated exactly like the node) recall by
object size, per class group, at two confidence floors, plus false positives
per image.

Node behaviour mirrored on the raw probe output before any scoring:
  * corner-tile boxes touching an interior tile edge within `cut_margin` are
    dropped in unpadded content coordinates;
  * corner-tile boxes larger than `corner_max_area` of the frame are dropped;
  * cross-region IoU aggregation, with full bodies preferred over contained
    crop fragments. --legacy-filters reproduces the pre-fix archived policy.

Ground truth is scaled to the canvas; size buckets are canvas-pixel heights
(what the detector sees at the node's 1280x720 tile source). Matching is
greedy, highest confidence first, IoU >= 0.5, within a class GROUP (person;
car/van/truck/bus; bicycle; motorcycle) so a van called "truck" still counts.
Detections whose centre falls in a VisDrone ignored region or on an unscored
category (tricycles, others) are discarded before false-positive counting.
Not mAP, not tracking: a size-recall / FP comparison only.
"""
import argparse
import json
import pathlib

from score_4k_tiles import iou, map_box

# VisDrone category -> scoring group (None = ignore region for FP purposes)
VISDRONE_GROUP = {1: 'person', 2: 'person', 3: 'bicycle', 4: 'vehicle', 5: 'vehicle',
                  6: 'vehicle', 9: 'vehicle', 10: 'motorcycle'}
LABEL_GROUP = {'person': 'person', 'bicycle': 'bicycle', 'car': 'vehicle', 'truck': 'vehicle',
               'bus': 'vehicle', 'motorcycle': 'motorcycle'}
BUCKETS = [('<16px', 0, 16), ('16-32px', 16, 32), ('32-64px', 32, 64), ('>=64px', 64, float('inf'))]
NODE = dict(cut_margin=0.08, corner_max_area=0.05, iou=0.3, containment=0.7)


def bucket(h):
    return next(name for name, lo, hi in BUCKETS if lo <= h < hi)


def contain(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    return ix * iy / smaller if smaller > 0 else 0


def cuts_object(r, d, margin, legacy=False):
    """SearchRegion::cuts_object on a network-space box (x1,y1,x2,y2 in 0..1)."""
    if r['full_frame']:
        return False
    if not legacy:
        nw,nh=r.get('network_w',640),r.get('network_h',640)   # the HEF's input; 640 unless the preparation says otherwise
        scale=min(nw/r['w'],nh/r['h'])
        cw,ch=r['w']*scale,r['h']*scale
        px,py=(nw-cw)/2,(nh-ch)/2
        d=dict(x1=(d['x1']*nw-px)/cw,x2=(d['x2']*nw-px)/cw,
               y1=(d['y1']*nh-py)/ch,y2=(d['y2']*nh-py)/ch)
    return ((r['x'] > 0 and d['x1'] <= margin) or (r['y'] > 0 and d['y1'] <= margin) or
            (r['x'] + r['w'] < r['source_w'] and d['x2'] >= 1 - margin) or
            (r['y'] + r['h'] < r['source_h'] and d['y2'] >= 1 - margin))


def aggregate(dets, iou_thr=NODE['iou'], contain_thr=NODE['containment'], legacy=False):
    kept = []
    def area(d):return (d['box'][2]-d['box'][0])*(d['box'][3]-d['box'][1])
    def fragment(big,small):
        return (big.get('region_full_frame',False) and not small.get('region_full_frame',False)
                and small.get('region_id',-1)>=0 and big['label']==small['label']
                and area(big)>2*area(small) and contain(big['box'],small['box'])>contain_thr)
    for d in sorted(dets, key=lambda d: -d['score']):
        if not legacy:
            if any(fragment(k,d) for k in kept):continue
            kept=[k for k in kept if not fragment(d,k)]
        if not any(k['label'] == d['label'] and
                   (legacy or k.get('region_id',-1)<0 or k.get('region_id')!=d.get('region_id')) and
                   (iou(k['box'],d['box'])>iou_thr or (legacy and contain(k['box'],d['box'])>contain_thr)) for k in kept):
            kept.append(d)
    return kept


def read_predictions(results):
    """letterbox.jsonl, or its gzipped form once an evidence directory is archived."""
    plain, packed = results / 'letterbox.jsonl', results / 'letterbox.jsonl.gz'
    if plain.exists():
        text = plain.read_text()
    else:
        import gzip
        text = gzip.decompress(packed.read_bytes()).decode()
    return [json.loads(s) for s in text.splitlines() if s.strip()]


def load_results(results, node=NODE):
    rs = json.loads((results / 'regions.json').read_text())
    ps = read_predictions(results)
    if len(rs) != len(ps):
        raise ValueError('missing results')
    per_image, stats = {}, dict(cut=0, corner_dropped_large=0, unscored_label=0, kept=0)
    for index, (r, pred) in enumerate(zip(rs, ps)):
        if pred['frame'] != index or pred['preprocessing'] != 'letterbox':
            raise ValueError('prediction order/mode mismatch')
        entry = per_image.setdefault(r['image_index'], {'full': [], 'corners': [], 'roi': []})
        frame_area = r['source_w'] * r['source_h']
        oracle = r.get('method') == 'oracle_roi'
        if oracle and r['full_frame']:
            continue   # crop did not fit: no ROI evidence for this frame
        for d in pred['detections']:
            if d['label'] not in LABEL_GROUP:
                stats['unscored_label'] += 1
                continue
            if oracle:
                # RoiAssist::merge applies its own edge and duplicate rules at merge time.
                box = map_box(r, d)
                if box is not None:
                    entry['roi'].append(dict(label=d['label'], score=d['score'], box=box))
                continue
            if cuts_object(r, d, node['cut_margin'],node.get('legacy',False)):
                stats['cut'] += 1
                continue
            box = map_box(r, d)
            if box is None:
                continue
            if not r['full_frame'] and (box[2]-box[0])*(box[3]-box[1]) > node['corner_max_area'] * frame_area:
                stats['corner_dropped_large'] += 1
                continue
            stats['kept'] += 1
            (entry['full'] if r['full_frame'] else entry['corners']).append(
                dict(label=d['label'], score=d['score'], box=box,region_id=index,region_full_frame=r['full_frame']))
    return per_image, stats


def canvas_truth(img):
    """Scaled ground truth: (scored objects with group + canvas height, ignore boxes)."""
    s, ox, oy = img['scale'], img['offset_x'], img['offset_y']
    gts, ignored = [], []
    for g in img['gt']:
        box = [g['x']*s+ox, g['y']*s+oy, (g['x']+g['w'])*s+ox, (g['y']+g['h'])*s+oy]
        group = VISDRONE_GROUP.get(g['category'])
        if group is None or g['score'] == 0:
            ignored.append(box)
        else:
            gts.append(dict(group=group, box=box, h=g['h']*s))
    return gts, ignored


def score_image(dets, gts, ignored, floor):
    """Greedy IoU>=0.5 within group; returns (matched gt indices, false positives).

    Each false positive is returned with its label, canvas-height bucket and
    whether it still overlaps SOME ground-truth box at IoU>=0.3 (a
    localisation/duplicate near-miss rather than a hallucination).
    """
    def in_ignore(d):
        cx, cy = (d['box'][0]+d['box'][2])/2, (d['box'][1]+d['box'][3])/2
        return any(ig[0] <= cx <= ig[2] and ig[1] <= cy <= ig[3] for ig in ignored)
    matched, fps = set(), []
    for d in sorted((d for d in dets if d['score'] >= floor), key=lambda d: -d['score']):
        best, best_iou = None, 0.5
        for gi, g in enumerate(gts):
            if gi in matched or g['group'] != LABEL_GROUP[d['label']]:
                continue
            v = iou(d['box'], g['box'])
            if v >= best_iou:
                best, best_iou = gi, v
        if best is not None:
            matched.add(best)
        elif not in_ignore(d):
            fps.append(dict(label=d['label'], bucket=bucket(d['box'][3]-d['box'][1]),
                            near_miss=any(iou(d['box'], g['box']) >= 0.3 for g in gts)))
    return matched, fps


def evaluate(per_image, manifest, floors=(0.15, 0.5), legacy=False, size_space='canvas'):
    if size_space not in ('canvas','original'):raise ValueError('unknown size space')
    out = {}
    truth = {img['index']: canvas_truth(img) for img in manifest['images']}
    if size_space=='original':
        for img in manifest['images']:
            for g in truth[img['index']][0]:g['h']/=img['scale']
    for tiling in ('single', 'five'):
        for floor in floors:
            tally, fps = {}, []
            for img in manifest['images']:
                entry = per_image.get(img['index'], {'full': [], 'corners': []})
                dets = entry['full'] if tiling == 'single' else aggregate(entry['full'] + entry['corners'],legacy=legacy)
                gts, ignored = truth[img['index']]
                matched, image_fps = score_image(dets, gts, ignored, floor)
                fps += image_fps
                for gi, g in enumerate(gts):
                    for gk in (g['group'], 'all'):
                        for bk in (bucket(g['h']), 'all'):
                            t = tally.setdefault((gk, bk), [0, 0])
                            t[1] += 1
                            t[0] += gi in matched
            n = len(manifest['images'])
            variant='grid' if tiling=='five' and manifest.get('native_pixels') else tiling
            out[f'{variant}@{floor}'] = dict(
                fp_per_image=round(len(fps)/max(1, n), 3), images=n,
                fp_breakdown=dict(
                    total=len(fps),
                    by_label={k: sum(f['label'] == k for f in fps) for k in sorted(LABEL_GROUP)},
                    by_height={b: sum(f['bucket'] == b for f in fps) for b, _, _ in BUCKETS},
                    near_miss_iou_0_3=sum(f['near_miss'] for f in fps)),
                recall={f'{g}/{b}': dict(matched=m, total=t, recall=round(m/t, 4) if t else None)
                        for (g, b), (m, t) in sorted(tally.items())})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('prepared', type=pathlib.Path)
    p.add_argument('results', type=pathlib.Path, nargs='+', help='one results dir per HEF')
    p.add_argument('--out', type=pathlib.Path, required=True)
    p.add_argument('--legacy-filters',action='store_true',help='reproduce archived pre-fix geometry/NMS')
    p.add_argument('--size-space',choices=['canvas','original'],default='canvas',help='use original pixels for paired geometry comparison')
    a = p.parse_args()
    manifest = json.loads((a.prepared / 'manifest.json').read_text())
    report = dict(scope='VisDrone2019-DET-val; recall at IoU>=0.5 by declared height coordinate '
                        'bucket within class group, per HEF, wide vs tiled with node filters '
                        'mirrored; FP/image outside ignore regions. Not mAP, not tracking, not live FPS.',
                  canvas=manifest['canvas'], target_size_space=a.size_space,
                  false_positive_size_space='canvas',images=len(manifest['images']),
                  source_sizes=manifest['source_sizes'], node_filters=dict(NODE,legacy=a.legacy_filters), runs={})
    for results in a.results:
        run = json.loads((results / 'run.json').read_text())
        per_image, stats = load_results(results,dict(NODE,legacy=a.legacy_filters))
        report['runs'][results.name] = dict(hef_sha256=run['hef_sha256'], filter_stats=stats,
                                            metrics=evaluate(per_image, manifest,legacy=a.legacy_filters,size_space=a.size_space))
    a.out.write_text(json.dumps(report, indent=2))
    for name, run in report['runs'].items():
        print(f'== {name} ({run["hef_sha256"][:8]}) filters {run["filter_stats"]} ==')
        for key, m in run['metrics'].items():
            rec, fb = m['recall'], m['fp_breakdown']
            for grp in ('person', 'vehicle', 'all'):
                cells = ' '.join(f"{b}:{rec.get(f'{grp}/{b}', {}).get('recall')}" for b, _, _ in BUCKETS)
                print(f"  {key:12s} {grp:8s} {cells} | all {rec.get(f'{grp}/all', {}).get('recall')}"
                      + (f" | FP/img {m['fp_per_image']} (near-miss {fb['near_miss_iou_0_3']}/{fb['total']})"
                         if grp == 'all' else ''))


if __name__ == '__main__':
    main()
