"""Isolated DFC 5.3 YOLO11s experiment, with retained stage artifacts and held-out inputs."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import numpy as np
from PIL import Image

MODEL_SHA = '0a44c5050d77a27abb971979e8399ab6084db18b0ffc7781e312171543efef8e'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def packed_full_nv12(image):
    # Inverse of the documented SDK full-range conversion, then 2x2 chroma mean. The packed
    # NV12 tensor the HEF consumes is (height/2, width, 3) for any even input size.
    rgb = np.asarray(image, dtype=np.float32)
    h, w = rgb.shape[:2]
    matrix = np.array([[1,0,1.4],[1,-.343,-.711],[1,1.765,0]], np.float32)
    yuv = rgb @ np.linalg.inv(matrix).T
    yuv[:, :, 1:] += 128
    y = np.clip(np.rint(yuv[:, :, 0]), 0, 255).astype(np.uint8)
    uv = yuv[:, :, 1:].reshape(h//2,2,w//2,2,2).mean(axis=(1,3))
    uv = np.clip(np.rint(uv), 0, 255).astype(np.uint8)
    return np.concatenate([y.ravel(), uv.ravel()]).reshape(h//2,w,3)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['prepare','parse','fp','fp-infer','quantize','quant-infer','compile'])
    p.add_argument('work', type=pathlib.Path)
    p.add_argument('--model', type=pathlib.Path)
    p.add_argument('--test-replay', type=pathlib.Path)
    p.add_argument('--calibration-root', type=pathlib.Path)
    p.add_argument('--model-sha', help='expected SHA256 of the source ONNX (default: the Hailo-published YOLO11s); '
                                       'a fine-tuned export passes its own recorded hash so the recipe stays pinned')
    p.add_argument('--input-size', type=int, nargs=2, default=(640, 640), metavar=('W', 'H'),
                   help='network input in pixels, matching the ONNX export (default 640 640); e.g. 1280 736 '
                        'holds a 16:9 frame at full 720p scale in one pass. Recorded in manifest.json and nms.json.')
    a = p.parse_args()
    global MODEL_SHA
    if a.model_sha:
        MODEL_SHA = a.model_sha
    W, H = a.input_size
    if W % 32 or H % 32 or W < 320 or H < 320 or W > 1920 or H > 1920:
        raise ValueError('input size must be multiples of 32 between 320 and 1920')
    a.work = a.work.resolve()
    os.chdir(a.work)
    if a.stage == 'prepare':
        if (a.work/'manifest.json').exists():
            raise ValueError('Preparation already exists')
        if sha(a.model) != MODEL_SHA:
            raise ValueError('Wrong source ONNX')
        files = sorted(a.calibration_root.rglob('*.jpg'))
        if len(files) < 1024:
            raise ValueError('Need 1024 separate calibration images')
        files = [files[i] for i in np.linspace(0, len(files)-1, 1024, dtype=int)]
        calibration = np.lib.format.open_memmap(a.work/'calibration.npy', mode='w+',
            dtype=np.uint8, shape=(1024,H//2,W,3))
        entries = []
        for index, path in enumerate(files):
            with Image.open(path) as source:
                image = source.convert('RGB')
                image.thumbnail((W,H), Image.Resampling.BILINEAR)
                canvas = Image.new('RGB',(W,H),(114,114,114))
                canvas.paste(image,((W-image.width)//2,(H-image.height)//2))
                calibration[index] = packed_full_nv12(canvas)
            entries.append(dict(path=str(path),sha256=sha(path)))
        calibration.flush()
        shutil.copyfile(a.model,a.work/'source.onnx')
        shutil.copyfile(a.test_replay/'network-inputs.nv12',a.work/'test-inputs.nv12')
        shutil.copyfile(a.test_replay/'regions.json',a.work/'regions.json')
        manifest = dict(onnx_sha256=MODEL_SHA, calibration=entries, input_size=dict(width=W,height=H),
            calibration_sha256=sha(a.work/'calibration.npy'), test_sha256=sha(a.work/'test-inputs.nv12'),
            scope='Diagnostic PTQ; 1024 indoor SUNRGBD calibration images separate from held-out desk crops; not COCO accuracy certification.',
            calibration_transform='RGB letterbox, inverse SDK full-range matrix, 2x2 chroma mean, rounded/clipped packed NV12')
        (a.work/'manifest.json').write_text(json.dumps(manifest,indent=2))
        print(f'Prepared 1024 calibration images at {W}x{H}; test inputs excluded',flush=True)
        return
    recorded = json.loads((a.work/'manifest.json').read_text()).get('input_size', dict(width=640,height=640))
    if (recorded['width'], recorded['height']) != (W, H):
        raise ValueError(f'work directory was prepared at {recorded["width"]}x{recorded["height"]}; pass the same --input-size')

    if sha(a.work/'source.onnx') != MODEL_SHA:
        raise ValueError('Controlled source ONNX changed')
    os.environ.setdefault('TF_FORCE_GPU_ALLOW_GROWTH','true')
    # Avoid the installed SDK's eager GPU warmup before its worker starts.
    os.environ.setdefault('HAILO_DISABLE_TF_AUTOSET','1')
    os.environ.setdefault('HAILO_DISABLE_MO_SUB_PROCESS','1')
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(4)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    for gpu in tf.config.list_physical_devices('GPU'):
        tf.config.experimental.set_memory_growth(gpu,True)
    from hailo_sdk_client import ClientRunner, InferenceContext
    calibration = np.load(a.work/'calibration.npy',mmap_mode='r')
    def dataset():
        def generate():
            for image in calibration:
                yield image.astype(np.float32), {}
        return tf.data.Dataset.from_generator(generate,
            output_signature=(tf.TensorSpec((H//2,W,3),tf.float32),{}))
    if a.stage == 'parse':
        runner = ClientRunner(hw_arch='hailo15l')
        nodes = [f'/model.23/cv{branch}.{i}/cv{branch}.{i}.2/Conv' for i in range(3) for branch in (2,3)]
        runner.translate_onnx_model(str(a.work/'source.onnx'),'yolov11s',end_node_names=nodes)
        runner.save_har(str(a.work/'parsed.har'))
        outputs = [l.inputs[0].rsplit('/',1)[-1] for l in runner.get_hn_model().get_output_layers()]
        config = dict(nms_scores_th=.05,nms_iou_th=.7,image_dims=[H,W],max_proposals_per_class=100,   # Hailo order: [height, width]
            classes=80,regression_length=16,background_removal=False,background_removal_index=0,
            bbox_decoders=[dict(name=f'bbox_decoder_{stride}',stride=stride,reg_layer=outputs[i*2],cls_layer=outputs[i*2+1]) for i,stride in enumerate((8,16,32))])
        (a.work/'nms.json').write_text(json.dumps(config,indent=2))
        script = ['normalization1 = normalization([0,0,0], [255,255,255])',
            'full_rgb = input_conversion(input_layer1, yuv_full_range_to_rgb)',
            'packed_yuv = input_conversion(input_layer1, nv12_to_hailo_yuv, emulator_support=True)',
            'model_optimization_flavor(optimization_level=2, compression_level=0, batch_size=1)',
            'model_optimization_config(calibration, batch_size=1, calibset_size=1024)',
            'post_quantization_optimization(finetune, policy=disabled)',
            'allocator_param(width_splitter_defuse=disabled)',
            'performance_param(compiler_optimization_level=0)']
        script += [f'change_output_activation({outputs[i]}, sigmoid)' for i in (1,3,5)]
        script += [f'nms_postprocess("{a.work}/nms.json", meta_arch=yolov8, engine=cpu)']
        (a.work/'model.alls').write_text('\n'.join(script)+'\n')
        print('Parsed output order:',outputs,flush=True)
        return
    if a.stage == 'quantize':
        runner = ClientRunner(har=str(a.work/'parsed.har'))
        runner.load_model_script(str(a.work/'model.alls'))
        runner.optimize(dataset)
        runner.save_har(str(a.work/'quantized.har'))
        return
    if a.stage == 'compile':
        runner = ClientRunner(har=str(a.work/'quantized.har'))
        (a.work/'controlled.hef').write_bytes(runner.compile())
        runner.save_har(str(a.work/'compiled.har'))
        print('HEF SHA256:',sha(a.work/'controlled.hef'),flush=True)
        return
    if a.stage == 'fp':
        runner = ClientRunner(har=str(a.work/'parsed.har'))
        runner.load_model_script(str(a.work/'model.alls'))
        runner.optimize_full_precision(dataset)
        runner.save_har(str(a.work/'fp.har'))
        context = InferenceContext.SDK_FP_OPTIMIZED
    elif a.stage == 'fp-infer':
        runner = ClientRunner(har=str(a.work/'fp.har'))
        context = InferenceContext.SDK_FP_OPTIMIZED
    else:
        runner = ClientRunner(har=str(a.work/'quantized.har'))
        context = InferenceContext.SDK_QUANTIZED
    inputs = np.fromfile(a.work/'test-inputs.nv12',dtype=np.uint8).reshape(-1,H//2,W,3).astype(np.float32)
    with runner.infer_context(context,nms_score_threshold=.05) as ctx:
        result = runner.infer(ctx,inputs,batch_size=1)
    array = np.asarray(result)
    np.save(a.work/(a.stage+'-outputs.npy'),array)
    print('Output shape:',array.shape,flush=True)

if __name__ == '__main__':
    main()
