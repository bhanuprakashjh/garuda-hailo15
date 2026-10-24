import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'bench'))
from analyze_capture_schedule import analyze


def record(index, passes, reason='observed'):
    return dict(sample_index=index, recording_id='r', source_id='s', stream_id='v', clock_domain='boot',
                frame=dict(sequence=index+1, capture_ms=1000+index*100),
                output=dict(sequence=index+1, capture_monotonic_ms=1000+index*100, lock=dict(reason=reason)),
                detection_tiles=dict(sequence=index+1, detector_passes_this_frame=passes,
                                     processing_wall_ms=passes*25, corner_wall_ms=max(0,passes-2)*25,
                                     capture_to_update_ms=passes*25+30, schedule_reason='fixture'))


class CaptureScheduleTests(unittest.TestCase):
    def test_same_frame_cost_and_next_interval_are_separate(self):
        result = analyze([record(0,1,'low_confidence'), record(1,6), record(2,2)])
        self.assertEqual(result['by_detector_passes']['6']['processing_wall_ms']['median'],150)
        self.assertEqual(result['by_detector_passes']['6']['next_source_interval_ms']['median'],100)
        self.assertEqual(result['broad_search_after_unobserved'][0]['sample_index'],1)
        self.assertFalse(result['tracking_accuracy_qualified'])
        self.assertFalse(result['counterfactual_speed_measured'])

    def test_last_frame_has_no_invented_next_interval(self):
        result=analyze([record(0,2)])
        self.assertNotIn('next_source_interval_ms',result['by_detector_passes']['2'])
        self.assertIsNone(result['source_interval_ms']['max'])

    def test_bad_provenance_and_timing_fail_closed(self):
        base=[record(0,1),record(1,6)]
        for key, value in [('sequence',99),('processing_wall_ms',float('nan')),
                           ('corner_wall_ms',-1),('detector_passes_this_frame',True)]:
            with self.subTest(key=key):
                rows=copy.deepcopy(base);rows[1]['detection_tiles'][key]=value
                with self.assertRaises(ValueError): analyze(rows)
        rows=copy.deepcopy(base);rows[1]['stream_id']='other'
        with self.assertRaises(ValueError): analyze(rows)
        rows=copy.deepcopy(base);rows[1]['frame']['sequence']=3
        rows[1]['output']['sequence']=3;rows[1]['detection_tiles']['sequence']=3
        with self.assertRaises(ValueError): analyze(rows)
        with self.assertRaises(ValueError): analyze([])
