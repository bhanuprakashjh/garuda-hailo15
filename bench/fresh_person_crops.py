#!/usr/bin/env python3
"""PC-only: reproduce the OSNet packed NV12 input from a pixel-crop manifest and saved JPEGs."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    import numpy as np
    from PIL import Image
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('images', type=Path)
    ap.add_argument('manifest', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    entries = json.loads(args.manifest.read_text())
    if not isinstance(entries, list) or not 1 <= len(entries) <= 600:
        raise ValueError('expected 1..600 crops')
    evidence = []
    with args.output.open('xb') as out:
        for i, entry in enumerate(entries):
            resolved = entry
            while 'duplicate_of' in resolved:
                index = resolved['duplicate_of']
                if type(index) is not int or not 0 <= index < i:
                    raise ValueError('duplicate must refer to an earlier frame')
                resolved = entries[index]
                if 'duplicate_of' in resolved:
                    raise ValueError('nested duplicate not supported')
            path = args.images / resolved['file']
            with Image.open(path) as source:
                x1, y1, x2, y2 = resolved['crop_xyxy']
                if any(type(v) is not int for v in (x1, y1, x2, y2)) or not (0 <= x1 < x2 <= source.width and 0 <= y1 < y2 <= source.height):
                    raise ValueError('invalid pixel crop')
                rgb = np.asarray(source.convert('RGB').crop((x1, y1, x2, y2)).resize((128, 256), Image.Resampling.BILINEAR), dtype=np.float32)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            y = np.clip(np.rint(16 + .257*r + .504*g + .098*b), 0, 255).astype(np.uint8)
            u = 128 - .148*r - .291*g + .439*b
            v = 128 + .439*r - .368*g - .071*b
            uv = np.empty((128, 128), np.uint8)
            uv[:, 0::2] = np.clip(np.rint(u.reshape(128, 2, 64, 2).mean(axis=(1, 3))), 0, 255)
            uv[:, 1::2] = np.clip(np.rint(v.reshape(128, 2, 64, 2).mean(axis=(1, 3))), 0, 255)
            packed = y.tobytes() + uv.tobytes()
            out.write(packed)
            evidence.append({'frame': i, 'source': resolved['file'], 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'crop_xyxy': [x1, y1, x2, y2], 'nv12_sha256': hashlib.sha256(packed).hexdigest()})
    args.output.with_suffix('.manifest.json').write_text(json.dumps({'frames': evidence,
        'scope': 'JPEG-derived RGB bilinear resize then BT.601 limited NV12; not raw ISP; detector-derived crops are not identity ground truth'}, indent=2) + '\n')
    print(f'Prepared {len(entries)} crops')

if __name__ == '__main__':
    main()
