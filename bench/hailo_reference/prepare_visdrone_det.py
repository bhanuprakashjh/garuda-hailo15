"""Prepare VisDrone2019-DET images as a replay stream for the on-board probe.

Every image is placed on ONE canvas the size of the node's tile source
(1280x720, the frame size `detection_tiles` requires): scaled to fit with the
aspect preserved, centred, padded with letterbox grey. VisDrone-DET-val mixes
1360x765, 960x540 and 1920x1080 (all 16:9, so no padding in practice; the
manifest records scale and offset per image either way). RGB is converted to
packed NV12 with the inverse of the SDK full-range matrix and a 2x2 chroma
mean — the same transform that produced the controlled HEF's calibration set.

Per image the regions mirror `five_tile_layout`: four 0.6x0.6 corner tiles at
0.4 stride, then the full view; the first region streams the frame, the rest
`reuse_source`. Scoring treats the full view alone as "single-tile" and all
five as "five-tile". Object sizes are recorded in original pixels; the scorer
buckets by canvas pixels (what the detector actually sees).
"""
import argparse
import hashlib
import json
import pathlib

import numpy as np
from PIL import Image

CANVAS_W, CANVAS_H = 1280, 720
PAD = (114, 114, 114)
FIELDS = ('x', 'y', 'w', 'h', 'score', 'category', 'truncation', 'occlusion')


def even_floor(v):
    return int(v) & ~1


def five_tile_layout(w, h):
    """Same fractions and rounding as garuda::fresh::five_tile_layout."""
    fracs = [(0.0, 0.0, 0.6, 0.6, False), (0.4, 0.0, 0.6, 0.6, False),
             (0.0, 0.4, 0.6, 0.6, False), (0.4, 0.4, 0.6, 0.6, False),
             (0.0, 0.0, 1.0, 1.0, True)]
    out = []
    for fx, fy, fw, fh, full in fracs:
        x, y = even_floor(fx * w), even_floor(fy * h)
        tw, th = even_floor(fw * w), even_floor(fh * h)
        if x + tw > w:
            tw = even_floor(w - x)
        if y + th > h:
            th = even_floor(h - y)
        out.append(dict(x=x, y=y, w=tw, h=th, full_frame=full))
    return out


def native_tile_layout(w=1920, h=1080):
    """Fixed, label-independent overlapping 640-square crops plus wide view."""
    def positions(size):
        if size < 640 or size % 2:
            raise ValueError('even source at least 640 required')
        return sorted(set(list(range(0, size-640+1, 512)) + [size-640]))
    return [dict(x=x,y=y,w=640,h=640,full_frame=False)
            for y in positions(h) for x in positions(w)] + [dict(x=0,y=0,w=w,h=h,full_frame=True)]


def place_native(image):
    """Preserve original RGB pixels; pad, never resize, into a fixed probe canvas."""
    if image.width > 1920 or image.height > 1080:
        raise ValueError('native-pixel experiment bounded to 1920x1080 originals')
    canvas=Image.new('RGB',(1920,1080),PAD)
    ox,oy=(1920-image.width)//2,(1080-image.height)//2
    canvas.paste(image,(ox,oy))
    return canvas,1.,ox,oy


def packed_full_nv12(image):
    """Inverse of the documented SDK full-range conversion, then 2x2 chroma mean."""
    rgb = np.asarray(image, dtype=np.float32)
    h, w = rgb.shape[:2]
    if h % 2 or w % 2:
        raise ValueError('NV12 needs even dimensions')
    matrix = np.array([[1, 0, 1.4], [1, -.343, -.711], [1, 1.765, 0]], np.float32)
    yuv = rgb @ np.linalg.inv(matrix).T
    yuv[:, :, 1:] += 128
    y = np.clip(np.rint(yuv[:, :, 0]), 0, 255).astype(np.uint8)
    uv = yuv[:, :, 1:].reshape(h // 2, 2, w // 2, 2, 2).mean(axis=(1, 3))
    uv = np.clip(np.rint(uv), 0, 255).astype(np.uint8)
    return np.concatenate([y.ravel(), uv.ravel()])


def place_on_canvas(image):
    scale = min(CANVAS_W / image.width, CANVAS_H / image.height)
    cw, ch = round(image.width * scale), round(image.height * scale)
    canvas = Image.new('RGB', (CANVAS_W, CANVAS_H), PAD)
    ox, oy = (CANVAS_W - cw) // 2, (CANVAS_H - ch) // 2
    canvas.paste(image.resize((cw, ch), Image.BILINEAR), (ox, oy))
    return canvas, scale, ox, oy


def read_annotations(path):
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip().rstrip(',')
        if not line:
            continue
        rows.append(dict(zip(FIELDS, (int(v) for v in line.split(',')))))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dataset', type=pathlib.Path, help='VisDrone2019-DET-val directory (images/, annotations/)')
    p.add_argument('output', type=pathlib.Path)
    p.add_argument('--limit', type=int, default=0, help='first N images only (0 = all)')
    p.add_argument('--sample-count', type=int, default=0, help='deterministic evenly spaced subset of sorted filenames')
    p.add_argument('--native-pixels', action='store_true', help='unresized originals in 1920x1080 padded source; fixed 640-grid, not live ISP')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    files = sorted((a.dataset / 'images').glob('*.jpg'))
    if a.sample_count:
        if a.limit or not 1 <= a.sample_count <= len(files):
            raise ValueError('choose valid sample-count OR limit')
        indices=np.linspace(0,len(files)-1,a.sample_count,dtype=int)
        files=[files[i] for i in indices]
    if a.limit:
        files = files[:a.limit]
    if not files:
        raise SystemExit('no images')
    regions, images = [], []
    digest = hashlib.sha256()
    sizes = {}
    width,height=(1920,1080) if a.native_pixels else (CANVAS_W,CANVAS_H)
    layout=native_tile_layout(width,height) if a.native_pixels else five_tile_layout(width,height)
    with (a.output / 'source.nv12').open('xb') as out:
        for index, file in enumerate(files):
            image = Image.open(file).convert('RGB')
            sizes[f'{image.width}x{image.height}'] = sizes.get(f'{image.width}x{image.height}', 0) + 1
            canvas, scale, ox, oy = place_native(image) if a.native_pixels else place_on_canvas(image)
            data = packed_full_nv12(canvas).tobytes()
            out.write(data)
            digest.update(data)
            for tile, r in enumerate(layout):
                regions.append(dict(source_w=width, source_h=height, **r, reuse_source=tile > 0,
                                    via_1080p=False, method='native_grid' if a.native_pixels else 'five_tile', tile=tile, image_index=index))
            images.append(dict(index=index, file=file.name, width=image.width, height=image.height,
                               image_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                               scale=scale, offset_x=ox, offset_y=oy,
                               gt=read_annotations(a.dataset / 'annotations' / (file.stem + '.txt'))))
    (a.output / 'regions.json').write_text(json.dumps(regions))
    manifest = dict(dataset=str(a.dataset.resolve()), canvas=[width, height], images=images,
                    inputs=len(regions), source_sha256=digest.hexdigest(), source_sizes=sizes,
                    tile_layout=layout, native_pixels=a.native_pixels,
                    sample_policy='evenly spaced sorted filenames' if a.sample_count else 'sorted filenames prefix/all',
                    conversion=('Unresized original RGB pixels, centred pad 114; ' if a.native_pixels else
                                'PIL bilinear fit to canvas, letterbox pad 114; ')+'RGB->NV12 via inverse SDK '
                               'full-range matrix, 2x2 chroma mean, rounded/clipped (same as controlled '
                               'HEF calibration transform)',
                    licence='VisDrone2019 (AISKYEYE, Tianjin University) — research use; images not committed')
    (a.output / 'manifest.json').write_text(json.dumps(manifest))
    print(json.dumps(dict(images=len(images), inputs=len(regions), source_sizes=sizes,
                          source_sha256=digest.hexdigest())))


if __name__ == '__main__':
    main()
