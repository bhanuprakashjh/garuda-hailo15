#!/usr/bin/env python3
"""PC-only float YOLOv8 reference on captured 640x640 NV12 (ONNX Runtime, numpy, Pillow)."""
import argparse
import json
import pathlib
import numpy as np
from PIL import Image
import onnxruntime as ort

def decode_nv12(file):
    packed = np.fromfile(file, np.uint8).astype(np.float32)
    if packed.size != 640 * 640 * 3 // 2:
        raise ValueError("expected packed 640x640 NV12")
    y, uv = packed[:409600].reshape(640, 640), packed[409600:].reshape(320, 640)
    u = uv[:, ::2].repeat(2, 0).repeat(2, 1) - 128
    v = uv[:, 1::2].repeat(2, 0).repeat(2, 1) - 128
    c = 1.164 * (y - 16)
    return np.clip(np.stack([c + 1.596*v, c - .392*u - .813*v, c + 2.017*u], -1), 0, 255).astype(np.uint8)

def detections(pred):
    result = []
    for cls in (0, 67):
        scores = pred[:, 4 + cls]
        indices = np.where(scores >= .05)[0]
        boxes = []
        for j in indices[np.argsort(scores[indices])[::-1]]:
            cx, cy, width, height = pred[j, :4]
            box = np.array([cx-width/2, cy-height/2, cx+width/2, cy+height/2])
            duplicate = False
            for old in boxes:
                area = max(0, min(box[2], old[2])-max(box[0], old[0])) * max(0, min(box[3], old[3])-max(box[1], old[1]))
                union = width*height + (old[2]-old[0])*(old[3]-old[1]) - area
                if union > 0 and area / union > .7:
                    duplicate = True
                    break
            if not duplicate:
                boxes.append(box)
                result.append({"class_id": cls, "score": float(scores[j]), "xyxy": (box / 640).tolist()})
            if len(boxes) >= 100:
                break
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("onnx", type=pathlib.Path)
    parser.add_argument("capture", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--compare-unstretch", action="store_true", help="Only use if actual captured pixels were stretched")
    args = parser.parse_args()
    if args.stride < 1 or not 1 <= args.limit <= 120:
        parser.error("positive stride and limit 1..120 required")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    session = ort.InferenceSession(str(args.onnx), options, providers=["CPUExecutionProvider"])
    if session.get_inputs()[0].shape != [1, 3, 640, 640] or session.get_outputs()[0].shape != [1, 84, 8400]:
        raise ValueError("unsupported reference ONNX layout")
    files = sorted(args.capture.glob("*.nv12"), key=lambda f: int(f.stem))[::args.stride][:args.limit]
    if not files:
        raise ValueError("no captured inputs")
    rows = []
    for file in files:
        rgb = decode_nv12(file)
        images = [("actual_input", rgb)]
        if args.compare_unstretch:
            corrected = Image.new("RGB", (640, 640), (114, 114, 114))
            corrected.paste(Image.fromarray(rgb).resize((640, 360), Image.Resampling.BILINEAR), (0, 140))
            images.append(("correct_letterbox", np.asarray(corrected)))
        for mode, pixels in images:
            output = session.run(None, {session.get_inputs()[0].name: pixels.astype(np.float32).transpose(2, 0, 1)[None] / 255})[0]
            if not np.isfinite(output).all():
                raise ValueError("nonfinite model result")
            rows.append({"sequence": int(file.stem), "mode": mode, "detections": detections(output[0].T)})
    args.output.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"inferred {len(rows)} reference inputs")

if __name__ == "__main__":
    main()
