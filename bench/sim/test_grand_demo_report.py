import copy
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from grand_demo_report import summarize


class ReportTests(unittest.TestCase):
    def report(self,moving=True,change=0,origin=11):
        source=dict(age_ms=70,roundtrip_ms=120,output=dict(source_id='replay',stream_id='one',sequence=1))
        first=dict(source=source,following=True,flight='Hover / offboard',armed=True,
                   yaw=math.pi-.01,position_ned=[0,0,-2])
        second=copy.deepcopy(first);second['yaw']=-math.pi+.01 if change else first['yaw']
        last=dict(first,following=False,armed=False,flight='Landed / disarmed')
        wire=dict(kind='wire',allowed=True,moving=moving,host_ns=10,deadline_ns=12,origin_deadline_ns=origin)
        with patch('grand_demo_report.json_lines',side_effect=[[first,second,last],[wire]]):
            return summarize(Path('/unused'))

    def test_forwarding_without_response_is_not_visual_success(self):
        self.assertFalse(self.report()['visual_response_observed'])
        self.assertFalse(self.report(moving=False,change=1)['visual_response_observed'])

    def test_heading_wrap_not_full_turn_and_age_scopes_separate(self):
        r=self.report(change=1)
        self.assertAlmostEqual(r['actual_follow_heading_span_deg'],math.degrees(.02))
        self.assertEqual(r['source_age_field_ms']['median'],70)
        self.assertEqual(r['ingress_roundtrip_ms']['median'],120)

    def test_origin_deadline_required(self):
        self.assertFalse(self.report(origin=None)['transport_demo_pass'])


if __name__=='__main__':unittest.main()
