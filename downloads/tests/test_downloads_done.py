# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_SMALL_COMFORTS_V1: the worker notes each finished download in a small file Omni watches.

/data/omni/downloads-done.txt (OMNI_DOWNLOADS_DONE_FILE overrides it) holds "job id<TAB>title" lines, newest last,
at most DONE_KEEP; Omni shows "Downloaded: <title>" once per id while the user is on another tab. Only completed,
non-demo jobs are noted; cancelled ones never; the file is written only when its folder exists.

Run: python3 -m unittest tests/test_downloads_done.py   (from the downloads folder)
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import worker  # noqa: E402


class DoneFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.done = self.root / 'omni' / 'downloads-done.txt'
        self.done.parent.mkdir()
        self.jobs = worker.Jobs(self.root / 'downloads', None, done_file=self.done)

    def tearDown(self):
        self.jobs.close(timeout=1)
        self.tmp.cleanup()

    def job(self, key, title='', demo=False, filepath=''):
        with self.jobs.lock:
            self.jobs.jobs[key] = dict(id=key, url='https://example.com/v', demo=demo, audio=False, state='downloading',
                                       progress=50, cancel=False, title=title, filepath=filepath, error='', note='')

    def lines(self):
        return self.done.read_text(encoding='utf-8').splitlines() if self.done.exists() else []

    def test_completed_job_is_noted(self):
        self.job('a1b2', title='My Video')
        self.jobs.update('a1b2', state='downloading', progress=90)
        self.assertEqual(self.lines(), [])
        self.jobs.update('a1b2', state='completed', progress=100, filepath='/x/My Video.mp4')
        self.assertEqual(self.lines(), ['a1b2\tMy Video'])
        self.assertFalse(self.done.with_name('downloads-done.txt.tmp').exists())

    def test_placeholder_title_uses_file_name(self):
        self.job('k1', title='Saving the file')
        self.jobs.update('k1', state='completed', filepath='/data/omni/downloads/Saved/report 2026.pdf')
        self.job('k2', title='Switching to JDownloader')
        self.jobs.update('k2', state='completed', filepath='')
        self.assertEqual(self.lines(), ['k1\treport 2026.pdf', 'k2\ta download'])

    def test_title_is_one_clean_line(self):
        self.job('k3', title='Bad\ttitle\nwith\rbreaks' + 'x' * 400)
        self.jobs.update('k3', state='completed')
        (line,) = self.lines()
        key, title = line.split('\t')
        self.assertEqual(key, 'k3')
        self.assertTrue(title.startswith('Bad title with breaks'))
        self.assertLessEqual(len(title), 200)

    def test_demo_failed_and_cancelled_jobs_are_not_noted(self):
        self.job('d', title='Demo', demo=True)
        self.jobs.update('d', state='completed')
        self.job('f', title='Failed')
        self.jobs.update('f', state='failed', error='nope')
        self.job('c', title='Cancelled')
        with self.jobs.lock:
            self.jobs.jobs['c']['cancel'] = True
        self.jobs.update('c', state='completed')
        self.assertEqual(self.jobs.jobs['c']['state'], 'cancelled')
        self.assertEqual(self.lines(), [])

    def test_keeps_the_newest_lines(self):
        for i in range(worker.DONE_KEEP + 3):
            self.job(f'j{i}', title=f'T{i}')
            self.jobs.update(f'j{i}', state='completed')
        lines = self.lines()
        self.assertEqual(len(lines), worker.DONE_KEEP)
        self.assertEqual(lines[0], 'j3\tT3')
        self.assertEqual(lines[-1], f'j{worker.DONE_KEEP + 2}\tT{worker.DONE_KEEP + 2}')

    def test_same_job_twice_is_one_line(self):
        self.job('r', title='Again')
        self.jobs.update('r', state='completed')
        self.jobs.update('r', state='completed')
        self.assertEqual(self.lines(), ['r\tAgain'])

    def test_no_folder_no_file_no_error(self):
        missing = self.root / 'no-such-dir' / 'downloads-done.txt'
        jobs = worker.Jobs(self.root / 'downloads2', None, done_file=missing)
        try:
            with jobs.lock:
                jobs.jobs['z'] = dict(id='z', demo=False, cancel=False, state='downloading', title='Z', filepath='')
            jobs.update('z', state='completed')
            self.assertEqual(jobs.jobs['z']['state'], 'completed')
            self.assertFalse(missing.parent.exists())
        finally:
            jobs.close(timeout=1)

    def test_disabled(self):
        jobs = worker.Jobs(self.root / 'downloads3', None, done_file=None)
        try:
            with jobs.lock:
                jobs.jobs['z'] = dict(id='z', demo=False, cancel=False, state='downloading', title='Z', filepath='')
            jobs.update('z', state='completed')
            self.assertEqual(self.lines(), [])
        finally:
            jobs.close(timeout=1)

    def test_default_path(self):
        self.assertTrue(str(worker.DONE_FILE).endswith('downloads-done.txt'))


if __name__ == '__main__':
    unittest.main()
