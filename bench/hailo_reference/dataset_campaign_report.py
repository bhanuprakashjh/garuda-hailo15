"""Re-score retained measurements and archive metadata, never dataset pixels."""
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from run_causal_replay import sha
from score_causal_timeline import timeline_score
from score_visdrone_det import evaluate, load_results, read_predictions


def campaign(directory):
    original=json.loads((directory/'summary.json').read_text())
    results=[]
    for item in original['results']:
        run_dir=directory/(item['sequence']+'-'+item['mode'])
        run=json.loads((run_dir/'run.json').read_text())
        manifest=json.loads((Path(run['prepared'])/'manifest.json').read_text())
        if manifest['source_sha256']!=run['source_sha256']:
            raise ValueError('source manifest changed')
        rows=[]
        for line in (run_dir/'outputs.jsonl').read_text().splitlines():
            try:row=json.loads(line)
            except ValueError:continue
            if isinstance(row,dict) and 'source_index' in row:rows.append(row)
        result=dict(item,timeline_rescored=timeline_score(rows,manifest,run['trial']),
                    output_sha256=sha(run_dir/'outputs.jsonl'),
                    source_manifest_sha256=sha(Path(run['prepared'])/'manifest.json'),
                    selection_errors=dict(collections.Counter(r.get('selection_error','') for r in rows)))
        results.append(result)
    return dict(scope='Frozen fullview regression, not an untouched test set; measured compute, assumed source timing',
                all_cases_retained=True,selected_sequences=sum(r['score']['selected'] for r in results),
                cases=len(results),results=results,robust_following_qualified=False)


def detector_pair(reduced,native):
    runs=[json.loads((d/'run.json').read_text()) for d in (reduced,native)]
    a,b=[r['preparation'] for r in runs]
    if [(i['file'],i['image_sha256']) for i in a['images']]!=[(i['file'],i['image_sha256']) for i in b['images']]:
        raise ValueError('paired images differ')
    if any(runs[0][k]!=runs[1][k] for k in ('hef_sha256','probe_sha256')):
        raise ValueError('paired model/probe differ')
    result={}
    for name,directory,run in zip(('reduced_720','original_pixel_grid'),(reduced,native),runs):
        per_image,filters=load_results(directory)
        waits=collections.defaultdict(float)
        regions=json.loads((directory/'regions.json').read_text())
        for region,pred in zip(regions,read_predictions(directory)):
            waits[region['image_index']]+=pred['infer_wait_ms']
        result[name]=dict(canvas=run['preparation']['canvas'],regions_per_image=len(regions)/len(waits),
            metrics=evaluate(per_image,run['preparation'],size_space='original'),filter_stats=filters,
            all_region_inference_wait_sum_ms_median=statistics.median(waits.values()),
            prediction_sha256=sha(directory/'letterbox.jsonl'))
    return dict(scope='Paired 64-image regression subset; real Hailo DSP/HEF; not live ISP or tracking',
                images=len(a['images']),model_sha256=runs[0]['hef_sha256'],probe_sha256=runs[0]['probe_sha256'],
                target_size_buckets='original image pixel height (same ground truth in both conditions)',
                results=result,limits=['Grid has nine passes versus five, not equal compute budget',
                    'Native condition preserves original pixels in a padded 1920x1080 canvas, not 4K capture',
                    'FP pixel-height buckets remain canvas-based; compare overall FP/image',
                    'Inference-wait sum excludes DSP crop/resize, transfer, tracking and camera exposure',
                    'Validation data already informed tuning; no held-out generalization claim'])


def archive(directory,destination):
    destination.mkdir(parents=True,exist_ok=False)
    manifest={}
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.suffix not in ('.json','.jsonl','.log','.txt'):continue
        relative=path.relative_to(directory)
        raw=path.read_bytes()
        packed=path.suffix in ('.jsonl','.log')
        target=destination/(str(relative)+'.gz' if packed else relative)
        target.parent.mkdir(parents=True,exist_ok=True)
        data=gzip.compress(raw,mtime=0) if packed else raw
        with target.open('xb') as stream:stream.write(data)
        manifest[str(target.relative_to(destination))]=dict(sha256=hashlib.sha256(data).hexdigest(),
                                                           uncompressed_sha256=hashlib.sha256(raw).hexdigest())
    with (destination/'archive-manifest.json').open('x') as stream:json.dump(manifest,stream,indent=2)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--paired-native',type=Path,help='when given, directory is reduced detector result')
    p.add_argument('--archive',type=Path)
    a=p.parse_args()
    report=detector_pair(a.directory,a.paired_native) if a.paired_native else campaign(a.directory)
    report['scorer_sha256']={name:sha(Path(__file__).parent/name) for name in
                            ('dataset_campaign_report.py','score_causal_timeline.py','score_visdrone_det.py')}
    with (a.directory/'dataset-report.json').open('x') as stream:json.dump(report,stream,indent=2)
    if a.archive:
        archive(a.directory,a.archive)
        if a.paired_native:archive(a.paired_native,a.archive/'native')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))


if __name__=='__main__':main()
