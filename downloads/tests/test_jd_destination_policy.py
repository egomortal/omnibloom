"""Audit JD-03 regression tests (GPL-3.0-or-later), local fakes only.

The Java bridge is replaced by an in-process fake (no Java, no sockets, no
outside network). Before the fix the adapter handed any syntactically valid
link to JDownloader and accepted a finished file reached through a symlink;
after it, JDownloader is held back until the bridge reports the reviewed egress
policy, private/local links never reach it, and outputs must be plain files
inside the job folder.
"""
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import jd_adapter  # noqa: E402
import probe  # noqa: E402

POLICY = getattr(jd_adapter, 'EGRESS_POLICY', 'omni-public-only-v1')


def resolver(host, port):
    if host == 'files.example':
        return (socket.AF_INET, '93.184.215.14', port)
    raise probe.Refused('Local or private address')


class FakeBridge(jd_adapter.JDownloaderAdapter):
    def __init__(self, health, output):
        super().__init__(dict(host='127.0.0.1', port=9, token='a' * 64))
        self.resolver = resolver
        self.health, self.output, self.calls = health, output, []

    def call(self, action, **parameters):
        self.calls.append(action)
        if action == 'health':
            return dict(ok=True, ready=True, status='ready', **self.health)
        if action == 'status':
            return dict(ok=True, state='completed', progress=100, title='t', filepath=self.output)
        return dict(ok=True)


class Policy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / 'job'
        self.dest.mkdir()
        (self.dest / 'video.mp4').write_bytes(b'x')

    def tearDown(self):
        self.tmp.cleanup()

    def run_job(self, bridge, url='https://files.example/v'):
        return bridge.download('0123456789abcdef', url, self.dest, lambda c: None, lambda: False)

    def test_held_back_without_reviewed_egress_policy(self):
        bridge = FakeBridge({}, str(self.dest / 'video.mp4'))
        self.assertFalse(bridge.capabilities()['jdownloader'])
        with self.assertRaises(Exception):
            self.run_job(bridge)
        self.assertNotIn('submit', bridge.calls)

    def test_private_link_never_submitted(self):
        bridge = FakeBridge({'egress_policy': POLICY}, str(self.dest / 'video.mp4'))
        for url in ('http://192.168.1.1/router', 'http://127.0.0.1:12800/', 'http://ps5.local/x'):
            with self.assertRaises(ValueError):
                self.run_job(bridge, url)
        self.assertNotIn('submit', bridge.calls)

    def test_symlinked_output_refused(self):
        os.symlink(self.dest / 'video.mp4', self.dest / 'link.mp4')
        bridge = FakeBridge({'egress_policy': POLICY}, str(self.dest / 'link.mp4'))
        with self.assertRaises(ValueError):
            self.run_job(bridge)

    def test_symlinked_folder_inside_job_refused(self):
        (self.dest / 'real').mkdir()
        (self.dest / 'real' / 'a.mp4').write_bytes(b'x')
        os.symlink(self.dest / 'real', self.dest / 'via')
        bridge = FakeBridge({'egress_policy': POLICY}, str(self.dest / 'via' / 'a.mp4'))
        with self.assertRaises(ValueError):
            self.run_job(bridge)

    def test_escapes_refused(self):
        outside = Path(self.tmp.name) / 'outside.mp4'
        outside.write_bytes(b'x')
        for value in (str(outside), str(self.dest / '..' / 'outside.mp4'), '', str(self.dest)):
            bridge = FakeBridge({'egress_policy': POLICY}, value)
            with self.assertRaises(ValueError, msg=value):
                self.run_job(bridge)

    def test_owned_file_accepted_and_released(self):
        bridge = FakeBridge({'egress_policy': POLICY}, str(self.dest / 'video.mp4'))
        result = self.run_job(bridge)
        self.assertEqual(Path(result['filepath']), (self.dest / 'video.mp4').resolve())
        self.assertIn('submit', bridge.calls)
        self.assertIn('release', bridge.calls)
        self.assertFalse(bridge.poisoned)


if __name__ == '__main__':
    unittest.main()
