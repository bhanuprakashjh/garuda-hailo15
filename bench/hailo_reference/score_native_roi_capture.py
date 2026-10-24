"""Score a native-crop A/B capture (`native_roi_capture.py` on the follow-native-compare profile).

For every recorded frame where the node ran the native ROI and the paired-copy ROI on the
same exposure, compare the best confidence each crop gave the locked target's own box
(label-bound, IoU >= 0.4 with the tracker's box, as the node reports it). Also reports how
often each path reached the 0.5 birth floor and the 0.4 control floor, the window sizes, the
per-frame cost of the native path (source copy + DSP + inference) and the frame ages, the
native pairing statistics, and the descriptor source. Confidence is the detector's own score;
nothing here says the target was the right person.
"""
import argparse
import json
import pathlib
import statistics


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(values):
    if not values:
        return None
    values = sorted(values)
    return dict(n=len(values), mean=round(statistics.mean(values), 3), median=round(values[len(values) // 2], 3),
                p10=round(values[len(values) // 10], 3), p90=round(values[min(len(values) - 1, len(values) * 9 // 10)], 3))


def score(rows):
    pairs, native_only, ages, native_cost, paired_cost, windows_native, windows_paired = [], [], [], [], [], [], []
    verified = dict(native=0, paired=0, native_ge_04=0, paired_ge_04=0, native_wins=0, paired_wins=0, ties=0)
    heights = []
    chosen = dict(native=0, paired=0)
    for r in rows:
        roi = r.get('target_roi') or {}
        if roi.get('reason') != 'inferred' or 'best_target_confidence' not in roi:
            continue
        box = (r.get('lock') or {}).get('box')
        if box:
            heights.append(box.get('h', 0))
        ages.append(r.get('age_ms'))
        active_native = str(roi.get('source', '')).startswith('native')
        chosen['native' if active_native else 'paired'] += 1
        cost = (roi.get('source_copy_ms') or 0) + (roi.get('dsp_ms') or 0) + (roi.get('inference_ms') or 0)
        # Two recorder generations: `compare_paired` (native always active) and `compare_other_path`
        # (the gated node runs whichever path was not chosen). Pair native and paired either way.
        cmp = roi.get('compare_paired') or roi.get('compare_other_path') or {}
        other_cost = (cmp.get('source_copy_ms') or 0) + (cmp.get('dsp_ms') or 0) + (cmp.get('inference_ms') or 0)
        if active_native:
            n, p = roi['best_target_confidence'], cmp.get('best_target_confidence')
            native_only.append(n)
            native_cost.append(cost)
            if roi.get('region'):
                windows_native.append(roi['region']['w'])
            if cmp.get('region'):
                windows_paired.append(cmp['region']['w'])
                paired_cost.append(other_cost)
        else:
            n, p = cmp.get('best_target_confidence'), roi['best_target_confidence']
            paired_cost.append(cost)
            if roi.get('region'):
                windows_paired.append(roi['region']['w'])
            if cmp.get('region'):
                native_only.append(n)
                windows_native.append(cmp['region']['w'])
                native_cost.append(other_cost)
        if n is None or p is None or not cmp.get('region'):
            continue
        pairs.append((n, p))
        verified['native'] += n >= .5
        verified['paired'] += p >= .5
        verified['native_ge_04'] += n >= .4
        verified['paired_ge_04'] += p >= .4
        if n > p + 1e-6:
            verified['native_wins'] += 1
        elif p > n + 1e-6:
            verified['paired_wins'] += 1
        else:
            verified['ties'] += 1
    last = rows[-1] if rows else {}
    return dict(frames=len(rows), locked_frames=sum(1 for r in rows if (r.get('lock') or {}).get('id') is not None),
                native_roi_frames=len(native_only), compared_frames=len(pairs), path_chosen=chosen,
                native_confidence=summarize([n for n, _ in pairs]), paired_confidence=summarize([p for _, p in pairs]),
                confidence_gain=summarize([n - p for n, p in pairs]), reached_floor=verified,
                native_window_px=summarize(windows_native), paired_window_px=summarize(windows_paired),
                target_height_fraction=summarize(heights),
                native_roi_cost_ms=summarize(native_cost), paired_roi_cost_ms=summarize(paired_cost),
                frame_age_ms=summarize([a for a in ages if a is not None]),
                native_pairing=last.get('native_pairing'), descriptor_source=(last.get('person_embedding') or {}).get('source'),
                scope='detector confidence on the locked box per ROI path, same exposure; no identity truth, no aerial claim')


def bands(rows, width=10):
    """Per target-height band (pixels in the 720p frame): paired native/paired confidences."""
    table = {}
    for r in rows:
        roi = r.get('target_roi') or {}
        cmp = roi.get('compare_paired') or roi.get('compare_other_path') or {}
        if roi.get('reason') != 'inferred' or not cmp.get('region') or cmp.get('best_target_confidence') is None:
            continue
        active_native = str(roi.get('source', '')).startswith('native')
        n = roi['best_target_confidence'] if active_native else cmp['best_target_confidence']
        p = cmp['best_target_confidence'] if active_native else roi['best_target_confidence']
        h = ((r.get('lock') or {}).get('box') or {}).get('h', 0)
        b = table.setdefault(int(h) // width * width, dict(n=0, native=[], paired=[], native_chosen=0, native_wins=0,
                                                            windows=[], ages=[]))
        b['n'] += 1
        b['native'].append(n)
        b['paired'].append(p)
        b['native_chosen'] += active_native
        b['native_wins'] += n > p + 1e-6
        b['windows'].append((roi if active_native else cmp)['region']['w'])
        b['ages'].append(r.get('age_ms') or 0)
    out = {}
    for lo in sorted(table):
        b = table[lo]
        out[f'{lo}-{lo + width}px'] = dict(frames=b['n'], native_mean=round(statistics.mean(b['native']), 3),
                                          native_at_floor=sum(v >= .5 for v in b['native']),
                                          paired_mean=round(statistics.mean(b['paired']), 3),
                                          paired_at_floor=sum(v >= .5 for v in b['paired']),
                                          native_wins=b['native_wins'], native_chosen=b['native_chosen'],
                                          native_window_px_median=sorted(b['windows'])[b['n'] // 2],
                                          age_ms_median=round(statistics.median(b['ages'])))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('capture', type=pathlib.Path)
    p.add_argument('--out', type=pathlib.Path)
    p.add_argument('--bands', action='store_true', help='also print the per-target-height table')
    a = p.parse_args()
    rows = load(a.capture)
    s = score(rows)
    if a.bands:
        s['bands'] = bands(rows)
    if a.out:
        a.out.write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))
    if a.bands:
        print('\nheight band   frames  native mean / >=.5   paired mean / >=.5   native wins  native chosen  window px  age ms')
        for name, b in s['bands'].items():
            print(f"{name:12s} {b['frames']:6d}  {b['native_mean']:.3f} / {b['native_at_floor']:4d}       "
                  f"{b['paired_mean']:.3f} / {b['paired_at_floor']:4d}       {b['native_wins']:4d}         "
                  f"{b['native_chosen']:4d}        {b['native_window_px_median']:5d}     {b['age_ms_median']:4d}")


if __name__ == '__main__':
    main()
