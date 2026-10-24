"""Inventory local data and flag provenance risks; never certify a holdout.

Filename group matches are conservative review flags, not proof that two frames
come from the same flight. Absence of a match cannot establish independence.
No images are copied, downloaded, decoded or used for training by this tool.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequence_group(name):
    match = re.fullmatch(r'uav(\d{7})_\d+_[sv]', name)
    return match.group(1) if match else None


def detection_group(name):
    match = re.fullmatch(r'(\d{7})_\d+_d_\d+\.(?:jpg|png)', name, re.I)
    return match.group(1) if match else None


def image_inventory(directory):
    if not directory.is_dir():
        raise ValueError(f'missing image directory: {directory}')
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    if not files:
        raise ValueError(f'empty image directory: {directory}')
    groups, source_sets = Counter(), Counter()
    resolved_paths = set()
    fingerprint = hashlib.sha256()
    for path in files:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ValueError(f'not a source file: {path}')
        group = detection_group(resolved.name)
        if group:
            groups[group] += 1
        # Named archive/split location, not an inferred license or model lineage.
        source_sets[str(resolved.parent)] += 1
        resolved_paths.add(str(resolved))
        fingerprint.update(json.dumps([path.name, str(resolved)], ensure_ascii=True).encode() + b'\n')
    return dict(directory=str(directory.resolve()), images=len(files),
                unique_resolved_sources=len(resolved_paths),
                source_directories=dict(sorted(source_sets.items())),
                filename_groups=dict(sorted(groups.items())),
                path_listing_sha256=fingerprint.hexdigest(),
                fingerprint_scope='names and resolved paths only; NOT image-content hashes')


def audit(visdrone, prepared, detector_train, reid_index):
    inventory = {split: image_inventory(visdrone / split / 'images')
                 for split in ('VisDrone2019-DET-train', 'VisDrone2019-DET-val')}
    training = image_inventory(detector_train)
    reid = json.loads(reid_index.read_text())
    reid_groups = {'train': set(), 'holdout': set()}
    id_counts, crop_counts = Counter(), Counter()
    for identity in reid['identities']:
        split = identity['split']
        group = sequence_group(identity['sequence'])
        if split not in reid_groups or group is None:
            raise ValueError('unknown reid split or sequence naming')
        if type(identity['crops']) is not int or identity['crops'] <= 0:
            raise ValueError('invalid crop count')
        reid_groups[split].add(group)
        id_counts[split] += 1
        crop_counts[split] += identity['crops']
    if not id_counts['train'] or not id_counts['holdout']:
        raise ValueError('missing reid training/validation identities')
    overlap = reid_groups['train'] & reid_groups['holdout']
    if overlap:
        raise ValueError(f'reid train/holdout group collision: {sorted(overlap)}')
    sot_root = visdrone / 'VisDrone2019-SOT-val' / 'sequences'
    mot_root = visdrone / 'VisDrone2019-MOT-val' / 'sequences'
    if not sot_root.is_dir() or not mot_root.is_dir():
        raise ValueError('missing raw video split')
    cases = []
    for manifest in sorted(prepared.glob('*/manifest.json')):
        data = json.loads(manifest.read_text())
        sequence = Path(data['sequence'])
        if sequence.resolve().parent != sot_root.resolve():
            raise ValueError('prepared sequence is outside declared SOT source split')
        group = sequence_group(sequence.name)
        if group is None or sequence.name != manifest.parent.name:
            raise ValueError('unknown or mismatched prepared sequence')
        frame_count = sum(1 for p in sequence.glob('*.jpg'))
        if not frame_count or type(data['frames']) is not int or not 0 < data['frames'] <= frame_count:
            raise ValueError('invalid prepared/raw frame count')
        cases.append(dict(sequence=sequence.name, filename_group=group,
                          raw_frames=frame_count, prepared_frames=data['frames'],
                          manifest_sha256=sha(manifest),
                          declared_source_sha256=data['source_sha256'],
                          detector_training_filename_group_match=group in training['filename_groups'],
                          reid_training_filename_group_match=group in reid_groups['train'],
                          reid_validation_filename_group_match=group in reid_groups['holdout'],
                          disposition='development: already used in tracker/model selection',
                          untouched_holdout=False))
    if not cases:
        raise ValueError('no prepared sequence manifests')
    return dict(scope='local inventory/provenance risk audit, not independence or license certification',
                inventory=inventory, declared_detector_training=training,
                detector_lineage_limit='training directory supplied by operator; does not prove checkpoint/HEF lineage',
                reid_index_sha256=sha(reid_index), reid_identity_counts=dict(id_counts),
                reid_crop_counts=dict(crop_counts),
                reid_filename_groups={k: sorted(v) for k, v in reid_groups.items()},
                raw_sot_sequences=sorted(p.name for p in sot_root.iterdir() if p.is_dir()),
                raw_mot_sequences=sorted(p.name for p in mot_root.iterdir() if p.is_dir()),
                cases=cases, prepared_frames_total=sum(c['prepared_frames'] for c in cases),
                eligible_untouched_holdout_sequences=0,
                caveats=['No pixel near-duplicate scan or authoritative flight mapping performed',
                         'Different task/split names do not establish flight independence',
                         'ReID holdout was scored during model development; it is validation, not untouched test',
                         'Source byte digests are declared by manifests, not rehashed by this inventory',
                         'No license permissions are inferred from local availability'],
                drone_mount_qualified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visdrone', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--detector-train', type=Path, required=True)
    parser.add_argument('--reid-index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.visdrone, args.prepared, args.detector_train, args.reid_index)
    result['auditor_sha256'] = sha(Path(__file__))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(cases=len(result['cases']), frames=result['prepared_frames_total'],
                         untouched_holdout=result['eligible_untouched_holdout_sequences'],
                         detector_group_matches=[c['sequence'] for c in result['cases']
                                                 if c['detector_training_filename_group_match']])))


if __name__ == '__main__':
    main()
