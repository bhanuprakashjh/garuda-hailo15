#!/usr/bin/env python3
"""PC-only paired phone crop diagnostic. Oracle crops measure detector headroom, not tracking."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def main():
    import numpy as np
    from PIL import Image
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('images', type=Path)
    ap.add_argument('annotations', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    annotations = json.loads(args.annotations.read_text())
    frames = annotations['frames']
    if not 1 <= len(frames) <= 12:
        raise ValueError('expected 1..12 annotated frames; bounded board staging')
    args.output.mkdir(parents=True, exist_ok=False)
    regions = []
    with (args.output / 'source.nv12').open('wb') as output:
        for frame in frames:
            path = args.images / frame['file']
            with Image.open(path) as image:
                if image.size != (1280, 720):
                    raise ValueError('expected 1280x720 JPEG')
                rgb = np.asarray(image.convert('RGB'), dtype=np.float32)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            y = np.clip(np.rint(16 + .257*r + .504*g + .098*b), 0, 255).astype(np.uint8)
            u = 128 - .148*r - .291*g + .439*b
            v = 128 + .439*r - .368*g - .071*b
            u = np.clip(np.rint(u.reshape(360, 2, 640, 2).mean(axis=(1, 3))), 0, 255).astype(np.uint8)
            v = np.clip(np.rint(v.reshape(360, 2, 640, 2).mean(axis=(1, 3))), 0, 255).astype(np.uint8)
            uv = np.empty((360, 1280), np.uint8)
            uv[:, 0::2], uv[:, 1::2] = u, v
            def degrade(a):
                im = Image.fromarray(a)
                return np.asarray(im.resize((im.width//2, im.height//2), Image.Resampling.BILINEAR).resize(im.size, Image.Resampling.BILINEAR))
            low_y = degrade(y)
            low_uv = np.empty_like(uv)
            low_uv[:, 0::2], low_uv[:, 1::2] = degrade(u), degrade(v)
            x1, y1, x2, y2 = frame['box_xyxy']
            if not (0 <= x1 < x2 <= 1280 and 0 <= y1 < y2 <= 720):
                raise ValueError('invalid annotation')
            dynamic = max(320, math.ceil(2.5 * max(x2-x1, y2-y1) / 2)*2)
            if dynamic > 720:
                raise ValueError('annotated phone too large for local diagnostic')
            for mode, side in [('full', None), ('crop640', 640), ('crop_dynamic', dynamic), ('crop_degraded', dynamic)]:
                region = dict(source_w=1280, source_h=720, x=0, y=0, w=1280, h=720, full_frame=side is None)
                if side:
                    region.update(x=int(max(0, min(1280-side, (x1+x2-side)/2))//2)*2,
                                  y=int(max(0, min(720-side, (y1+y2-side)/2))//2)*2, w=side, h=side)
                region.update(mode=mode, file=frame['file'], annotation_xyxy=frame['box_xyxy'],
                              clipped=frame['clipped'], source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              localization='current-frame manual annotation (oracle)')
                regions.append(region)
                if mode == 'crop_degraded': output.write(low_y.tobytes());output.write(low_uv.tobytes())
                else: output.write(y.tobytes());output.write(uv.tobytes())
    (args.output/'regions.json').write_text(json.dumps(regions, indent=2)+'\n')
    print(f'Prepared {len(regions)} paired inputs; JPEG-derived NV12; no tracking metric implied')

if __name__ == '__main__':
    main()
