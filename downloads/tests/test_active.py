# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_PROGRESS_V1: GET /api/active, what Omni's top bar polls ("2 ↓ 45%") while downloads run.

Read-only and tiny: {"api_version": 1, "active": N, "percent": P}. Active = jobs not finished, not paused, not
pausing / cancelling; percent = the mean of their known progress (queued counts 0, inspecting has none), -1 when
none is known. Counts only (no titles, links or ids), no token, Host must be 127.0.0.1:<port> like every route.

Run: python3 -m unittest tests/test_active.py   (from the downloads folder)
"""
import http.client
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import worker  # noqa: E402


class Summary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jobs = worker.Jobs(Path(self.tmp.name) / 'downloads', None, done_file=None)

    def tearDown(self):
        self.jobs.close(timeout=1)
        self.tmp.cleanup()

    def put(self, key, state, progress):
        with self.jobs.lock:
            self.jobs.jobs[key] = dict(id=key, url='https://example.com/' + key, demo=False, state=state,
                                       progress=progress, title='Secret title ' + key, cancel=False)

    def test_empty(self):
        self.assertEqual(self.jobs.active_summary(), {'api_version': 1, 'active': 0, 'percent': -1})

    def test_mean_of_known_progress(self):
        self.put('a', 'downloading', 40)
        self.put('b', 'downloading', 51)
        self.assertEqual(self.jobs.active_summary(), {'api_version': 1, 'active': 2, 'percent': 45})

    def test_queued_counts_zero_extracting_unknown(self):
        self.put('a', 'downloading', 90)
        self.put('b', 'queued', 0)
        self.put('c', 'extracting', None)
        self.assertEqual(self.jobs.active_summary(), {'api_version': 1, 'active': 3, 'percent': 45})

    def test_only_unknown(self):
        self.put('c', 'extracting', None)
        self.assertEqual(self.jobs.active_summary()['percent'], -1)
        self.assertEqual(self.jobs.active_summary()['active'], 1)

    def test_finished_paused_and_stopping_jobs_do_not_count(self):
        for key, state in (('d', 'completed'), ('f', 'failed'), ('x', 'cancelled'), ('i', 'interrupted'),
                           ('p', 'paused'), ('q', 'pausing'), ('r', 'cancelling')):
            self.put(key, state, 70)
        self.put('live', 'processing', 100)
        self.assertEqual(self.jobs.active_summary(), {'api_version': 1, 'active': 1, 'percent': 100})

    def test_odd_progress_values(self):
        self.put('a', 'downloading', 250)      # clamped
        self.put('b', 'downloading', -5)       # clamped
        self.put('c', 'downloading', True)     # not a number here
        self.put('d', 'downloading', '50')     # not a number here
        self.put('e', 'downloading', 33.9)
        value = self.jobs.active_summary()
        self.assertEqual(value['active'], 5)
        self.assertEqual(value['percent'], int((100 + 0 + 33.9) / 3))

    def test_no_titles_links_or_ids(self):
        self.put('abc123', 'downloading', 10)
        text = json.dumps(self.jobs.active_summary())
        self.assertNotIn('Secret', text)
        self.assertNotIn('example.com', text)
        self.assertNotIn('abc123', text)


class Route(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dl-active-')
        cls.server = worker.make_server(0, cls.tmp, Path(cls.tmp) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.server.jobs.set_paused(True)   # demo jobs stay queued: nothing runs

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def get(self, path, host=None, method='GET'):
        port = self.server.server_port
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader('Host', host if host is not None else '127.0.0.1:%d' % port)
        conn.endheaders()
        response = conn.getresponse()
        body = response.read()
        headers = dict(response.getheaders())
        conn.close()
        return response.status, headers, body

    def test_listens_on_loopback_only(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')

    def test_shape_without_token(self):
        status, headers, body = self.get('/api/active')
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Type'), 'application/json')
        self.assertEqual(headers.get('Cache-Control'), 'no-store')
        value = json.loads(body)
        self.assertEqual(set(value), {'api_version', 'active', 'percent'})
        self.assertEqual(value['api_version'], 1)
        self.assertLess(len(body), 200)   # Omni's reader takes small fixed-size bodies only
        self.assertIn('Content-Length', headers)

    def test_counts_a_queued_job(self):
        jobs = self.server.jobs
        key = jobs.create('https://example.com/a.mp4', True)
        try:
            value = json.loads(self.get('/api/active')[2])
            self.assertGreaterEqual(value['active'], 1)
            self.assertEqual(value['percent'], 0)
        finally:
            jobs.cancel(key)
        value = json.loads(self.get('/api/active')[2])
        self.assertEqual(value['active'], 0)

    def test_foreign_host_refused(self):
        self.assertEqual(self.get('/api/active', host='evil.example:%d' % self.server.server_port)[0], 403)
        self.assertEqual(self.get('/api/active', host='localhost:%d' % self.server.server_port)[0], 403)

    def test_read_only(self):
        port = self.server.server_port
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        conn.request('POST', '/api/active', body=b'{}', headers={'Host': '127.0.0.1:%d' % port,
                                                                 'Content-Type': 'application/json',
                                                                 'X-Omni-Token': self.server.token})
        status = conn.getresponse().status
        conn.close()
        self.assertGreaterEqual(status, 400)

    def test_query_or_suffix_is_not_the_route(self):
        self.assertNotEqual(self.get('/api/active?x=1')[0], 200)
        self.assertNotEqual(self.get('/api/active/')[0], 200)


if __name__ == '__main__':
    unittest.main()
