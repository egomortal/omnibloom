# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_QUEUE_ORDER_V1 (D04): queue reorder / "start next".

Ordering, persistence (with the old FIFO history format still loading), races with the dispatcher, validation and
the token-protected POST /api/queue/move route. No network: jobs run through a stand-in _run that finishes at once.

Run: python -m unittest tests/test_queue_order.py   (from the downloads folder)
"""
import json
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import history  # noqa: E402
import worker  # noqa: E402


def wait_for(predicate, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('timed out')


class FastJobs(worker.Jobs):
    """Records the order jobs start in and finishes each at once."""

    def __init__(self, *args, **kwargs):
        self.started = []
        super().__init__(*args, **kwargs)

    def _run(self, key):
        self.started.append(key)
        self.update(key, state='completed', title='done')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='dl-queue-'))
        self.history = self.tmp / 'history.json'
        self.jobs = FastJobs(self.tmp, str(self.history), done_file=None)
        self.jobs.set_paused(True)
        self.others = []

    def tearDown(self):
        for jobs in [self.jobs] + self.others:
            jobs.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, n):
        return [self.jobs.create('https://example.com/%d.mp4' % i, True) for i in range(n)]

    def file(self):
        return json.loads(self.history.read_text())


class Ordering(Base):
    def test_front_end_up_down_and_index(self):
        a, b, c, d = self.add(4)
        self.assertEqual(self.jobs.move(d, 'front'), [d, a, b, c])      # start next
        self.assertEqual(self.jobs.move(a, 'end'), [d, b, c, a])
        self.assertEqual(self.jobs.move(c, 'up'), [d, c, b, a])
        self.assertEqual(self.jobs.move(d, 'down'), [c, d, b, a])
        self.assertEqual(self.jobs.move(a, 1), [c, a, d, b])
        self.assertEqual(self.jobs.move(a, 1), [c, a, d, b])            # same place: no change
        self.jobs.set_paused(False)
        wait_for(lambda: len(self.jobs.started) == 4)
        self.assertEqual(self.jobs.started, [c, a, d, b])

    def test_snapshot_reports_queue_position(self):
        a, b, c = self.add(3)
        self.jobs.move(c, 'front')
        places = {j['id']: j.get('queue_position') for j in self.jobs.snapshot()}
        self.assertEqual(places, {c: 1, a: 2, b: 3})
        self.jobs.pause(a)
        places = {j['id']: j.get('queue_position') for j in self.jobs.snapshot()}
        self.assertEqual(places, {c: 1, a: None, b: 2})

    def test_cancel_and_pause_keep_the_rest_in_order(self):
        a, b, c, d = self.add(4)
        self.jobs.move(d, 'front')
        self.jobs.cancel(a)
        self.jobs.pause(b)
        self.assertEqual(list(self.jobs.pending), [d, c])
        self.jobs.resume(b)                                            # a resumed job joins the end, as before
        self.assertEqual(list(self.jobs.pending), [d, c, b])


class Validation(Base):
    def test_rules(self):
        a, b = self.add(2)
        for bad in ('x', 'A' * 16, 7, None):
            with self.assertRaises(ValueError):
                self.jobs.move(bad, 'front')
        with self.assertRaises(ValueError) as ctx:
            self.jobs.move('0' * 16, 'front')
        self.assertNotIsInstance(ctx.exception, worker.QueueConflict)
        for bad in ('top', '', None, True, False, 1.0, '1', [0]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.jobs.move(a, bad)
        for bad in (-1, 2, 99):
            with self.assertRaises(ValueError) as ctx:
                self.jobs.move(a, bad)
            self.assertNotIsInstance(ctx.exception, worker.QueueConflict)
            self.assertIn('0 to 1', str(ctx.exception))
        with self.assertRaises(ValueError):
            self.jobs.move(a, 'up')                                    # already first
        with self.assertRaises(ValueError):
            self.jobs.move(b, 'down')                                  # already last
        self.assertEqual(list(self.jobs.pending), [a, b])

    def test_paused_finished_and_running_jobs_conflict(self):
        a, b = self.add(2)
        self.jobs.pause(a)
        with self.assertRaises(worker.QueueConflict):
            self.jobs.move(a, 'front')
        self.jobs.cancel(a)
        with self.assertRaises(worker.QueueConflict):
            self.jobs.move(a, 'end')
        gate, release = threading.Event(), threading.Event()

        def hold(key):
            gate.set()
            release.wait(5)
            self.jobs.update(key, state='completed')
        self.jobs._run = hold
        self.jobs.set_paused(False)
        self.assertTrue(gate.wait(5))
        with self.assertRaises(worker.QueueConflict):
            self.jobs.move(b, 'front')                                 # running: not in the queue any more
        release.set()


class Races(Base):
    def test_run_returns_when_its_job_was_moved_back(self):
        a, b = self.add(2)
        self.jobs.move(b, 'front')
        # The dispatcher read pending[0] (a), released the lock, then the user moved b in front: run(a) must give
        # the turn back instead of waiting for ever (the dispatcher is the only thread that would start b).
        done = threading.Event()
        threading.Thread(target=lambda: (self.jobs.run(a), done.set()), daemon=True).start()
        self.assertTrue(done.wait(3), 'run() waited on a job that is no longer first')
        self.assertEqual(self.jobs.started, [])
        self.assertEqual(list(self.jobs.pending), [b, a])
        self.jobs.set_paused(False)
        wait_for(lambda: len(self.jobs.started) == 2)
        self.assertEqual(self.jobs.started, [b, a])

    def test_moves_while_the_dispatcher_runs_never_lose_or_repeat_a_job(self):
        for _round in range(5):
            keys = self.add(8)
            stop = threading.Event()
            errors = []

            def shuffle(keys=keys, stop=stop, errors=errors, seed=_round):
                rnd = random.Random(seed)
                while not stop.is_set():
                    key = rnd.choice(keys)
                    try:
                        self.jobs.move(key, rnd.choice(['front', 'end', 'up', 'down', 0]))
                    except worker.QueueConflict:
                        pass                                           # it started meanwhile
                    except ValueError as error:
                        if 'already' not in str(error):
                            errors.append(error)
            mover = threading.Thread(target=shuffle, daemon=True)
            mover.start()
            self.jobs.set_paused(False)
            wait_for(lambda keys=keys: all(self.jobs.jobs[k]['state'] == 'completed' for k in keys))
            stop.set()
            mover.join(5)
            self.assertEqual(errors, [])
            self.assertEqual(sorted(self.jobs.started), sorted(keys))  # each ran exactly once
            self.assertEqual(list(self.jobs.pending), [])
            self.jobs.started.clear()
            self.jobs.set_paused(True)

    def test_order_seen_at_unpause_is_the_run_order(self):
        keys = self.add(6)
        rnd = random.Random(4)
        for _ in range(40):
            self.jobs.move(rnd.choice(keys), rnd.choice(['front', 'end', 2]))
        expected = list(self.jobs.pending)
        self.jobs.set_paused(False)
        wait_for(lambda: len(self.jobs.started) == 6)
        self.assertEqual(self.jobs.started, expected)


class Persistence(Base):
    def restart(self):
        """As if the worker died (no close): load a copy of the history in a fresh worker."""
        folder = Path(tempfile.mkdtemp(prefix='dl-queue-restart-', dir=self.tmp))
        shutil.copy(self.history, folder / 'history.json')
        jobs = FastJobs(folder, str(folder / 'history.json'), done_file=None)
        jobs.set_paused(True)
        self.others.append(jobs)
        return jobs, folder / 'history.json'

    def test_move_is_saved_and_survives_a_restart(self):
        a, b, c, d = self.add(4)
        self.jobs.move(d, 'front')
        self.jobs.move(a, 'end')
        self.assertEqual(self.file()['queue'], [d, b, c, a])
        self.assertEqual(self.file()['version'], 1)
        again, path = self.restart()
        self.assertEqual(again.history.queue, [d, b, c, a])
        self.assertTrue(all(again.jobs[k]['state'] == 'interrupted' for k in (a, b, c, d)))
        for key in (a, c, b, d):                                       # resumed in any order...
            again.resume(key)
        self.assertEqual(list(again.pending), [d, b, c, a])             # ...they take their saved places
        again.set_paused(False)
        wait_for(lambda: len(again.started) == 4)
        self.assertEqual(again.started, [d, b, c, a])

    def test_saved_order_is_kept_across_a_second_restart_before_resuming(self):
        a, b, c = self.add(3)
        self.jobs.move(c, 'front')
        again, path = self.restart()
        again.resume(b)                                                # a save with only b resumed
        data = json.loads(path.read_text())
        self.assertEqual(data['queue'], [b, c, a])
        folder = path.parent
        third = FastJobs(folder, str(path), done_file=None)
        self.others.append(third)
        third.set_paused(True)
        self.assertEqual(third.history.queue, [b, c, a])

    def test_fresh_job_and_resumed_jobs(self):
        a, b, c = self.add(3)
        self.jobs.move(c, 'front')                                     # saved order c, a, b
        again, _ = self.restart()
        again.resume(b)
        fresh = again.create('https://example.com/new.mp4', True)
        again.resume(c)
        again.resume(a)
        self.assertEqual(list(again.pending), [c, a, b, fresh])

    def test_old_fifo_history_without_queue_still_loads(self):
        records = [dict(id=k * 16, state='queued', title='t', url='https://example.com/%s.mp4' % k) for k in 'abc']
        self.history.write_text(json.dumps({'version': 1, 'jobs': records}))
        old = FastJobs(self.tmp, str(self.history), done_file=None)
        self.others.append(old)
        old.set_paused(True)
        self.assertEqual(old.history.queue, [])
        for k in 'cab':
            old.resume(k * 16)
        self.assertEqual(list(old.pending), ['c' * 16, 'a' * 16, 'b' * 16])   # FIFO by resume, as before
        self.assertEqual(json.loads(self.history.read_text())['queue'], ['c' * 16, 'a' * 16, 'b' * 16])

    def test_bad_queue_values_are_ignored(self):
        records = [dict(id=k * 16, state='queued', title='t', url='https://example.com/%s.mp4' % k) for k in 'abc']
        records.append(dict(id='d' * 16, state='completed', title='t'))
        records.append(dict(id='e' * 16, state='queued', title='old record without a link'))
        for queue, expected in (('abc', []), ({'a': 1}, []), (7, []),
                                ([None, 5, 'zz', 'f' * 16, 'd' * 16, 'e' * 16, 'b' * 16, 'b' * 16, 'a' * 16],
                                 ['b' * 16, 'a' * 16])):
            self.history.write_text(json.dumps({'version': 1, 'jobs': records, 'queue': queue}))
            loaded = history.History(self.history)
            jobs = loaded.load()
            self.assertEqual(loaded.error, '')
            self.assertEqual(len(jobs), 5)
            self.assertEqual(loaded.queue, expected, repr(queue))

    def test_plain_history_writes_no_queue_key(self):
        plain = history.History(self.tmp / 'plain.json')
        plain.save({'a' * 16: dict(id='a' * 16, state='completed', title='t')})
        data = json.loads((self.tmp / 'plain.json').read_text())
        self.assertEqual(set(data), {'version', 'jobs'})


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dl-queue-api-')
        cls.server = worker.make_server(0, cls.tmp, Path(cls.tmp) / 'history.json')
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.server.jobs.set_paused(True)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, path, body=None, token=True):
        port = self.server.server_port
        headers = {'Content-Type': 'application/json', 'Host': '127.0.0.1:%d' % port}
        if token:
            headers['X-Omni-Token'] = self.server.token
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), data=data, headers=headers,
                                         method='POST' if body is not None else 'GET')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_move_endpoint(self):
        keys = [self.request('/api/jobs', {'url': 'https://example.com/%d.mp4' % n, 'demo': True})[1]['id'] for n in range(3)]
        a, b, c = keys
        try:
            self.assertEqual(self.request('/api/queue/move', {'id': c, 'to': 'front'}),
                             (200, {'ok': True, 'id': c, 'queue': [c, a, b]}))
            self.assertEqual(self.request('/api/queue/move', {'id': c, 'to': 'end'}, token=False)[0], 403)
            self.assertEqual(self.request('/api/queue/move', {'id': c, 'to': 2})[1]['queue'], [a, b, c])
            for body in ({'id': c}, {'to': 'end'}, {'id': c, 'to': 'end', 'x': 1}, {'id': 'nothex', 'to': 'end'},
                         {'id': '0' * 16, 'to': 'end'}, {'id': c, 'to': 3}, {'id': c, 'to': -1}, {'id': c, 'to': 'top'},
                         {'id': c, 'to': True}, {'id': a, 'to': 'up'}):
                self.assertEqual(self.request('/api/queue/move', body)[0], 400, body)
            self.request('/api/jobs/pause', {'id': b})
            code, value = self.request('/api/queue/move', {'id': b, 'to': 'front'})
            self.assertEqual(code, 409)
            self.assertIn('not in the queue', value['error'])
            status = self.request('/api/status')[1]
            places = {j['id']: j.get('queue_position') for j in status['jobs']}
            self.assertEqual((places[a], places[b], places[c]), (1, None, 2))
            self.assertEqual(self.request('/api/queue', {'paused': True}), (200, {'queue_paused': True}))  # unchanged route
        finally:
            for key in keys:
                self.server.jobs.cancel(key)


if __name__ == '__main__':
    unittest.main()
