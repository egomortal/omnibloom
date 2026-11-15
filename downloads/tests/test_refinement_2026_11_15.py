# SPDX-License-Identifier: GPL-3.0-or-later
"""Refinement review 2026-11-15, Downloads worker: local fakes only, no outside network.

- a failed accept() no longer ends the shared egress guard (every later download failed until restart);
- a JDownloader fallback is checked against the job folder the Java bridge really writes to (every finished
  JD-fallback download was reported as failed).
"""
import errno
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import egress_guard  # noqa: E402


class FakeListen:
    def __init__(self, guard, errors):
        self.guard, self.errors, self.calls = guard, list(errors), 0

    def accept(self):
        self.calls += 1
        if self.errors:
            raise OSError(self.errors.pop(0), 'fake')
        self.guard._closed = True   # end the loop after the errors
        raise OSError(errno.EBADF, 'closed')


def bare_guard():
    guard = egress_guard.EgressGuard.__new__(egress_guard.EgressGuard)
    guard._closed = False
    return guard


class EgressAccept(unittest.TestCase):
    def test_a_failed_accept_does_not_end_the_guard(self):
        guard = bare_guard()
        guard._sock = FakeListen(guard, [errno.EMFILE, errno.ECONNABORTED])
        guard._accept()
        self.assertEqual(guard._sock.calls, 3)   # kept accepting after both failures

    def test_a_broken_socket_ends_it_and_a_new_guard_is_made(self):
        guard = bare_guard()
        guard._sock = FakeListen(guard, [errno.EBADF])
        guard._accept()
        self.assertTrue(guard._closed)   # shared_guard() then starts a fresh one
        self.assertEqual(guard._sock.calls, 1)


class JdFallbackFolder(unittest.TestCase):
    def test_jdownloader_fallback_uses_the_job_folder(self):
        import worker
        jobs = worker.Jobs.__new__(worker.Jobs)
        seen = {}
        jobs.update = lambda key, **values: None
        jobs.cancelled = lambda key: False
        jobs.jd_adapter = type('JD', (), {'poisoned': False})()

        def ytdlp(key, job, target):
            seen['ytdlp'] = target
            raise worker.EngineUnavailable('no')

        def jd(key, job, target):
            seen['jdownloader'] = target
            return dict(filepath=str(target / 'f.bin'), via='JDownloader')
        jobs._run_ytdlp, jobs._run_jdownloader = ytdlp, jd
        folder = Path(tempfile.mkdtemp()) / 'job1'
        jobs._route('job1', dict(engine='ytdlp', audio=False, auto_fallback=True), folder)
        self.assertEqual(seen['ytdlp'], folder)
        self.assertEqual(seen['jdownloader'], folder)   # was folder/via-jdownloader: the bridge writes to folder


if __name__ == '__main__':
    unittest.main()
