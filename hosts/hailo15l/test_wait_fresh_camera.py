import unittest
from wait_fresh_camera import wait_ready


def row(sequence,stream='one',age=100):
    return dict(source_id='hailo15l.imx678',stream_id=stream,sequence=sequence,
                frame=dict(width=1280,height=720),timestamp_valid=True,age_ms=age)


class ReadyTests(unittest.TestCase):
    def run_rows(self,rows):
        timer=[0.];it=iter(rows);last=[rows[-1]]
        def fetch():
            last[0]=next(it,last[0]);return last[0]
        def sleep(n):timer[0]+=n
        return wait_ready(fetch,timeout=1,clock=lambda:timer[0],sleep=sleep)

    def test_advancing_same_stream_required(self):
        self.assertEqual(self.run_rows([row(1),row(2)])['sequence'],2)
        for rows in ([None],[dict(error='no snapshot yet')],[row(1)],[row(1),row(2,age=2000)],
                     [row(1),row(2,stream='different')],[row(1),row(2,age=float('nan'))]):
            with self.assertRaises(TimeoutError):self.run_rows(rows)

    def test_producer_restart_must_advance_again(self):
        self.assertEqual(self.run_rows([row(100),row(1,'new'),row(2,'new')])['stream_id'],'new')


if __name__=='__main__':unittest.main()
