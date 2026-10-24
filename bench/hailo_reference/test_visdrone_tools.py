import json
import numpy as np
from PIL import Image

import prepare_visdrone_det as prep
import score_visdrone_det as score
import sot_to_replay
import score_sot_replay


def test_native_grid_preserves_pixels_and_covers_source():
    image=Image.new('RGB',(1360,765),(12,34,56))
    canvas,scale,ox,oy=prep.place_native(image)
    assert scale==1 and canvas.crop((ox,oy,ox+1360,oy+765)).tobytes()==image.tobytes()
    grid=prep.native_tile_layout()
    covered=np.zeros((1080,1920),dtype=bool)
    for r in grid[:-1]:
        assert r['w']==r['h']==640
        covered[r['y']:r['y']+640,r['x']:r['x']+640]=True
    assert covered.all() and len(grid)==9 and grid[-1]['full_frame']


def test_original_pixel_buckets_do_not_shift_with_canvas():
    img=dict(index=0,scale=.5,offset_x=0,offset_y=0,gt=[
        dict(x=10,y=20,w=10,h=40,score=1,category=1)])
    m=dict(images=[img],native_pixels=True)
    r=score.evaluate({},m,size_space='original')
    assert r['grid@0.15']['recall']['person/32-64px']['total']==1
    assert 'person/16-32px' not in r['grid@0.15']['recall']


def test_five_tile_layout_matches_node_geometry():
    # Values the C++ five_tile_layout produces for the node's 1280x720 source.
    tiles = prep.five_tile_layout(1280, 720)
    assert [(t['x'], t['y'], t['w'], t['h'], t['full_frame']) for t in tiles] == [
        (0, 0, 768, 432, False), (512, 0, 768, 432, False),
        (0, 288, 768, 432, False), (512, 288, 768, 432, False), (0, 0, 1280, 720, True)]
    assert all(v % 2 == 0 for t in tiles for v in (t['x'], t['y'], t['w'], t['h']))


def test_nv12_roundtrip_of_flat_colour():
    image = Image.new('RGB', (64, 32), (200, 100, 50))
    packed = prep.packed_full_nv12(image)
    assert packed.size == 64*32*3//2
    y, uv = packed[:64*32].astype(float), packed[64*32:].reshape(16, 64)
    u, v = float(uv[0, 0]), float(uv[0, 1])
    # invert with the SDK full-range forward matrix
    r, g, b = y[0]+1.4*(v-128), y[0]-.343*(u-128)-.711*(v-128), y[0]+1.765*(u-128)
    assert abs(r-200) < 2 and abs(g-100) < 2 and abs(b-50) < 2
    assert np.ptp(packed[:64*32]) == 0


def test_canvas_placement_keeps_aspect_and_centres():
    canvas, scale, ox, oy = prep.place_on_canvas(Image.new('RGB', (960, 540), (0, 0, 0)))
    assert canvas.size == (1280, 720) and abs(scale-4/3) < 1e-9 and (ox, oy) == (0, 0)
    canvas, scale, ox, oy = prep.place_on_canvas(Image.new('RGB', (640, 640), (0, 0, 0)))
    assert scale == 720/640 and ox == (1280-720)//2 and oy == 0
    assert canvas.getpixel((0, 0)) == prep.PAD and canvas.getpixel((640, 360)) == (0, 0, 0)


def test_cuts_object_unpads_letterbox_and_can_reproduce_archived_bug():
    left_top = dict(source_w=1280, source_h=720, x=0, y=0, w=768, h=432, full_frame=False)
    # touching the tile's right (interior) edge is cut; touching the frame's left edge is not
    assert score.cuts_object(left_top, dict(x1=.5, y1=.4, x2=.95, y2=.5), .08)
    assert not score.cuts_object(left_top, dict(x1=0, y1=.4, x2=.2, y2=.5), .08)
    # letterbox content spans 0.21875..0.78125 vertically: a box on the content's
    # bottom edge is now checked against CONTENT, not the padded network frame.
    assert score.cuts_object(left_top, dict(x1=.3, y1=.7, x2=.4, y2=.78125), .08)
    assert not score.cuts_object(left_top, dict(x1=.3, y1=.7, x2=.4, y2=.78125), .08,legacy=True)
    assert not score.cuts_object(dict(left_top, full_frame=True), dict(x1=.5, y1=.4, x2=.99, y2=.5), .08)


def test_aggregate_prefers_full_body_and_preserves_same_view_objects():
    big = dict(label='person', score=.8, box=[0, 0, 100, 100],region_id=4,region_full_frame=True)
    inner = dict(label='person', score=.95, box=[10, 10, 50, 50],region_id=0,region_full_frame=False)
    other = dict(label='car', score=.5, box=[10, 10, 50, 50])      # other class survives
    kept = score.aggregate([inner, big, other])
    assert kept == [big, other]
    assert score.aggregate([inner,big],legacy=True)==[inner]
    same_view=dict(inner,region_id=4,region_full_frame=True)
    assert score.aggregate([same_view,big])==[same_view,big]


def test_group_matching_and_ignore_regions(tmp_path):
    img = dict(index=0, scale=2.0, offset_x=0, offset_y=0, gt=[
        dict(x=10, y=10, w=20, h=10, score=1, category=5, truncation=0, occlusion=0),   # van
        dict(x=100, y=100, w=50, h=50, score=1, category=7, truncation=0, occlusion=0),  # tricycle: ignore
        dict(x=300, y=300, w=10, h=40, score=0, category=1, truncation=0, occlusion=0)]) # score 0: ignore
    manifest = dict(images=[img], canvas=[1280, 720], source_sizes={})
    per_image = {0: dict(full=[dict(label='truck', score=.8, box=[20, 20, 60, 40]),   # van as truck: hit
                              dict(label='person', score=.7, box=[210, 210, 220, 240]),  # in tricycle: no FP
                              dict(label='car', score=.9, box=[500, 500, 540, 520])],  # FP
                         corners=[])}
    m = score.evaluate(per_image, manifest)
    single = m['single@0.15']
    assert single['recall']['vehicle/16-32px'] == dict(matched=1, total=1, recall=1.0)
    assert single['recall']['all/all']['total'] == 1
    assert single['fp_per_image'] == 1.0
    assert single['fp_breakdown']['by_label']['car'] == 1 and single['fp_breakdown']['near_miss_iou_0_3'] == 0


def test_load_results_applies_node_filters(tmp_path):
    regions = [dict(source_w=1280, source_h=720, x=0, y=0, w=1280, h=720, full_frame=True, image_index=0),
               dict(source_w=1280, source_h=720, x=0, y=0, w=768, h=432, full_frame=False, image_index=0)]
    preds = [dict(frame=0, preprocessing='letterbox', detections=[
                 dict(label='person', score=.5, x1=.4, y1=.4, x2=.5, y2=.6),
                 dict(label='chair', score=.5, x1=.4, y1=.4, x2=.5, y2=.6)]),
             dict(frame=1, preprocessing='letterbox', detections=[
                 dict(label='person', score=.5, x1=.5, y1=.4, x2=.95, y2=.5),      # cut at right edge
                 dict(label='person', score=.5, x1=.2, y1=.3, x2=.7, y2=.7),       # large corner box
                 dict(label='person', score=.5, x1=.2, y1=.4, x2=.25, y2=.45)])]   # kept
    (tmp_path / 'regions.json').write_text(json.dumps(regions))
    (tmp_path / 'letterbox.jsonl').write_text('\n'.join(json.dumps(p) for p in preds) + '\n')
    per_image, stats = score.load_results(tmp_path)
    assert stats == dict(cut=1, corner_dropped_large=1, unscored_label=1, kept=2)
    assert len(per_image[0]['full']) == 1 and len(per_image[0]['corners']) == 1
    # archived evidence keeps the predictions gzipped
    import gzip
    (tmp_path / 'letterbox.jsonl.gz').write_bytes(gzip.compress((tmp_path / 'letterbox.jsonl').read_bytes()))
    (tmp_path / 'letterbox.jsonl').unlink()
    assert score.load_results(tmp_path)[1] == stats


def test_describe_port_bins_flat_colour_like_the_node():
    # Flat NV12: Y=200 (bin 6), U=64 (bin 2), V=160 (bin 5) -> uv bin 2*8+5=21
    y = np.full((720, 1280), 200, np.uint8)
    uv = np.zeros((360, 1280), np.uint8)
    uv[:, 0::2] = 64
    uv[:, 1::2] = 160
    hist = sot_to_replay.describe(y, uv, (0.1, 0.1, 0.2, 0.3))
    assert abs(hist[21] - 0.8) < 1e-9 and abs(hist[64 + 6] - 0.2) < 1e-9
    assert abs(sum(hist) - 1.0) < 1e-9
    assert sot_to_replay.describe(y, uv, (0.1, 0.1, 0.004, 0.004)) is None   # under 8 px


def test_sot_score_counts_loss_episodes_and_off_target_control():
    def out(seq, state, valid, box):
        return {'v': 2, 'sequence': seq, 'frame': {'width': 1000, 'height': 1000},
                'lock': {'state': state, 'control_valid': valid,
                         'box': None if box is None else {'x': box[0]*1000, 'y': box[1]*1000, 'w': box[2]*1000, 'h': box[3]*1000}}}
    target = dict(x=.4, y=.4, w=.2, h=.3, visibility=1.0)
    truth = [dict(sequence=s, capture_ms=s*100.0, target=target, others=[], dropped=False) for s in range(1, 8)]
    on, off = (.4, .4, .2, .3), (.0, .0, .2, .3)
    outs = [out(1, 'none', False, None), out(2, 'tracking', True, on), out(3, 'tracking', True, on),
            out(4, 'coasting', False, off), out(5, 'lost', False, None), out(6, 'tracking', True, on),
            out(7, 'tracking', True, off)]
    s = score_sot_replay.score(outs, truth, lock_sequence=2)
    assert s['frames_after_lock'] == 6 and s['on_target_rate'] == round(3/6, 4)
    assert s['loss_episodes'] == 2 and s['recovered_episodes'] == 1
    assert s['episodes'][0]['duration_ms'] == 200.0 and s['episodes'][0]['recovered']
    assert s['control_valid_off_target'] == 1


def test_sot_target_hit_compares_xyxy_detection_with_xywh_target():
    dets = [dict(label='person', score=.9, box=[100, 100, 130, 180])]
    assert sot_to_replay.target_hit(dets, [100, 100, 30, 80], .5) == .9          # same box, xywh
    assert sot_to_replay.target_hit(dets, [100, 100, 130, 180], .5) is None    # xyxy mistaken for xywh
    s = sot_to_replay.confidence_summary([None, .2, .7, .9])
    assert s == dict(frames=4, detected=3, conf_median=.7, conf_max=.9, frames_at_or_above_birth=2)


def test_oracle_roi_mirrors_search_planner_geometry():
    import prepare_visdrone_sot as sot
    r = sot.oracle_roi([648, 370, 34, 95], 1280, 720)          # 95 px target: 2.5x = 238 < minimum 640
    assert (r['w'], r['h'], r['full_frame']) == (640, 640, False)
    assert r['x'] == 344 and r['y'] == 80                       # centre (665,417) - 320, floored to even, clamped
    r = sot.oracle_roi([10, 10, 300, 300], 1280, 720)           # 2.5x = 750 > min(1280,720): full frame
    assert r['full_frame']
    r = sot.oracle_roi([1200, 600, 30, 60], 1280, 720)          # clamped into the frame
    assert (r['x'], r['y']) == (640, 80)


def test_roi_merge_mirrors_roi_assist():
    region = dict(source_w=1280, source_h=720, x=344, y=80, w=640, h=640, full_frame=False)
    full = [dict(label='person', score=.6, box=[648, 370, 682, 465])]
    same = dict(label='person', score=.9, box=[650, 372, 684, 467])     # duplicate of a full-view box
    new = dict(label='person', score=.7, box=[400, 200, 430, 280])      # new person inside the crop
    other = dict(label='car', score=.9, box=[400, 200, 460, 240])       # not the target class
    edge = dict(label='person', score=.7, box=[346, 300, 380, 380])     # touches the crop's left (interior) edge
    merged = sot_to_replay.roi_merge(full, [same, new, other, edge], 'person', region)
    assert merged == [same, new]                                          # the more confident crop box replaces
    weaker = dict(same, score=.5)
    assert sot_to_replay.roi_merge(full, [weaker], 'person', region) == full


def test_crop_nv12_matches_resize_nv12_crop_rounding():
    import embed_visdrone_sot as emb
    y = (np.arange(720*1280, dtype=np.uint32).reshape(720, 1280) % 251).astype(np.uint8)
    uv = np.full((360, 1280), 128, np.uint8)
    out = emb.crop_nv12(y, uv, (0.5, 0.5, 0.1, 0.2))
    assert len(out) == 128*256*3//2
    # box 0.5..0.6 x 0.5..0.7 -> x 640..768, y 360..504 (already even); a 128-wide crop
    # resized to 128 keeps every source column, so the first output pixel is y[360, 640]
    assert out[0] == y[360, 640]
    assert out[128*256] == 128 and out[128*256 + 1] == 128         # UV plane follows Y, interleaved


def test_embeddings_attach_by_frame_and_box():
    rows = [dict(frame=3, box=[10, 20, 30, 80], model='m', values=[0.0]*512)]
    dets = [dict(label='person', score=.9, box=[10, 20, 30, 80]), dict(label='person', score=.9, box=[0, 0, 5, 5])]
    attached = sot_to_replay.attach_embeddings(dets, 3, sot_to_replay.index_embeddings(rows))
    assert attached[0]['embedding'] == dict(model='m', values=[0.0]*512) and 'embedding' not in attached[1]
    assert sot_to_replay.attach_embeddings(dets, 4, sot_to_replay.index_embeddings(rows)) == dets


def test_target_label_is_the_detector_majority_on_the_annotated_box():
    per = {0: dict(full=[dict(label='car', score=.9, box=[100, 100, 160, 140]), dict(label='person', score=.3, box=[100, 100, 160, 140])], corners=[], roi=[]),
           1: dict(full=[dict(label='car', score=.8, box=[102, 100, 162, 140])], corners=[], roi=[])}
    targets = [dict(index=0, box=[100, 100, 60, 40]), dict(index=1, box=[102, 100, 60, 40])]
    assert sot_to_replay.target_label(per, targets) == 'car'
    assert sot_to_replay.target_label({}, targets) == 'person'
