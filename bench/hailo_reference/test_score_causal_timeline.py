import unittest
from score_causal_timeline import timeline_score


def sample(index,age=50,valid=True,x=10):
    return dict(source_index=index,age_ms=age,
                output=dict(lock=dict(control_valid=valid,box=dict(x=x,y=20,w=30,h=80))))


class TimelineTests(unittest.TestCase):
    def score(self,rows):
        return timeline_score(rows,dict(targets=[dict(index=i,box=[10,20,30,80]) for i in range(8)]),
                              dict(frames=8,select_frame=0,period_ms=50,source_age_ms=50))

    def test_skips_and_expiry_are_not_hidden(self):
        r=self.score([sample(0)])
        self.assertEqual(r['counts'],dict(no_publication=1,eligible_on_target=3,expired=4))
        self.assertEqual(r['source_slots'],8)
        self.assertEqual(r['eligible_on_target_fraction'],3/8)
        self.assertEqual(r['longest_without_on_target_ms'],200)

    def test_future_output_cannot_score_earlier_frame(self):
        r=self.score([sample(0,age=200)])
        self.assertNotIn('eligible_on_target',r['counts'])
        self.assertEqual(r['counts']['no_publication'],4)

    def test_time_integral_avoids_release_sampling_alias(self):
        r=self.score([sample(0,age=175)])
        self.assertNotIn('eligible_on_target',r['counts'])
        self.assertEqual(r['time_weighted']['durations_ms']['eligible_on_target'],25)
        self.assertEqual(sum(r['time_weighted']['durations_ms'].values()),400)

    def test_invalid_or_off_target_not_success(self):
        r=self.score([sample(0,valid=False),sample(2,x=100)])
        self.assertEqual(r['counts']['not_control_valid'],2)
        self.assertEqual(r['counts']['eligible_off_target'],3)
        self.assertEqual(r['eligible_on_target_fraction'],0)

    def test_duplicate_or_nonfinite_input_rejected(self):
        for rows in ([sample(0),sample(0)],[sample(2),sample(1)],[sample(0,float('nan'))]):
            with self.assertRaises(ValueError):self.score(rows)

    def test_empty_outputs_count_all_slots(self):
        self.assertEqual(self.score([])['counts'],dict(no_publication=8))


if __name__=='__main__':unittest.main()
