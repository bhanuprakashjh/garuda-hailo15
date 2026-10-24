"""Bench-only Hailo-15L recorded-pixel replay; restores the desk demo on exit.

The board receives pixels, a fixed initial selection point and timing assumptions.
Ground truth stays on the host and is used ONLY for that initial point and scoring.
No oracle crops, precomputed detections, identities or embeddings reach the tracker.
This is measured compute scheduling, not a live ISP/transport latency benchmark.
"""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRAME_BYTES = 1280 * 720 * 3 // 2


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def score(rows, manifest, trial):
    from score_4k_tiles import iou
    from score_causal_timeline import timeline_score
    truth = {t['index']: t['box'] for t in manifest['targets']}
    evaluated = []
    for row in rows:
        index = row['source_index']
        if index < trial['select_frame']:
            continue
        lock = row['output']['lock']
        b = lock.get('box')
        x, y, w, h = truth[index]
        overlap = iou([b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']],
                      [x, y, x + w, y + h]) if b else 0.
        evaluated.append(dict(index=index, iou=overlap,
            valid=lock.get('control_valid', False), state=lock['state'],age_ms=row['age_ms']))
    ages = sorted(row['age_ms'] for row in rows)
    return dict(timeline=timeline_score(rows,manifest,trial),
        source_frames=trial['frames'], processed=len(rows), skipped=trial['frames']-len(rows),
        selected=any(r['selected'] for r in rows),
        roi_frames=sum(r['roi'] is not None for r in rows), global_frames=sum(r['global'] for r in rows),
        processing_plus_assumed_source_age_ms_median=ages[len(ages)//2] if ages else None,
        processing_plus_assumed_source_age_ms_p95=ages[int((len(ages)-1)*.95)] if ages else None,
        evaluated_processed_frames=len(evaluated), on_target=sum(r['iou'] >= .5 for r in evaluated),
        valid_on_target=sum(r['valid'] and r['iou'] >= .5 for r in evaluated),
        valid_off_target=sum(r['valid'] and r['iou'] < .5 for r in evaluated),
        under_200ms_valid_on_target=sum(r['valid'] and r['age_ms']<200 and r['iou']>=.5 for r in evaluated),
        under_200ms_valid_off_target=sum(r['valid'] and r['age_ms']<200 and r['iou']<.5 for r in evaluated),
        states={s: sum(r['state'] == s for r in evaluated) for s in sorted({r['state'] for r in evaluated})},
        scope='Processed-frame overlap only; skipped frames remain unscored. Not live FPS, identity-switch certification or flight validation.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('prepared', type=pathlib.Path)
    p.add_argument('--binary', required=True, type=pathlib.Path)
    p.add_argument('--profile', type=pathlib.Path, default=ROOT/'hosts/hailo15l/fresh/perception-follow.json')
    p.add_argument('--out', required=True, type=pathlib.Path)
    p.add_argument('--frames', type=int, default=200)
    p.add_argument('--select-frame', type=int, default=15)
    p.add_argument('--period-ms', type=float, default=50.)
    p.add_argument('--source-age-ms', type=float, default=50.)
    p.add_argument('--fixed-stride', type=int, default=0,
                   help='0 = timing-driven latest-frame scheduling (the measured-cadence protocol). N > 0 = labelled '
                        'A/B variant: process every Nth source frame regardless of processing time, so two trackers '
                        'or models see the identical frame set (timing is still measured and reported)')
    p.add_argument('--select-retry-any', action='store_true',
                   help='with --select-retry-ms: repeat the click after ANY refusal within the window (a person '
                        'clicking again), not only after a missing-descriptor refusal')
    p.add_argument('--select-retry-ms', type=float, default=0.,
                   help='0 = frozen protocol (one click). >0 = labelled variant: a click refused only for a missing '
                        'descriptor is repeated on later processed frames within this window while the node '
                        'describes the pointed-at person first')
    a = p.parse_args()
    manifest = json.loads((a.prepared/'manifest.json').read_text())
    source = a.prepared/'source.nv12'
    if manifest['canvas'] != [1280,720] or source.stat().st_size != manifest['frames']*FRAME_BYTES:
        raise ValueError('source geometry/length mismatch')
    if sha(source) != manifest['source_sha256']:
        raise ValueError('source checksum mismatch')
    frames = min(a.frames, manifest['frames'])
    if not 0 <= a.select_frame < frames:
        raise ValueError('invalid selection frame')
    x,y,w,h = manifest['targets'][a.select_frame]['box']
    trial = dict(frames=frames, select_frame=a.select_frame, period_ms=a.period_ms,
                 source_age_ms=a.source_age_ms, x=x+w/2, y=y+h/2, select_retry_ms=a.select_retry_ms,
                 fixed_stride=a.fixed_stride, select_retry_any=bool(a.select_retry_any))
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/'trial.json').write_text(json.dumps(trial, indent=2))
    (a.out/'profile.json').write_bytes(a.profile.read_bytes())
    ssh = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','root@10.0.0.1']
    # /tmp is RAM-backed on this board. Repeated binary staging there consumes
    # non-CMA headroom needed to restore the real camera after a campaign.
    remote = subprocess.check_output(ssh+['test -d /opt/garuda-sim && mktemp -d /opt/garuda-sim/garuda-causal.XXXXXX'], text=True).strip()
    if not remote.startswith('/opt/garuda-sim/garuda-causal.') or any(c.isspace() for c in remote):
        raise ValueError('unexpected staging path')
    subprocess.run(['scp',str(a.binary),str(a.out/'trial.json'),str(a.out/'profile.json'),
                    'root@10.0.0.1:'+remote+'/'],check=True)
    ctl = ['bash',str(ROOT/'hosts/hailo15l/fresh_tracking_ctl.sh')]
    if subprocess.run(ssh+['pgrep -f "^/opt/garuda-sim/garuda-causal-stream"'],stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError('stop the visual simulation before borrowing the NPU')
    was_running = subprocess.run(ssh+['pgrep -f "^/opt/garuda-fresh/garuda-fresh-tracking "'],stdout=subprocess.DEVNULL).returncode == 0
    original_profile = subprocess.check_output(ssh+['sha256sum /opt/garuda-fresh/current.json']).split()[0]
    metadata = dict(trial=trial, binary_sha256=sha(a.binary), profile_sha256=sha(a.profile),
        source_sha256=manifest['source_sha256'], prepared=str(a.prepared), remote=remote,
        scope='real DSP/YOLO11/OSNet plus shared native tracker/planner; CPU motion downsize differs from live ISP; ground truth excluded after initial click')
    started = time.monotonic()
    try:
        subprocess.run(ctl+['stop'], check=True, timeout=30)
        command = 'LD_LIBRARY_PATH=/opt/garuda-fresh/lib timeout 600 '+ ' '.join(map(shlex.quote,
            [remote+'/'+a.binary.name,remote+'/profile.json',remote+'/trial.json']))
        with source.open('rb') as inp, (a.out/'outputs.jsonl').open('wb') as out, (a.out/'stderr.log').open('wb') as err:
            result = subprocess.run(ssh+[command],stdin=inp,stdout=out,stderr=err,timeout=620)
        metadata['returncode'] = result.returncode
        result.check_returncode()
    finally:
        metadata['wall_s'] = time.monotonic()-started
        # The staging directory holds a copy of the binary; left behind, 381 of them filled the
        # board's eMMC (2026-09-18) and every later campaign failed at mktemp.
        subprocess.run(ssh+['rm -rf '+shlex.quote(remote)],timeout=30)
        restored = subprocess.run(ctl+['start-current'],timeout=30) if was_running else None
        metadata['restore_returncode'] = restored.returncode if restored else None
        metadata['was_running'] = was_running
        metadata['profile_unchanged'] = original_profile == subprocess.check_output(ssh+['sha256sum /opt/garuda-fresh/current.json']).split()[0]
        (a.out/'run.json').write_text(json.dumps(metadata,indent=2))
        if restored:
            restored.check_returncode()
        if not metadata['profile_unchanged']:
            raise RuntimeError('desk profile changed during replay')
    # Hailo libraries can write startup diagnostics to stdout: retain them, but
    # only explicit source-index records enter the scorer.
    rows=[]
    for line in (a.out/'outputs.jsonl').read_text().splitlines():
        try: row=json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(row,dict) and 'source_index' in row: rows.append(row)
    if not rows or any(b['source_index'] <= a['source_index'] for a,b in zip(rows,rows[1:])):
        raise ValueError('missing or reordered replay output')
    report=score(rows,manifest,trial)
    (a.out/'score.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
