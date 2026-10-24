import json
from pathlib import Path
import tempfile
import unittest

from recorded_input_campaign import layouts
from score_recorded_input import load, merge, phones


class RecordedInputTests(unittest.TestCase):
    def test_exact_native_field_of_view_alignment(self):
        for native, small in zip(layouts(3840,2160), layouts(1280,720)):
            self.assertEqual(native[0], small[0])
            self.assertEqual(tuple(v//3 for v in native[1:5]), small[1:5])
            self.assertTrue(all(v%6==0 for v in native[1:5]))

    def fixture(self):
        r=dict(source_w=1280,source_h=720,x=0,y=288,w=768,h=432,full_frame=False,method='corner2')
        d=dict(class_id=67,score=.3,x1=.6,x2=.67,y1=.24,y2=.34,fixed_cut=True,relative_cut=False)
        return r,d

    def test_candidate_changes_only_boundary_gate(self):
        r,d=self.fixture();p=dict(pre_filter=[d])
        self.assertEqual(phones(r,p,'fixed'),[])
        self.assertEqual(len(phones(r,p,'relative')),1)
        d['score']=.14
        self.assertEqual(phones(r,p,'relative'),[])
        d['score']=.3;d['relative_cut']=True
        self.assertEqual(phones(r,p,'relative'),[])

    def test_roi_policy_not_relaxed(self):
        r,d=self.fixture();r['method']='recorded_roi';d['y1']=140/640
        for policy in ('fixed','relative'):
            self.assertEqual(phones(r,dict(pre_filter=[d]),policy),[])

    def test_merge_preserves_same_tile_and_deduplicates_cross_tile(self):
        a=dict(box=[1,1,10,10],score=.8,region='corner0')
        self.assertEqual(len(merge([a,dict(a,score=.7)])),2)
        self.assertEqual(len(merge([a,dict(a,score=.7,region='full')])),1)

    def test_incomplete_or_reordered_results_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'test-regions.json').write_text(json.dumps([{}]))
            for data in ('',json.dumps(dict(frame=1))+'\n'):
                (p/'test.jsonl').write_text(data)
                with self.assertRaises(ValueError):load(p,'test','test')


if __name__=='__main__':unittest.main()
