"""Capture protocol correspondence/incomplete-prefix checks, without a board."""
import json
import os
import pathlib
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import socket
import threading

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[3]/'bench'))
from fresh_stream_capture import receive, capture_transport, spool_packets, require_capture_memory, diagnostic_headroom


def packet(meta,pixels=b''):
    raw=json.dumps(meta).encode()
    return struct.pack('!4sII',b'GRC1',len(raw),len(pixels))+raw+pixels


def frame():
    return dict(recording_id='test',type='frame',sample_index=0,input_w=2,input_h=2,
                pixel_format='NV12',packed_stride=2,frame=dict(sequence=10,capture_ms=1000),
                output=dict(sequence=10,capture_monotonic_ms=1000),
                source_id='camera',stream_id='process',clock_domain='boot')


class CaptureReceiverTests(unittest.TestCase):
    def run_bytes(self,data,output,reserve_bytes=0,spool=False):
        reader,writer=os.pipe()
        try:
            os.write(writer,data);os.close(writer);writer=-1
            with patch('fresh_stream_capture.memory_available_bytes',return_value=4*1024**3):
                return receive(reader,output,'test',1,reserve_bytes,spool)
        finally:
            os.close(reader)
            if writer>=0:os.close(writer)

    def test_exact_correspondence_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)
            footer=dict(type='end',recording_id='test',complete=True,sent=1)
            result=self.run_bytes(packet(frame(),b'abcdef')+packet(footer),path)
            self.assertTrue(result['complete'])
            self.assertEqual((path/'000000.nv12').read_bytes(),b'abcdef')
            self.assertEqual(len(json.loads((path/'000000.json').read_text())['nv12_sha256']),64)

    def test_storage_reserve_stops_before_writing_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)
            with patch('fresh_stream_capture.shutil.disk_usage') as usage:
                usage.return_value.free=1024
                with self.assertRaisesRegex(RuntimeError,'storage reserve'):
                    self.run_bytes(packet(frame(),b'abcdef'),path,reserve_bytes=2048)
            self.assertFalse(list(path.glob('*.nv12')))
            self.assertFalse((path/'end.json').exists())

    def test_spool_keeps_correspondence_and_propagates_errors(self):
        footer=dict(type='end',recording_id='test',complete=True,sent=1)
        for ending in [packet(footer),b'']:
            with tempfile.TemporaryDirectory() as directory:
                path=pathlib.Path(directory)
                data=packet(frame(),b'abcdef')+ending
                if ending:
                    result=self.run_bytes(data,path,spool=True)
                    self.assertTrue(result['complete'])
                else:
                    with self.assertRaises(EOFError):self.run_bytes(data,path,spool=True)
                self.assertEqual((path/'000000.nv12').read_bytes(),b'abcdef')

    def test_spool_rejects_invalid_order(self):
        with tempfile.TemporaryDirectory() as directory:
            meta=frame();meta['sample_index']=8
            with self.assertRaisesRegex(ValueError,'order mismatch'):
                self.run_bytes(packet(meta,b'abcdef'),pathlib.Path(directory),spool=True)

    def test_spool_has_a_frame_bound(self):
        with patch('fresh_stream_capture.memory_available_bytes',return_value=4*1024**3),\
             patch('fresh_stream_capture.read_packet',return_value=(frame(),b'abcdef',10,6)) as read:
            get=spool_packets(-1,1)
            self.assertEqual(read.call_count,2)
            self.assertEqual(get()[1],b'abcdef')
            with self.assertRaisesRegex(ValueError,'spool bound'):get()

    def test_spool_checks_memory_before_reading_and_during_capture(self):
        with patch('fresh_stream_capture.memory_available_bytes',return_value=0),\
             patch('fresh_stream_capture.read_packet') as read:
            with self.assertRaisesRegex(RuntimeError,'RAM reserve'):require_capture_memory(24)
            with self.assertRaises(RuntimeError):spool_packets(-1,1)
            read.assert_not_called()

    def test_cma_is_never_counted_as_python_capture_memory(self):
        # Same pressure/normal/missing/reversed cases as native diagnostic budget.
        self.assertEqual(diagnostic_headroom('MemAvailable: 1081344 kB\nCmaFree: 1038592 kB\n'),42752*1024)
        self.assertEqual(diagnostic_headroom('MemAvailable: 1400000 kB\nCmaFree: 1000000 kB\n'),400000*1024)
        self.assertEqual(diagnostic_headroom('MemAvailable: 1 kB\nCmaFree: 2 kB\n'),0)
        for text in ['MemAvailable: 1400000 kB\n','MemAvailable: huge kB\nCmaFree: 0 kB\n',
                     'MemAvailable: -1 kB\nCmaFree: 0 kB\n']:
            with self.assertRaises((ValueError,RuntimeError)):diagnostic_headroom(text)
        with patch('fresh_stream_capture.memory_available_bytes',return_value=42752*1024):
            with self.assertRaises(RuntimeError):require_capture_memory(1)
        with patch('fresh_stream_capture.memory_available_bytes',return_value=4*1024**3):
            with self.assertRaises(ValueError):require_capture_memory(25)
        with patch('fresh_stream_capture.memory_available_bytes',side_effect=[4*1024**3,0]),\
             patch('fresh_stream_capture.read_packet') as read:
            get=spool_packets(-1,1)
            with self.assertRaisesRegex(RuntimeError,'RAM reserve'):get()
            read.assert_not_called()

    def test_local_transport_captures_without_ssh(self):
        with socket.socket() as server, tempfile.TemporaryDirectory() as directory:
            server.bind(('127.0.0.1',0));server.listen(1);server.settimeout(3)
            requests=[];errors=[]
            def serve():
                try:
                    conn,_=server.accept()
                    with conn:
                        conn.settimeout(3);raw=b''
                        while not raw.endswith(b'\n'):raw+=conn.recv(4096)
                        requests.append(json.loads(raw))
                        conn.sendall(packet(frame(),b'abcdef')+packet(dict(type='end',recording_id='test',complete=True,sent=1)))
                except Exception as error:errors.append(error)
            worker=threading.Thread(target=serve);worker.start()
            try:
                with patch('fresh_stream_capture.subprocess.Popen',side_effect=AssertionError('SSH invoked')):
                    request=dict(recording_id='test',frames=1)
                    with capture_transport('unused',server.getsockname()[1],request,local=True) as fd:
                        result=receive(fd,pathlib.Path(directory),'test',1)
                self.assertTrue(result['complete'])
            finally:worker.join(timeout=5)
            self.assertFalse(worker.is_alive());self.assertFalse(errors)
            self.assertEqual(requests,[request])

    def test_exact_source_pair_saved_separately(self):
        meta=frame();meta['isp_timestamp_ns']=1_000_000_000
        meta['output']['frame']=dict(width=2,height=2)
        meta['source_image']=dict(width=2,height=2,pixel_format='NV12',packed_stride=2,
                                  byte_offset=6,byte_length=6,isp_timestamp_ns=1_000_000_000)
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory);footer=dict(type='end',recording_id='test',complete=True,sent=1)
            result=self.run_bytes(packet(meta,b'abcdefghijkl')+packet(footer),path)
            self.assertEqual(result['paired_frames'],1)
            self.assertEqual(result['pixel_bytes'],12)
            self.assertEqual((path/'000000.nv12').read_bytes(),b'abcdef')
            self.assertEqual((path/'000000.source.nv12').read_bytes(),b'ghijkl')
            self.assertEqual(len(json.loads((path/'000000.json').read_text())['source_image']['sha256']),64)

    def test_nearby_source_exposure_is_rejected(self):
        meta=frame();meta['isp_timestamp_ns']=1_000_000_000;meta['output']['frame']=dict(width=2,height=2)
        meta['source_image']=dict(width=2,height=2,pixel_format='NV12',packed_stride=2,
                                  byte_offset=6,byte_length=6,isp_timestamp_ns=1_000_000_001)
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)
            with self.assertRaisesRegex(ValueError,'exposure'):self.run_bytes(packet(meta,b'abcdefghijkl'),path)
            self.assertFalse(list(path.glob('*.nv12')))

    def test_incomplete_stream_retains_only_verified_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)
            with self.assertRaises(EOFError):self.run_bytes(packet(frame(),b'abcdef'),path)
            self.assertTrue((path/'000000.nv12').exists())
            self.assertFalse((path/'end.json').exists())

    def test_mismatched_image_observations_and_oversize_rejected(self):
        for data in (struct.pack('!4sII',b'GRC1',128*1024+1,0),
                     packet({**frame(),'output':dict(sequence=11,capture_monotonic_ms=1000)},b'abcdef'),
                     packet(frame(),b'abc')):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):self.run_bytes(data,pathlib.Path(directory))
                self.assertFalse(list(pathlib.Path(directory).glob('*.nv12')))


if __name__=='__main__':unittest.main()
