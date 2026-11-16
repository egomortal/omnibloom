# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_SAVE_V1 (Downloads 0.5.4): file type, where to save, live byte counts, free-space check.
Local fakes only: no network, no real USB drive (mounts are simulated)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import save_places  # noqa: E402
import worker  # noqa: E402


class Names(unittest.TestCase):
    def test_plain_names_pass(self):
        for name in ('Music', 'My videos (2026)', 'clip_01.mp4', 'a'):
            self.assertEqual(save_places.clean_name(name, 'x'), name)
        self.assertIsNone(save_places.clean_name('', 'x'))
        self.assertIsNone(save_places.clean_name(None, 'x'))

    def test_paths_and_tricks_are_refused(self):
        for name in ('../etc', 'a/b', 'a\\b', '.hidden', 'x..y', 'end.', 'end ', '/abs', 'C:', 'tab\tname', 'a' * 81, 5):
            with self.assertRaises(ValueError, msg=repr(name)):
                save_places.clean_name(name, 'x')

    def test_places_are_ids_not_paths(self):
        for bad in ('/mnt/usb0', 'usb8', 'usb', '../internal', 'Internal', 3):
            with self.assertRaises(ValueError):
                save_places.check_place(bad)


class Places(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.internal = self.tmp / 'downloads'
        self.internal.mkdir()
        self.usb = (str(self.tmp / 'usb0'),) + tuple(str(self.tmp / ('usb%d' % i)) for i in range(1, 8))
        os.mkdir(self.usb[0])

    def test_a_pulled_drive_is_not_offered_and_not_written(self):
        with mock.patch.object(save_places, 'mounted', lambda root: False):
            self.assertEqual([p['id'] for p in save_places.places(self.internal, self.usb)], ['internal'])
            with self.assertRaises(ValueError):
                save_places.base_for('usb0', self.internal, self.usb)
            self.assertFalse(save_places.still_there('usb0', self.usb))
        self.assertTrue(save_places.still_there('internal', self.usb))

    def test_a_mounted_drive_is_offered_with_free_space(self):
        with mock.patch.object(save_places, 'mounted', lambda root: root == self.usb[0]):
            listed = save_places.places(self.internal, self.usb)
        self.assertEqual([p['id'] for p in listed], ['internal', 'usb0'])
        self.assertTrue(all(p['free_bytes'] > 0 and p['total_bytes'] > 0 for p in listed))

    def test_publish_names_and_never_overwrites(self):
        work = self.internal / 'abcd'
        work.mkdir()
        first = work / 'Song [xyz].f251.webm'
        first.write_bytes(b'one')
        saved = save_places.publish(first, 'internal', self.internal, 'Music', None)
        self.assertEqual(saved, self.internal / 'Saved' / 'Music' / 'Song [xyz].webm')
        second = work / 'Song [xyz].f251.webm'
        second.write_bytes(b'two')
        again = save_places.publish(second, 'internal', self.internal, 'Music', None)
        self.assertEqual(again.name, 'Song [xyz] (2).webm')
        self.assertEqual(saved.read_bytes(), b'one')

    def test_publish_uses_the_chosen_name_and_keeps_the_real_extension(self):
        src = self.internal / 'job' / 'Clip [id].merged.mkv'
        src.parent.mkdir()
        src.write_bytes(b'x')
        saved = save_places.publish(src, 'internal', self.internal, None, 'Holiday 2026')
        self.assertEqual(saved.name, 'Holiday 2026.mkv')
        self.assertFalse(src.exists())

    def test_publish_to_usb_lands_on_the_drive(self):
        src = self.internal / 'job' / 'File.mp4'
        src.parent.mkdir()
        src.write_bytes(b'data')
        with mock.patch.object(save_places, 'mounted', lambda root: root == self.usb[0]):
            saved = save_places.publish(src, 'usb0', self.internal, 'Films', None, usb_roots=self.usb)
        self.assertEqual(saved, Path(self.usb[0]) / 'Omni Downloads' / 'Films' / 'File.mp4')
        self.assertEqual(saved.read_bytes(), b'data')

    def test_publish_refuses_a_link_in_the_way(self):
        target = self.tmp / 'elsewhere'
        target.mkdir()
        (self.internal / 'Saved').mkdir()
        try:
            os.symlink(target, self.internal / 'Saved' / 'Music')
        except OSError:
            self.skipTest('symbolic links unavailable')
        src = self.internal / 'job' / 'a.mp4'
        src.parent.mkdir()
        src.write_bytes(b'x')
        with self.assertRaises(ValueError):
            save_places.publish(src, 'internal', self.internal, 'Music', None)
        self.assertEqual(list(target.iterdir()), [])


class FakeAdapter:
    """Two streams (video then audio) with yt-dlp-shaped hook calls; writes the merged file."""
    sizes = (3000, 1000)
    info = {'title': 'Clip', 'requested_formats': [{'filesize': 3000}, {'filesize': 1000}]}

    def download(self, url, folder, audio, hook, metadata, cancelled, postprocess_hook, **kw):
        type(self).seen = kw
        metadata(self.info)
        for name, size in zip(('v.f1.mp4', 'a.f2.m4a'), self.sizes):
            for done in (size // 2, size):
                hook({'status': 'downloading', 'filename': name, 'downloaded_bytes': done, 'total_bytes': size, 'speed': 500.0})
        out = Path(folder) / ('Clip [id].merged.' + (kw.get('container') or 'mkv'))
        out.write_bytes(b'media')
        return {'filepath': str(out)}


class Jobs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.jobs = worker.Jobs(self.tmp, str(self.tmp / 'history.json'))
        self.updates = []
        real = self.jobs.update
        def record(key, **values):
            self.updates.append(dict(values))
            real(key, **values)
        self.jobs.update = record
        self.jobs.ytdlp_adapter = lambda: FakeAdapter
        self.jobs.set_paused(True)   # the test runs each job itself; the queue must not run it too

    def run_job(self, **kw):
        key = self.jobs.create('https://example.com/v', False, quality={'height': 1080}, auto_fallback=False, **kw)
        with self.jobs.lock:
            job = dict(self.jobs.jobs[key])
        (self.tmp / key).mkdir()
        with mock.patch('importlib.util.find_spec', return_value=object()):
            self.jobs._route(key, job, self.tmp / key)
        with self.jobs.lock:
            return dict(self.jobs.jobs[key])

    def tearDown(self):
        self.jobs.close()

    def test_progress_counts_both_streams_once(self):
        job = self.run_job(container='mp4', save_place='internal', save_folder='Videos')
        counts = [u for u in self.updates if 'downloaded_bytes' in u]
        self.assertEqual([u['downloaded_bytes'] for u in counts], [1500, 3000, 3500, 4000])
        self.assertTrue(all(u['total_bytes'] == 4000 for u in counts))
        self.assertEqual([u['progress'] for u in counts], [37, 75, 87, 100])   # never restarts at the audio stream
        self.assertEqual(counts[0]['speed_bps'], 500)
        self.assertEqual(counts[0]['eta_seconds'], 5)
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(Path(job['filepath']), self.tmp / 'Saved' / 'Videos' / 'Clip [id].mp4')
        self.assertEqual(FakeAdapter.seen.get('container'), 'mp4')

    def test_not_enough_space_stops_before_downloading(self):
        with mock.patch.object(save_places, 'usage', lambda path: (1000, 10 ** 9)):
            job = self.run_job_expect_failure()
        self.assertIn('Not enough free space', job['error'])
        self.assertFalse([u for u in self.updates if 'downloaded_bytes' in u])

    def run_job_expect_failure(self):
        key = self.jobs.create('https://example.com/v', False, quality={'height': 1080}, auto_fallback=False, save_place='internal')
        with self.jobs.lock:
            job = dict(self.jobs.jobs[key])
        (self.tmp / key).mkdir()
        try:
            with mock.patch('importlib.util.find_spec', return_value=object()):
                self.jobs._route(key, job, self.tmp / key)
        except Exception as error:
            self.jobs.update(key, state='failed', error=str(error))
        with self.jobs.lock:
            return dict(self.jobs.jobs[key])

    def test_old_clients_keep_the_job_folder(self):
        job = self.run_job()
        self.assertTrue(job['filepath'].startswith(str(self.tmp / job['id'])))

    def test_create_checks_type_and_names(self):
        with self.assertRaises(ValueError):
            self.jobs.create('https://example.com/v', False, container='mp3')
        with self.assertRaises(ValueError):
            self.jobs.create('https://example.com/v', False, audio=True, container='mp4')
        with self.assertRaises(ValueError):
            self.jobs.create('https://example.com/v', False, save_place='internal', save_folder='../x')
        with self.assertRaises(ValueError):
            self.jobs.create('https://example.com/v', False, save_folder='Music')   # a name without a place
        with mock.patch.object(save_places, 'mounted', lambda root: False):
            with self.assertRaises(ValueError):
                self.jobs.create('https://example.com/v', False, save_place='usb0')

    def test_audio_type_picks_the_matching_stream(self):
        key = self.jobs.create('https://example.com/v', False, audio=True, container='m4a', save_place='internal')
        self.assertTrue(self.jobs.jobs[key]['format'].startswith('bestaudio[ext=m4a]/'))


class Status(unittest.TestCase):
    def test_status_lists_places(self):
        tmp = Path(tempfile.mkdtemp())
        jobs = worker.Jobs(tmp, None)
        try:
            listed = save_places.places(jobs.folder)
            self.assertEqual(listed[0]['id'], 'internal')
            json.dumps(listed)
        finally:
            jobs.close()


class ExpectedSize(unittest.TestCase):
    def test_sum_of_chosen_streams_or_nothing(self):
        self.assertEqual(worker.expected_size({'requested_formats': [{'filesize': 10}, {'filesize_approx': 5}]}), 15)
        self.assertIsNone(worker.expected_size({'requested_formats': [{'filesize': 10}, {}]}))
        self.assertEqual(worker.expected_size({'filesize': 7}), 7)
        self.assertEqual(worker.human_bytes(1536), '1.5 KB')


class PageCheckGivesUp(unittest.TestCase):
    """OMNI_PROBE_GIVEUP_V1: a page check that hangs or dies never leaves the GUI spinning forever."""
    def setUp(self):
        import probe, socket, threading
        self.probe, self.threading = probe, threading
        self.now = [1000.0]
        self.resolver = lambda host, port: (socket.AF_INET, '93.184.215.14', port)

    def prober(self, site):
        return self.probe.Prober(resolver=self.resolver, site=site, clock=lambda: self.now[0])

    def test_a_hanging_check_is_given_up_and_frees_the_slot(self):
        release = self.threading.Event()
        def hang(url):
            release.wait(5)
            return self.probe.result('ok', kind='page', source='yt-dlp')
        p = self.prober(hang)
        with mock.patch.object(self.probe, 'SITE_TIMEOUT', 0.05):
            self.assertEqual(p.probe('https://slow.test/watch', deep=True)['status'], 'slow')
            self.now[0] += 61
            gave_up = p.probe('https://slow.test/watch', deep=True)
            self.assertEqual(gave_up['status'], 'error')
            self.assertIn('took too long', gave_up['message'])
            # the slot is free again: another page is checked, not "busy"
            other = p.probe('https://other.test/watch', deep=True)
            self.assertNotEqual(other['status'], 'busy')
        release.set()

    def test_a_check_that_dies_answers_instead_of_spinning(self):
        def die(url):
            raise SystemExit('extractor exit')
        p = self.prober(die)
        with mock.patch.object(self.probe, 'SITE_TIMEOUT', 2.0):
            r = p.probe('https://dies.test/watch', deep=True)
        self.assertEqual(r['status'], 'error')
        self.assertEqual(p.probe('https://dies.test/watch', deep=True)['status'], 'error')   # cached, not "slow"


if __name__ == '__main__':
    unittest.main()
