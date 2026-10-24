import json
from pathlib import Path
import tempfile
import unittest

from resolution_campaign import predictions, detections
from score_4k_tiles import map_box
from score_controlled_yolo11 import exact_rgb


class ResolutionTests(unittest.TestCase):
    def test_rectangular_nv12_conversion(self):
        raw=bytes([17])*(1024*576)+bytes([128])*(1024*576//2)
        rgb=exact_rgb(raw,1024,576)
        self.assertEqual(rgb.shape,(576,1024,3))
        self.assertTrue((rgb==17).all())
        with self.assertRaises(ValueError):exact_rgb(raw)
        with self.assertRaises(ValueError):exact_rgb(raw,1023,576)

    def test_fullview_coordinate_parity(self):
        r=dict(x=0,y=0,w=1280,h=720,source_w=1280,source_h=720)
        a=map_box(r,dict(x1=.4,x2=.5,y1=(140+.2*360)/640,y2=(140+.4*360)/640))
        b=map_box(dict(r,network_w=1024,network_h=576),dict(x1=.4,x2=.5,y1=.2,y2=.4))
        for x,y in zip(a,b):self.assertAlmostEqual(x,y)

    def test_corner_rectangular_mapping(self):
        r=dict(x=512,y=288,w=768,h=432,network_w=1024,network_h=576)
        self.assertEqual(map_box(r,dict(x1=0,y1=0,x2=1,y2=1)),[512,288,1280,720])

    def test_fixed_boundary_not_relative_candidate(self):
        r=dict(x=0,y=0,w=1280,h=720,source_w=1280,source_h=720,network_w=1024,network_h=576,method='full')
        d=dict(class_id=67,score=.9,x1=.4,y1=.4,x2=.5,y2=.5,fixed_cut=True,relative_cut=False)
        self.assertEqual(detections(r,dict(pre_filter=[d]),67),[])
        d['fixed_cut']=False
        self.assertEqual(len(detections(r,dict(pre_filter=[d]),67)),1)
        self.assertEqual(detections(r,dict(pre_filter=[d]),0),[])

    def test_actual_shape_and_order_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            (out/'phone-regions.json').write_text('[{}]')
            path=out/'phone-1024.jsonl'
            for prediction in (dict(frame=0,network_w=640,network_h=640),dict(frame=1,network_w=1024,network_h=576)):
                path.write_text(json.dumps(prediction)+'\n')
                with self.assertRaises(ValueError):list(predictions(out,'phone',1024))
            path.write_text(json.dumps(dict(frame=0,network_w=1024,network_h=576))+'\n')
            self.assertEqual(list(predictions(out,'phone',1024))[0][0]['network_h'],576)
            path.write_text('')
            with self.assertRaises(ValueError):list(predictions(out,'phone',1024))


if __name__=='__main__':unittest.main()
