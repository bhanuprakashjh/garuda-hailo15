"""YOLO11 ONNX on exact dumped DSP inputs; explicit color-conversion sensitivity."""
import argparse
import ast
import hashlib
import json
import pathlib
import numpy as np
import onnxruntime as ort
from PIL import Image
from score_4k_tiles import ANNOTATIONS, iou, map_box

def rgb_from_nv12(data, mode):
    packed = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
    if packed.size != 640*640*3//2:
        raise ValueError('Invalid packed NV12 size')
    y = packed[:640*640].reshape(640, 640)
    uv = packed[640*640:].reshape(320, 640)
    u = uv[:, ::2].repeat(2, 0).repeat(2, 1)-128
    v = uv[:, 1::2].repeat(2, 0).repeat(2, 1)-128
    if mode == '601_limited':
        c = 1.164*(y-16)
        channels = [c+1.596*v, c-.392*u-.813*v, c+2.017*u]
    elif mode == '709_limited':
        c = 1.164*(y-16)
        channels = [c+1.793*v, c-.213*u-.533*v, c+2.112*u]
    elif mode == 'sdk_full':
        channels = [y+1.4*v, y-.343*u-.711*v, y+1.765*u]
    else:
        raise ValueError('Unknown conversion')
    return np.clip(np.stack(channels, -1), 0, 255).astype(np.uint8)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('model', type=pathlib.Path)
    p.add_argument('replay', type=pathlib.Path)
    p.add_argument('output', type=pathlib.Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    regions = json.loads((a.replay/'regions.json').read_text())
    hailo = [json.loads(s) for s in (a.replay/'letterbox.jsonl').read_text().splitlines()]
    inputs = (a.replay/'network-inputs.nv12').read_bytes()
    size = 640*640*3//2
    if len(inputs) != len(regions)*size or len(hailo) != len(regions):
        raise ValueError('Input/prediction count mismatch')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    session = ort.InferenceSession(str(a.model), options, providers=['CPUExecutionProvider'])
    if session.get_inputs()[0].shape != [1, 3, 640, 640] or session.get_outputs()[0].shape != [1, 84, 8400]:
        raise ValueError('Unsupported ONNX shape')
    labels = ast.literal_eval(session.get_modelmeta().custom_metadata_map['names'])
    report = []
    for index, (region, hp) in enumerate(zip(regions, hailo)):
        if hp['frame'] != index:
            raise ValueError('Wrong Hailo prediction order')
        annotation = ANNOTATIONS[region['source_frame']]
        matched_hailo = []
        for d in hp['detections']:
            b = map_box(region, d)
            if b is not None and iou(b, annotation) >= .5:
                matched_hailo.append(dict(d, iou=iou(b, annotation)))
        for mode in ('601_limited', '709_limited', 'sdk_full'):
            rgb = rgb_from_nv12(inputs[index*size:(index+1)*size], mode)
            Image.fromarray(rgb).save(a.output/f'input-{index:02d}-{mode}.png')
            tensor = rgb.transpose(2, 0, 1)[None].astype(np.float32)/255
            pred = session.run(None, {session.get_inputs()[0].name: tensor})[0][0].T
            if pred.shape != (8400, 84) or not np.isfinite(pred).all():
                raise ValueError('Invalid model output')
            # Inspect every anchor before NMS, so suppression cannot hide a
            # low-confidence phone or alternative class at the annotated box.
            matches = []
            phone_ds = []
            for row in pred:
                cx, cy, w, h = row[:4]
                d = dict(x1=float((cx-w/2)/640), y1=float((cy-h/2)/640),
                         x2=float((cx+w/2)/640), y2=float((cy+h/2)/640))
                b = map_box(region, d)
                if b is None:
                    continue
                overlap = iou(b, annotation)
                if overlap >= .5:
                    classes = np.argsort(row[4:])[-5:][::-1]
                    matches.append(dict(phone_score=float(row[71]), iou=overlap,
                        top_classes=[dict(label=labels[int(c)], score=float(row[4+c])) for c in classes]))
                if row[71] >= .05:
                    phone_ds.append(dict(score=float(row[71]), box=b, iou=overlap))
            kept = []
            for d in sorted(phone_ds, key=lambda d:d['score'], reverse=True):
                if not any(iou(d['box'], k['box']) > .7 for k in kept):
                    kept.append(d)
            result = dict(index=index, source_frame=region['source_frame'], method=region['method'],
                conversion=mode, matched_hailo=matched_hailo,
                float_best_phone_score_before_nms=max((m['phone_score'] for m in matches), default=None),
                float_best_phone_anchor=max(matches, key=lambda m:m['phone_score'], default=None),
                float_strongest_alternative=max(matches, key=lambda m:m['top_classes'][0]['score'], default=None),
                float_phone_after_nms=kept)
            report.append(result)
            print(json.dumps({k:result[k] for k in ('index','source_frame','method','conversion','float_best_phone_score_before_nms')}), flush=True)
    manifest = dict(onnx_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        nv12_sha256=hashlib.sha256(inputs).hexdigest(), onnxruntime=ort.__version__,
        onnx_metadata=session.get_modelmeta().custom_metadata_map,
        source_url='https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ObjectDetection/Detection-COCO/yolo/yolov11s/2024-10-02/yolo11s.zip',
        limitations='HEF source-weight identity and embedded conversion unverified; three explicit RGB conversions with clipping/uint8 rounding, not a bit-exact HEF emulation. Sparse oracle crops, not recall/tracking.',
        rows=report)
    (a.output/'report.json').write_text(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
