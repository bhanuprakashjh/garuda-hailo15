#!/usr/bin/env python3
"""Reproduce and score a sparse, oracle-crop object appearance diagnostic (not tracking accuracy)."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(args):
    import numpy as np
    from PIL import Image, __version__ as pillow_version
    manifest = json.loads(args.manifest.read_text())
    roots = dict(item.split('=', 1) for item in args.root)
    frames = manifest['frames']
    if not 1 <= len(frames) <= 600:
        raise ValueError('expected 1..600 frames')
    prepared = []
    with args.output.open('xb') as output:
        for i, entry in enumerate(frames):
            data = (Path(roots[entry['root']]) / entry['file']).read_bytes()
            if digest(data) != entry['source_sha256']:
                raise ValueError(f'source hash mismatch at {i}')
            import io
            with Image.open(io.BytesIO(data)) as source:
                box = entry['crop_xyxy']
                if len(box) != 4 or any(type(v) is not int for v in box):
                    raise ValueError('integer crop required')
                x1, y1, x2, y2 = box
                if not (0 < x2-x1 == y2-y1 <= 2048 and x1 < source.width and y1 < source.height and x2 > 0 and y2 > 0):
                    raise ValueError('expected intersecting square crop of at most 2048 pixels')
                # Out-of-image pixels are black, preserving square geometry at the edge.
                rgb = np.asarray(source.convert('RGB').crop(box).resize((224, 224), Image.Resampling.BILINEAR), dtype=np.float32)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            y = np.clip(np.rint(16 + .257*r + .504*g + .098*b), 0, 255).astype(np.uint8)
            u, v = 128 - .148*r - .291*g + .439*b, 128 + .439*r - .368*g - .071*b
            uv = np.empty((112, 224), np.uint8)
            uv[:, 0::2] = np.clip(np.rint(u.reshape(112, 2, 112, 2).mean(axis=(1, 3))), 0, 255)
            uv[:, 1::2] = np.clip(np.rint(v.reshape(112, 2, 112, 2).mean(axis=(1, 3))), 0, 255)
            packed = y.tobytes() + uv.tobytes()
            output.write(packed)
            prepared.append(dict(entry, frame=i, nv12_sha256=digest(packed)))
    args.output.with_suffix('.manifest.json').write_text(json.dumps({
        'manifest_sha256': digest(args.manifest.read_bytes()), 'frames': prepared, 'anchor': manifest.get('anchor', 0),
        'preprocessing': 'square oracle crop; black edge padding; Pillow bilinear 224x224 RGB; BT.601 limited NV12 with 2x2 mean chroma',
        'pillow_version': pillow_version, 'numpy_version': np.__version__,
        'input_sha256': digest(args.output.read_bytes()),
        'scope': 'JPEG-derived sparse appearance diagnostic; no detector, trajectory, ISP or identity accuracy claim'
    }, indent=2) + '\n')


def score(args):
    import numpy as np
    manifest = json.loads(args.manifest.read_text())
    frames = manifest['frames']
    rows = [json.loads(line) for line in args.embeddings.read_text().splitlines() if line.strip()]
    if len(rows) != len(frames) or not rows:
        raise ValueError('embedding/frame count mismatch')
    model = rows[0]['model']
    vectors = []
    for i, (entry, row) in enumerate(zip(frames, rows)):
        vector = np.asarray(row['embedding'], dtype=np.float64)
        if row['frame'] != i or entry['frame'] != i or row['model'] != model or vector.shape != (512,) or not np.isfinite(vector).all() or abs(np.linalg.norm(vector)-1) > 1e-5:
            raise ValueError(f'invalid embedding at {i}')
        if (row['input_width'], row['input_height']) != (224, 224):
            raise ValueError('unexpected input geometry')
        if entry['role'] not in ('same_phone', 'other_phone', 'printed_phone_excluded', 'duplicate'):
            raise ValueError('unknown diagnostic role')
        if entry['role'] == 'duplicate':
            index = entry.get('duplicate_of')
            if type(index) is not int or not 0 <= index < i or entry.get('nv12_sha256') != frames[index].get('nv12_sha256'):
                raise ValueError('duplicate must bind an earlier identical input')
        elif 'duplicate_of' in entry:
            raise ValueError('duplicates cannot count as independent queries')
        vectors.append(vector)
    similarity = np.clip(np.asarray(vectors) @ np.asarray(vectors).T, -1, 1)
    positives = [i for i, e in enumerate(frames) if e['role'] == 'same_phone']
    negatives = [i for i, e in enumerate(frames) if e['role'] == 'other_phone']
    anchor = manifest.get('anchor', 0)
    if type(anchor) is not int or anchor not in positives or len(positives) < 2 or not negatives:
        raise ValueError('need a positive anchor, another view and other-phone examples')
    positive_scores = [float(similarity[anchor, i]) for i in positives if i != anchor]
    negative_scores = [float(similarity[anchor, i]) for i in negatives]
    pairs = [float(similarity[a, b]) for a in positives for b in positives if a < b]
    cross = [float(similarity[a, b]) for a in positives for b in negatives]
    result = {
        'scope': 'descriptive sparse oracle-crop diagnostic; thresholds are not calibrated identity gates; negatives include visibly different older handsets',
        'model': model, 'embeddings_sha256': digest(args.embeddings.read_bytes()),
        'manifest_sha256': digest(args.manifest.read_bytes()), 'anchor_frame': anchor,
        'same_phone_views': len(positives), 'other_phone_images': len(negatives),
        'anchor_same_phone_range': [min(positive_scores), max(positive_scores)],
        'anchor_other_phone_range': [min(negative_scores), max(negative_scores)],
        'all_same_phone_pairs_range': [min(pairs), max(pairs)],
        'all_cross_phone_pairs_range': [min(cross), max(cross)],
        'anchor_scores': [dict(frame=i, role=e['role'], cosine=float(similarity[anchor, i])) for i, e in enumerate(frames)],
        'fixed_threshold_diagnostic': [dict(threshold=t, same_phone_accepted=sum(v >= t for v in positive_scores), same_phone_queries=len(positive_scores),
            other_phone_accepted=sum(v >= t for v in negative_scores), other_phone_queries=len(negative_scores)) for t in (.7, .75, .8, .85, .9, .95)],
        'duplicate_max_abs_difference': {str(i): float(np.max(np.abs(vectors[i]-vectors[e['duplicate_of']]))) for i, e in enumerate(frames) if 'duplicate_of' in e},
        'cosine_matrix': similarity.tolist()
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('manifest', type=Path)
    prep.add_argument('output', type=Path)
    prep.add_argument('--root', action='append', required=True, help='name=/local/image/root')
    prep.set_defaults(run=prepare)
    scoring = sub.add_parser('score')
    scoring.add_argument('manifest', type=Path, help='prepared .manifest.json')
    scoring.add_argument('embeddings', type=Path)
    scoring.add_argument('output', type=Path)
    scoring.set_defaults(run=score)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
