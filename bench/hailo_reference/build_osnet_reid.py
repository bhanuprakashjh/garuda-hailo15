"""Compile an OSNet x1.0 person re-identification ONNX for the Hailo-15L with the model zoo's
quantisation recipe (normalisation in-net, percentile clipping on the two layers the zoo names,
bias correction) and the same NV12 input conversion as the deployed detector recipe, so the
node feeds it the same 128x256 NV12 crops it feeds the zoo HEF today.

Stages, each in its own process: prepare (1024 calibration crops, packed NV12 128x128x3, from a
directory of 128x256 person crops) -> parse -> quantize -> compile. The source ONNX is pinned by
hash. Bench only; the HEF is a candidate until measured on the board.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import numpy as np
from PIL import Image


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def packed_full_nv12(image):
    """Inverse of the documented SDK full-range conversion, then 2x2 chroma mean: (h/2, w, 3)."""
    rgb = np.asarray(image, dtype=np.float32)
    h, w = rgb.shape[:2]
    matrix = np.array([[1, 0, 1.4], [1, -.343, -.711], [1, 1.765, 0]], np.float32)
    yuv = rgb @ np.linalg.inv(matrix).T
    yuv[:, :, 1:] += 128
    y = np.clip(np.rint(yuv[:, :, 0]), 0, 255).astype(np.uint8)
    uv = yuv[:, :, 1:].reshape(h // 2, 2, w // 2, 2, 2).mean(axis=(1, 3))
    uv = np.clip(np.rint(uv), 0, 255).astype(np.uint8)
    return np.concatenate([y.ravel(), uv.ravel()]).reshape(h // 2, w, 3)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('stage', choices=['prepare', 'parse', 'quantize', 'compile'])
    p.add_argument('work', type=pathlib.Path)
    p.add_argument('--model', type=pathlib.Path, help='source ONNX (prepare)')
    p.add_argument('--model-sha', required=True, help='expected SHA256 of the source ONNX; the recipe stays pinned')
    p.add_argument('--calibration-root', type=pathlib.Path, help='directory tree of 128x256 person crops (prepare)')
    a = p.parse_args()
    a.work = a.work.resolve()
    os.chdir(a.work)
    if a.stage == 'prepare':
        if (a.work / 'manifest.json').exists():
            raise ValueError('Preparation already exists')
        if sha(a.model) != a.model_sha:
            raise ValueError('Wrong source ONNX')
        files = sorted(a.calibration_root.rglob('*.png'))
        if len(files) < 1024:
            raise ValueError('Need 1024 separate calibration crops')
        files = [files[i] for i in np.linspace(0, len(files) - 1, 1024, dtype=int)]
        calibration = np.lib.format.open_memmap(a.work / 'calibration.npy', mode='w+', dtype=np.uint8, shape=(1024, 128, 128, 3))
        entries = []
        for index, path in enumerate(files):
            with Image.open(path) as source:
                image = source.convert('RGB')
                if image.size != (128, 256):
                    image = image.resize((128, 256), Image.BILINEAR)
                calibration[index] = packed_full_nv12(image)
            entries.append(dict(path=str(path), sha256=sha(path)))
        calibration.flush()
        shutil.copyfile(a.model, a.work / 'source.onnx')
        manifest = dict(onnx_sha256=a.model_sha, calibration=entries, calibration_sha256=sha(a.work / 'calibration.npy'),
                        input=dict(width=128, height=256, packed_nv12=[128, 128, 3]),
                        scope='PTQ of a fine-tuned OSNet x1.0 on 1024 drone-view person crops; bench candidate, not certified',
                        calibration_transform='128x256 RGB crop, inverse SDK full-range matrix, 2x2 chroma mean, packed NV12')
        (a.work / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print('Prepared 1024 calibration crops', flush=True)
        return
    if sha(a.work / 'source.onnx') != a.model_sha:
        raise ValueError('Controlled source ONNX changed')
    os.environ.setdefault('TF_FORCE_GPU_ALLOW_GROWTH', 'true')
    os.environ.setdefault('HAILO_DISABLE_TF_AUTOSET', '1')
    os.environ.setdefault('HAILO_DISABLE_MO_SUB_PROCESS', '1')
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(4)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    for gpu in tf.config.list_physical_devices('GPU'):
        tf.config.experimental.set_memory_growth(gpu, True)
    from hailo_sdk_client import ClientRunner
    calibration = np.load(a.work / 'calibration.npy', mmap_mode='r')

    def dataset():
        def generate():
            for image in calibration:
                yield image.astype(np.float32), {}
        return tf.data.Dataset.from_generator(generate, output_signature=(tf.TensorSpec((128, 128, 3), tf.float32), {}))
    if a.stage == 'parse':
        runner = ClientRunner(hw_arch='hailo15l')
        runner.translate_onnx_model(str(a.work / 'source.onnx'), 'osnet_x1_0')
        runner.save_har(str(a.work / 'parsed.har'))
        names = [l.name for l in runner.get_hn_model().layers.values()] if hasattr(runner.get_hn_model(), 'layers') else []
        # The zoo clips two layers by name; keep the lines only when this graph has those layers.
        clip = [name for name in ('dw51', 'dense_conv79') if any(n.endswith(name) for n in names)] if names else ['dw51', 'dense_conv79']
        script = ['normalization1 = normalization([123.675, 116.28, 103.53], [58.395, 57.12, 57.375])',
                  'full_rgb = input_conversion(input_layer1, yuv_full_range_to_rgb)',
                  'packed_yuv = input_conversion(input_layer1, nv12_to_hailo_yuv, emulator_support=True)',
                  'model_optimization_config(calibration, batch_size=8, calibset_size=1024)',
                  'pre_quantization_optimization(equalization, policy=disabled)']
        script += [f'pre_quantization_optimization(activation_clipping, layers=[{"osnet_x1_0/" + c if c.startswith("dense") else c}], mode=percentile, clipping_values=[0, 99.75])' for c in clip]
        script += ['post_quantization_optimization(finetune, policy=disabled)',
                   'post_quantization_optimization(bias_correction, policy=enabled)']
        (a.work / 'model.alls').write_text('\n'.join(script) + '\n')
        (a.work / 'layers.txt').write_text('\n'.join(names))
        print('Parsed; clipping layers present:', clip, flush=True)
        return
    if a.stage == 'quantize':
        runner = ClientRunner(har=str(a.work / 'parsed.har'))
        runner.load_model_script(str(a.work / 'model.alls'))
        runner.optimize(dataset)
        runner.save_har(str(a.work / 'quantized.har'))
        return
    runner = ClientRunner(har=str(a.work / 'quantized.har'))
    (a.work / 'osnet_reid.hef').write_bytes(runner.compile())
    runner.save_har(str(a.work / 'compiled.har'))
    print('HEF SHA256:', sha(a.work / 'osnet_reid.hef'), flush=True)


if __name__ == '__main__':
    main()
