"""Offline all-release-slot score, including compute skips and stale publication.

This replays a last-published box at declared source-frame instants. It is NOT
the ROS/controller, a live latency measurement, or an identity certification.
Truth never enters inference. SOT labels only one target; off-target overlap
cannot distinguish another identity from localisation error.
"""
import collections
import math
from score_4k_tiles import iou


def timeline_score(rows, manifest, trial):
    frames, start = trial['frames'], trial['select_frame']
    period = trial['period_ms']
    if not 0 <= start < frames or not math.isfinite(period) or period <= 0:
        raise ValueError('invalid timeline')
    truth = {t['index']: t['box'] for t in manifest['targets']}
    if any(i not in truth for i in range(frames)):
        raise ValueError('missing source ground truth')
    publications = []
    previous = -1
    for row in rows:
        index, age = row['source_index'], row['age_ms']
        if type(index) is not int or not previous < index < frames or not math.isfinite(age) or age < 0:
            raise ValueError('invalid/reordered source index or age')
        ready = index * period + age
        if publications and ready < publications[-1][0]:
            raise ValueError('publication time regressed')
        publications.append((ready, row))
        previous = index
    counts = collections.Counter()
    durations = collections.Counter()
    by_height = {}
    cursor, current, longest, gap = 0, None, 0, 0
    def verdict(index, now, current):
        x,y,w,h = truth[index]
        if w <= 0 or h <= 0:return 'unscorable_truth'
        if current is None:return 'no_publication'
        lock=current['output']['lock'];box=lock.get('box')
        if now-current['source_index']*period >= 200:return 'expired'
        if not lock.get('control_valid') or box is None:return 'not_control_valid'
        overlap=iou([box['x'],box['y'],box['x']+box['w'],box['y']+box['h']],[x,y,x+w,y+h])
        return 'eligible_on_target' if overlap>=.5 else 'eligible_off_target'

    for index in range(start, frames):
        now = index * period
        while cursor < len(publications) and publications[cursor][0] <= now:
            current = publications[cursor][1]
            cursor += 1
        reason=verdict(index,now,current)
        h=truth[index][3]
        counts[reason] += 1
        height = '<32' if h < 32 else '32-64' if h < 64 else '64-128' if h < 128 else '>=128'
        by_height.setdefault(height, collections.Counter())[reason] += 1
        gap = 0 if reason == 'eligible_on_target' else gap + 1
        longest = max(longest, gap)
        # Integrate exact publication/expiry boundaries, so a 175 ms result does
        # not disappear merely because release-slot sampling next occurs at 200.
        end=(index+1)*period
        boundaries={now,end}
        for ready,row in publications:
            for edge in (ready,row['source_index']*period+200):
                if now < edge < end:boundaries.add(edge)
        edges=sorted(boundaries)
        for left,right in zip(edges,edges[1:]):
            while cursor<len(publications) and publications[cursor][0]<=left:
                current=publications[cursor][1];cursor+=1
            durations[verdict(index,left,current)]+=right-left
    n = frames-start
    return dict(source_slots=n, counts=dict(counts),
                eligible_on_target_fraction=counts['eligible_on_target']/n,
                longest_without_on_target_ms=longest*period,
                time_weighted=dict(duration_ms=n*period,durations_ms=dict(durations),
                    eligible_on_target_fraction=durations['eligible_on_target']/(n*period),
                    truth_assumption='piecewise constant between labelled source-frame instants; no interpolated truth'),
                by_target_canvas_height_px={k:dict(v) for k,v in by_height.items()},
                scope='Offline last-published-box overlap at all source releases; 200 ms expiry; no real commands',
                assumptions=dict(period_ms=period,initial_source_age_ms=trial['source_age_ms']),
                limits=['Skipped source frames remain in denominator',
                        'SOT off-target is not a wrong-person identity count',
                        'No ROS/SSH/ISP delay included; measured compute plus declared initial age'])
