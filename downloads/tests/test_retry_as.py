# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_RETRY_AS_V1 (D05): a failed yt-dlp download retried as audio only or at 1080p, and POST /api/jobs/retry-as.

Run: python3 -m unittest tests/test_retry_as.py   (from the downloads folder; no network: the queue stays paused)
"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import worker  # noqa: E402


class RetryAs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dl-retry-as-')
        cls.server = worker.make_server(0, cls.tmp, Path(cls.tmp) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.server.jobs.set_paused(True)
        cls.jobs = cls.server.jobs

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def failed(self, **fields):
        """A real job, then marked failed (as the dispatcher would after an error)."""
        key = self.jobs.create('https://example.com/watch/%d' % len(self.jobs.jobs), False)
        with self.jobs.lock:
            if key in self.jobs.pending:
                self.jobs.pending.remove(key)
            self.jobs.jobs[key].update(state='failed', error='No engine could download this link.', **fields)
        return key

    def request(self, path, body, token=True):
        port = self.server.server_port
        headers = {'Content-Type': 'application/json', 'Host': '127.0.0.1:%d' % port}
        if token:
            headers['X-Omni-Token'] = self.server.token
        req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), data=json.dumps(body).encode(), headers=headers, method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_audio(self):
        key = self.failed(preset='best', format='bestvideo+bestaudio', quality_key='q', container='mkv')
        self.assertEqual(self.jobs.retry_as(key, 'audio'), 'queued')
        j = self.jobs.jobs[key]
        self.assertEqual((j['audio'], j['preset'], j['format'], j['quality_key'], j['container'], j['state'], j['retries']),
                         (True, 'audio-m4a', None, '', None, 'queued', 1))
        self.assertIn('Retry 1', j['note'])

    def test_1080p(self):
        key = self.failed(preset='best')
        self.jobs.retry_as(key, '1080p')
        j = self.jobs.jobs[key]
        self.assertEqual((j['audio'], j['preset'], j['state']), (False, '1080p', 'queued'))

    def test_refusals(self):
        for fields, how in (({'audio': True}, 'audio'), ({'preset': '1080p'}, '1080p'), ({'clip': [10, 20]}, 'audio'),
                            ({'direct': True}, 'audio'), ({'engine': 'jdownloader', 'engine_requested': 'jdownloader'}, 'audio'),
                            ({'demo': True}, '1080p')):
            key = self.failed(**fields)
            with self.assertRaises(ValueError, msg=str(fields)):
                self.jobs.retry_as(key, how)
            self.assertEqual(self.jobs.jobs[key]['state'], 'failed')
        key = self.failed()
        for how in ('720p', '', None, 5):
            with self.assertRaises(ValueError):
                self.jobs.retry_as(key, how)
        with self.jobs.lock:
            self.jobs.jobs[key]['state'] = 'completed'
        with self.assertRaises(ValueError):
            self.jobs.retry_as(key, 'audio')

    def test_route(self):
        key = self.failed(preset='best')
        self.assertEqual(self.request('/api/jobs/retry-as', {'id': key, 'how': 'audio'}, token=False)[0], 403)
        self.assertEqual(self.request('/api/jobs/retry-as', {'id': key, 'how': 'audio'}),
                         (200, {'ok': True, 'id': key, 'state': 'queued', 'how': 'audio'}))
        for body in ({'id': key}, {'how': 'audio'}, {'id': key, 'how': 'audio', 'x': 1}, {'id': 'nothex', 'how': 'audio'},
                     {'id': key, 'how': 'best'}):
            self.assertEqual(self.request('/api/jobs/retry-as', body)[0], 400, body)


if __name__ == '__main__':
    unittest.main()
