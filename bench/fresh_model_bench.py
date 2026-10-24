#!/usr/bin/env python3
"""Fixed-image detector bench. PC-only: Pillow/numpy for prepare; Hailo probe runs on board."""
import argparse
import hashlib
import json
import pathlib
import time
import urllib.request

def capture(args):
    args.directory.mkdir(parents=True, exist_ok=False)
    start, last, count, buffer = time.monotonic(), 0, 0, b""
    with urllib.request.urlopen(args.url.rstrip("/") + "/stream", timeout=10) as response:
        with (args.directory / "frames.jsonl").open("w") as log:
            while time.monotonic() - start < args.seconds and count < 600:
                buffer += response.read(8192)
                if len(buffer) > 4 * 1024 * 1024:
                    raise ValueError("malformed or oversized MJPEG frame")
                while True:
                    begin = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", max(0, begin))
                    if begin < 0 or end < 0:
                        break
                    jpeg, buffer = buffer[begin:end + 2], buffer[end + 2:]
                    now = time.monotonic()
                    if now - last < .2:
                        continue
                    last = now
                    count += 1
                    name = f"{count:04}.jpg"
                    (args.directory / name).write_bytes(jpeg)
                    log.write(json.dumps({"file": name, "elapsed_s": now - start}) + "\n")
    print(f"saved {count} JPEG frames")

def prepare(args):
    import numpy as np
    from PIL import Image
    files = sorted(args.directory.glob("*.jpg"))[::args.stride]
    if not files or len(files) > 600:
        raise ValueError("expected 1..600 selected JPEGs")
    manifest = [{"frame": i, "file": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
                for i, f in enumerate(files)]
    for mode in ("stretch", "letterbox"):
        with (args.directory / (mode + ".nv12")).open("wb") as output:
            for file in files:
                image = Image.open(file).convert("RGB")
                if image.size != (1280, 720):
                    raise ValueError("bench expects a 1280x720 preview")
                if mode == "stretch":
                    resized = image.resize((640, 640), Image.Resampling.BILINEAR)
                else:
                    resized = Image.new("RGB", (640, 640), (114, 114, 114))
                    resized.paste(image.resize((640, 360), Image.Resampling.BILINEAR), (0, 140))
                rgb = np.asarray(resized, dtype=np.float32)
                r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
                y = np.clip(np.rint(16 + .257*r + .504*g + .098*b), 0, 255).astype(np.uint8)
                u, v = 128 - .148*r - .291*g + .439*b, 128 + .439*r - .368*g - .071*b
                u = np.clip(np.rint(u.reshape(320, 2, 320, 2).mean(axis=(1, 3))), 0, 255).astype(np.uint8)
                v = np.clip(np.rint(v.reshape(320, 2, 320, 2).mean(axis=(1, 3))), 0, 255).astype(np.uint8)
                uv = np.empty((320, 640), np.uint8)
                uv[:, 0::2], uv[:, 1::2] = u, v
                output.write(y.tobytes())
                output.write(uv.tobytes())
    (args.directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"prepared {len(files)} frames per mode; BT.601 limited NV12 from JPEG, not raw ISP input")

def summarize(args):
    import gzip
    results = {}
    for file in args.files:
        opener = gzip.open if file.suffix == ".gz" else open
        with opener(file, "rt") as source:
            rows = [json.loads(line) for line in source]
        results[file.name] = {
            "frames": len(rows),
            "phone_frames_at_confidence": {
                str(threshold): sum(any(d["class_id"] == 67 and d["score"] >= threshold
                                        for d in row["detections"]) for row in rows)
                for threshold in (.05, .15, .4, .5)
            },
            "person_frames_at_0.5": sum(any(d["class_id"] == 0 and d["score"] >= .5
                                            for d in row["detections"]) for row in rows),
        }
    print(json.dumps(results, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("capture")
    p.add_argument("directory", type=pathlib.Path)
    p.add_argument("--url", default="http://10.0.0.1:8099")
    p.add_argument("--seconds", type=float, default=60)
    p.set_defaults(run=capture)
    p = subs.add_parser("prepare")
    p.add_argument("directory", type=pathlib.Path)
    p.add_argument("--stride", type=int, default=4)
    p.set_defaults(run=prepare)
    p = subs.add_parser("summarize")
    p.add_argument("files", nargs="+", type=pathlib.Path)
    p.set_defaults(run=summarize)
    args = parser.parse_args()
    if getattr(args, "stride", 1) < 1 or not 0 < getattr(args, "seconds", 60) <= 120:
        parser.error("stride must be positive; duration must be 0..120 seconds")
    args.run(args)

if __name__ == "__main__":
    main()
