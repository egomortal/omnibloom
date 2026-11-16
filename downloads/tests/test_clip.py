# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_CLIP_V1 (D01): "Save a clip (from 1:20 to 3:45)".
Time parsing, checks, the yt-dlp option mapping (fake yt-dlp, no network) and the job plumbing.
Run with the test stand-in on the path: PYTHONPATH=fake_ytdlp python3 -m unittest test_clip"""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import adapters  # noqa: E402
import clips  # noqa: E402
import history  # noqa: E402
import worker  # noqa: E402

URL = 'https://example.com/watch/video'


class Parsing(unittest.TestCase):
    def test_good_times(self):
        for text, seconds in (('1:20', 80), ('01:20', 80), ('0:00', 0), ('3:45', 225), ('90:00', 5400),
                              ('1:02:03', 3723), ('5:59:59', 21599), (' 1:20 ', 80)):
            self.assertEqual(clips.parse_time(text), seconds, text)

    def test_bad_times(self):
        for bad in ('', '80', '1:2', '1:60', '1:20:60', '12:00:00', '1.20', '-1:20', '1:20:00:00', 'a:bc', '1:2O',
                    '1234:00', None, 80, 1.5, [], '1:20\n'):
            with self.assertRaises(ValueError, msg=repr(bad)):
                clips.parse_time(bad)

    def test_stamps_and_file_suffix(self):
        self.assertEqual(clips.stamp(80), '1m20s')
        self.assertEqual(clips.stamp(0), '0m00s')
        self.assertEqual(clips.stamp(3723), '1h02m03s')
        self.assertEqual(clips.suffix((80, 225)), ' (clip 1m20s-3m45s)')
        self.assertEqual(clips.suffix(None), '')


class Checks(unittest.TestCase):
    def test_clip_pairs(self):
        self.assertIsNone(clips.check_clip(None, None))
        self.assertIsNone(clips.check_clip('', '  '))
        self.assertEqual(clips.check_clip('1:20', '3:45'), (80, 225))
        self.assertEqual(clips.check_clip('', '3:45'), (0, 225))      # empty start = from the beginning
        self.assertEqual(clips.check_clip(None, '6:00:00'), (0, 21600))  # exactly 6 h is allowed

    def test_refusals(self):
        for start, end, why in (('1:20', None, 'end time'), ('3:45', '1:20', 'start before'), ('1:20', '1:20', 'start before'),
                                ('0:00', '6:00:01', '6 hours'), ('0:00', '7:00:00', '6 hours'), ('x', '1:00', 'look like')):
            with self.assertRaisesRegex(ValueError, why):
                clips.check_clip(start, end)

    def test_against_the_video(self):
        clips.check_against_info({'duration': 600}, (80, 225))
        clips.check_against_info({'duration': 225.4}, (80, 226))      # rounding slack
        clips.check_against_info({}, (80, 225))                       # length unknown: yt-dlp cuts what is there
        clips.check_against_info({'is_live': True}, None)             # no clip: not our business
        with self.assertRaisesRegex(ValueError, 'ends after'):
            clips.check_against_info({'duration': 200}, (80, 225))
        with self.assertRaisesRegex(ValueError, 'starts after'):
            clips.check_against_info({'duration': 60}, (80, 225))
        for live in ({'is_live': True, 'duration': 9999}, {'live_status': 'is_live'}, {'live_status': 'is_upcoming'},
                     {'live_status': 'post_live'}):
            with self.assertRaisesRegex(ValueError, 'live stream'):
                clips.check_against_info(live, (80, 225))

    def test_notes(self):
        self.assertEqual(clips.note(None, True), '')
        self.assertIn('cut exactly', clips.note((80, 225), True))
        keyframe = clips.note((80, 225), False)
        self.assertIn('nearest keyframes', keyframe)
        self.assertIn('1m20s to 3m45s', keyframe)


def fake_ytdlp(info, record):
    """A yt_dlp module stand-in: records the options and the range function's arguments."""
    module = types.ModuleType('yt_dlp')
    utils = types.ModuleType('yt_dlp.utils')

    class DownloadError(Exception):
        pass

    def download_range_func(chapters, ranges, *rest):
        record['range_args'] = (chapters, ranges)
        return ('ranges', tuple(ranges))
    utils.DownloadError = DownloadError
    utils.download_range_func = download_range_func

    class YoutubeDL:
        def __init__(self, options):
            record['options'] = options

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False, **kw):
            return dict(info)

        def process_ie_result(self, value, download=True):
            record['downloaded'] = True
            return dict(value, filepath='/x/' + record['options']['outtmpl'].rsplit('/', 1)[-1])
    module.YoutubeDL = YoutubeDL
    module.utils = utils
    return {'yt_dlp': module, 'yt_dlp.utils': utils}


class OptionMapping(unittest.TestCase):
    def run_adapter(self, clip, info=None, ffmpeg='/usr/bin/ffmpeg'):
        record = {}
        with mock.patch.dict(sys.modules, fake_ytdlp(info or {'id': 'v1', 'title': 'Talk', 'duration': 600}, record)), \
                mock.patch.object(adapters, 'install_challenge_provider', lambda: None), \
                mock.patch.object(adapters, 'guard_options', lambda options: options), \
                mock.patch.object(adapters, 'check_public_link', lambda url: None), \
                mock.patch.object(adapters, 'FFmpegAdapter', lambda: types.SimpleNamespace(executable=ffmpeg)):
            try:
                adapters.PythonYtdlpAdapter().download(URL, '/x', False, clip=clip)
            except ValueError as error:
                record['error'] = str(error)
        return record

    def test_exact_cuts_with_ffmpeg(self):
        r = self.run_adapter((80, 225))
        self.assertEqual(r['range_args'], (None, [(80, 225)]))
        self.assertEqual(r['options']['download_ranges'], ('ranges', ((80, 225),)))
        self.assertIs(r['options']['force_keyframes_at_cuts'], True)
        self.assertTrue(r['options']['outtmpl'].endswith('%(title).120s [%(id)s] (clip 1m20s-3m45s).%(ext)s'))
        self.assertTrue(r['downloaded'])

    def test_keyframe_cuts_without_ffmpeg(self):
        r = self.run_adapter((80, 225), ffmpeg=None)
        self.assertEqual(r['options']['download_ranges'], ('ranges', ((80, 225),)))
        self.assertIs(r['options']['force_keyframes_at_cuts'], False)

    def test_whole_video_is_unchanged(self):
        r = self.run_adapter(None)
        self.assertNotIn('download_ranges', r['options'])
        self.assertNotIn('force_keyframes_at_cuts', r['options'])
        self.assertTrue(r['options']['outtmpl'].endswith('%(title).120s [%(id)s].%(ext)s'))
        self.assertNotIn('range_args', r)

    def test_live_and_too_long_are_refused_before_downloading(self):
        r = self.run_adapter((80, 225), info={'id': 'v', 'title': 'Live', 'is_live': True})
        self.assertIn('live stream', r['error'])
        self.assertNotIn('downloaded', r)
        r = self.run_adapter((80, 225), info={'id': 'v', 'title': 'Short', 'duration': 100})
        self.assertIn('ends after', r['error'])
        self.assertNotIn('downloaded', r)

    def test_console_native_path_refuses_clips_before_any_byte(self):
        with mock.patch('importlib.util.find_spec', return_value=object()):
            with self.assertRaisesRegex(ValueError, 'FFmpeg'):
                adapters.NativePythonYtdlpAdapter().download(URL, '/x', clip=(80, 225))


class FakeAdapter:
    def download(self, url, folder, audio, hook, metadata, cancelled, postprocess_hook, **kw):
        type(self).seen = kw
        metadata({'title': 'Talk'})
        out = Path(folder) / ('Talk [v1]' + clips.suffix(kw.get('clip')) + '.mp4')
        out.write_bytes(b'media')
        return {'filepath': str(out)}


class JobPlumbing(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.jobs = worker.Jobs(self.tmp, str(self.tmp / 'history.json'))
        self.jobs.ytdlp_adapter = lambda: FakeAdapter
        self.jobs.set_paused(True)

    def tearDown(self):
        self.jobs.close()

    def create(self, *args, **kw):
        # A real (non-demo) yt-dlp job needs yt-dlp importable; the tests never reach it.
        with mock.patch('importlib.util.find_spec', return_value=object()):
            return self.jobs.create(*args, **kw)

    def run_job(self, exact, **kw):
        key = self.create(URL, False, **kw)
        with self.jobs.lock:
            job = dict(self.jobs.jobs[key])
        (self.tmp / key).mkdir()
        self.jobs.clip_cut_exact = lambda: exact
        with mock.patch('importlib.util.find_spec', return_value=object()):
            self.jobs._route(key, job, self.tmp / key)
        with self.jobs.lock:
            return dict(self.jobs.jobs[key])

    def test_create_keeps_the_clip_and_turns_fallback_off(self):
        key = self.create(URL, False, clip_start='1:20', clip_end='3:45')
        job = self.jobs.jobs[key]
        self.assertEqual(job['clip'], [80, 225])
        self.assertFalse(job['auto_fallback'])     # JDownloader would save the whole video
        self.assertIn('"clip": [80, 225]', job['quality_key'])
        whole = self.create(URL, False)
        self.assertIsNone(self.jobs.jobs[whole]['clip'])
        self.assertTrue(self.jobs.jobs[whole]['auto_fallback'])

    def test_create_refusals(self):
        for kw in (dict(clip_start='3:45', clip_end='1:20'), dict(clip_end='7:00:00'), dict(clip_start='1:20'),
                   dict(clip_end='abc'), dict(clip_end='3:45', engine='jdownloader'), dict(clip_end='3:45', direct=True)):
            with self.assertRaises(ValueError, msg=repr(kw)):
                self.create(URL, False, **kw)

    def test_same_request_id_with_another_clip_is_refused(self):
        rid = 'ab' * 16
        key = self.create(URL, False, request_id=rid, clip_end='3:45')
        self.assertEqual(self.create(URL, False, request_id=rid, clip_end='3:45'), key)
        with self.assertRaises(ValueError):
            self.create(URL, False, request_id=rid, clip_end='3:46')

    def test_clip_reaches_the_adapter_and_the_note(self):
        job = self.run_job(True, clip_start='1:20', clip_end='3:45')
        self.assertEqual(job['state'], 'completed')
        self.assertEqual(FakeAdapter.seen['clip'], (80, 225))
        self.assertIn('cut exactly', job['note'])
        self.assertTrue(job['filepath'].endswith('Talk [v1] (clip 1m20s-3m45s).mp4'))
        job = self.run_job(False, clip_end='3:45')
        self.assertIn('nearest keyframes', job['note'])
        self.assertIn('0m00s to 3m45s', job['note'])

    def test_whole_video_adds_no_clip_argument(self):
        job = self.run_job(True)
        self.assertNotIn('clip', FakeAdapter.seen)
        self.assertNotIn('Clip', job['note'])

    def test_typed_file_name_gets_the_clip_suffix(self):
        job = self.run_job(True, clip_start='1:20', clip_end='3:45', save_place='internal', save_name='My talk')
        self.assertEqual(Path(job['filepath']).name, 'My talk (clip 1m20s-3m45s).mp4')
        self.assertEqual(worker.clip_save_name('My talk.mp4', [80, 225], 'x.mp4'), 'My talk (clip 1m20s-3m45s).mp4')
        long = worker.clip_save_name('a' * 80, [0, 21600], 'x.mp4')
        self.assertLessEqual(len(long), 80)
        self.assertTrue(long.endswith(' (clip 0m00s-6h00m00s)'))
        self.assertEqual(worker.clip_save_name('Name', None, 'x.mp4'), 'Name')
        self.assertIsNone(worker.clip_save_name(None, [0, 5], 'x.mp4'))

    def test_history_keeps_only_a_valid_clip(self):
        self.assertEqual(history._clip([80, 225]), [80, 225])
        for bad in ([225, 80], [0, 21601], ['1', 2], [1], None, 'x', [True, 5], [-1, 5]):
            self.assertIsNone(history._clip(bad), repr(bad))


if __name__ == '__main__':
    unittest.main()
