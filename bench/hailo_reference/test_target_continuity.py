import unittest
from check_target_continuity import check


def row(index,x=10,valid=True,track=8):
    return dict(source_index=index,output=dict(lock=dict(control_valid=valid,
                box=dict(x=x,y=20,w=20,h=30),track_id=track,reason='observed')))


class TargetContinuityTests(unittest.TestCase):
    def setUp(self):
        self.truth=dict(targets=[dict(index=i,box=[10,20,20,30]) for i in range(5)])

    def test_correct_target_passes_narrow_gate(self):
        self.assertTrue(check([row(0),row(1)],self.truth,0)['passed'])

    def test_same_id_jump_and_later_rebind_both_fail(self):
        result=check([row(0),row(1,valid=False),row(2,x=100),row(3,x=150,track=141)],self.truth,0)
        self.assertFalse(result['passed'])
        self.assertEqual(result['zero_overlap_control_frames'],2)
        self.assertEqual([v['track_id'] for v in result['violations']],[8,141])

    def test_invalid_predictions_are_not_authorized_observations(self):
        result=check([row(0),row(1,x=100,valid=False)],self.truth,0)
        self.assertTrue(result['passed'])

    def test_no_acquisition_is_not_a_vacuous_pass(self):
        result=check([row(0,valid=False)],self.truth,0)
        self.assertFalse(result['passed'])
        self.assertTrue(result['no_demonstrated_target_tracking'])

    def test_missing_truth_and_reorder_fail(self):
        for rows in ([row(9)],[row(1),row(0)]):
            with self.assertRaises(ValueError):check(rows,self.truth,0)

    def test_malformed_valid_geometry_cannot_hide_a_failure(self):
        for bad in (row(1,x=float('nan')),row(1,x=float('inf')),row(1,valid='true')):
            with self.assertRaises(ValueError):check([row(0),bad],self.truth,0)


if __name__=='__main__':unittest.main()
