# SPDX-License-Identifier: GPL-3.0-or-later
"""OMNI_DL_FFMPEG_V1: the console worker's in-process FFmpeg (_omni_native.remux).
Detection, option/metadata mapping and the native adapter's clip/remux flow with a fake _omni_native and a
fake yt-dlp (no network, no console). When OMNI_NATIVE_HOST_DIR points at a host-built _omni_native.so and
ffmpeg/ffprobe exist (test-only sample generator), a real copy-mode cut runs on a tiny generated sample.
Run: python3 -m unittest test_native_ffmpeg"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'worker'))
import adapters  # noqa: E402
import clips  # noqa: E402
import worker  # noqa: E402

URL = 'https://example.com/watch/video'
INFO = {'id': 'v1', 'title': 'Talk', 'duration': 600, 'uploader': 'Someone', 'upload_date': '20260102',
        'webpage_url': URL}


def fake_native(remux=None):
    module = types.ModuleType('_omni_native')
    module.merge = lambda *a: None
    if remux is not None:
        module.remux = remux
    return module


class Detection(unittest.TestCase):
    def test_no_module_means_no_in_process_ffmpeg(self):
        with mock.patch.dict(sys.modules, {'_omni_native': None}):
            self.assertIsNone(clips.native_remux())

    def test_older_worker_without_remux(self):
        with mock.patch.dict(sys.modules, {'_omni_native': fake_native()}):
            self.assertIsNone(clips.native_remux())

    def test_worker_with_remux(self):
        remux = lambda *a: True
        with mock.patch.dict(sys.modules, {'_omni_native': fake_native(remux)}):
            self.assertIs(clips.native_remux(), remux)

    def test_older_worker_still_refuses_clips_before_any_byte(self):
        with mock.patch('importlib.util.find_spec', return_value=object()), \
                mock.patch.dict(sys.modules, {'_omni_native': fake_native()}):
            with self.assertRaisesRegex(ValueError, 'FFmpeg'):
                adapters.NativePythonYtdlpAdapter().download(URL, '/x', clip=(80, 225))


class Mapping(unittest.TestCase):
    def test_metadata(self):
        tags = clips.media_metadata(dict(INFO, title='A\x00\x1bB', channel='Other'))
        self.assertEqual(tags, {'title': 'AB', 'artist': 'Someone', 'comment': URL, 'date': '2026-01-02'})
        self.assertEqual(clips.media_metadata({'channel': 'C', 'upload_date': '2026'}), {'artist': 'C'})
        self.assertEqual(clips.media_metadata(None), {})
        self.assertEqual(len(clips.media_metadata({'title': 'x' * 5000})['title']), 500)

    def test_targets(self):
        self.assertEqual(clips.cut_targets('/d/a.merged.mkv'), ['mp4', 'mkv'])    # MP4 first: exact start
        self.assertEqual(clips.cut_targets('/d/a.ts', 'mp4'), ['mp4', 'mkv'])
        self.assertEqual(clips.cut_targets('/d/a.ts', 'mkv'), ['mkv'])             # the user's choice wins
        self.assertEqual(clips.cut_targets('/d/a.m4a', audio=True), ['m4a', 'mka'])
        self.assertEqual(clips.cut_targets('/d/a.aac', audio=True), ['m4a', 'mka'])
        self.assertEqual(clips.cut_targets('/d/a.webm', audio=True), ['mka'])

    def test_notes(self):
        self.assertIn('cut exactly', clips.note((80, 225), True, clips.KEYFRAME_CONTAINER))
        keyframe = clips.note((80, 225), False, clips.KEYFRAME_CONTAINER)
        self.assertIn('MKV and WebM', keyframe)
        self.assertNotIn('no FFmpeg', keyframe)
        self.assertIn('no FFmpeg', clips.note((80, 225), False))   # the old wording stays the default


def fake_ytdlp(info, streams, record):
    module = types.ModuleType('yt_dlp')
    utils = types.ModuleType('yt_dlp.utils')

    class DownloadError(Exception):
        pass
    utils.DownloadError = DownloadError

    class YoutubeDL:
        def __init__(self, options):
            record['options'] = options
            self.folder = Path(options['outtmpl']).parent

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False, **kw):
            return dict(info, requested_formats=[dict(s) for s in streams])

        def prepare_filename(self, item):
            return str(self.folder / ('%s [%s].f%s.%s' % (item['title'], item['id'], item['format_id'], item['ext'])))

        def process_info(self, item):
            record.setdefault('fetched', []).append(item['format_id'])
            Path(self.prepare_filename(item)).write_bytes(b'stream')
    module.YoutubeDL = YoutubeDL
    module.utils = utils
    return {'yt_dlp': module, 'yt_dlp.utils': utils}


class FakeMerger:
    executable = None   # no ffmpeg program, as on the console

    def merge(self, video, audio, output, cancelled=None):
        Path(output).write_bytes(b'merged')


VIDEO = {'format_id': '137', 'ext': 'mp4', 'protocol': 'https', 'vcodec': 'avc1', 'acodec': 'none'}
AUDIO = {'format_id': '140', 'ext': 'm4a', 'protocol': 'https', 'vcodec': 'none', 'acodec': 'mp4a'}


class NativeFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_native(self, remux, clip=(80, 225), container=None, audio=False, streams=(VIDEO, AUDIO), info=INFO):
        record = {'remux': [], 'hooks': []}

        def recording_remux(source, target, start, end, tags, cancel):
            record['remux'].append((Path(source).name, Path(target).name, start, end, dict(tags)))
            return remux(source, target, start, end, tags, cancel)
        with mock.patch('importlib.util.find_spec', return_value=object()), \
                mock.patch.dict(sys.modules, {'_omni_native': fake_native(recording_remux),
                                              **fake_ytdlp(info, streams, record)}), \
                mock.patch.object(adapters, 'install_challenge_provider', lambda: None), \
                mock.patch.object(adapters, 'guard_options', lambda options: options), \
                mock.patch.object(adapters, 'check_public_link', lambda url: None), \
                mock.patch.object(adapters, '_forbid_external_ffmpeg', lambda: None), \
                mock.patch.object(adapters, 'FFmpegAdapter', FakeMerger):
            try:
                record['result'] = adapters.NativePythonYtdlpAdapter().download(
                    URL, self.tmp, audio=audio, clip=clip, container=container,
                    postprocess_hook=lambda d: record['hooks'].append((d['status'], d['postprocessor'])))
            except (ValueError, RuntimeError) as error:
                record['error'] = str(error)
        record['files'] = sorted(p.name for p in self.tmp.iterdir())
        return record

    @staticmethod
    def writes(exact):
        def remux(source, target, start, end, tags, cancel):
            Path(target).write_bytes(b'cut')
            return exact
        return remux

    def test_clip_is_cut_in_process_into_mp4(self):
        r = self.run_native(self.writes(True))
        self.assertEqual(r['remux'], [('Talk [v1].f137.merged.mkv', 'Talk [v1].f137 (clip 1m20s-3m45s).mp4', 80, 225,
                                       {'title': 'Talk', 'artist': 'Someone', 'comment': URL, 'date': '2026-01-02'})])
        self.assertEqual(r['files'], ['Talk [v1].f137 (clip 1m20s-3m45s).mp4'])   # streams and merged file removed
        self.assertTrue(r['result']['filepath'].endswith('(clip 1m20s-3m45s).mp4'))
        self.assertIn('cut exactly', r['result']['clip_note'])
        self.assertIn(('started', 'OmniNativeCut'), r['hooks'])
        self.assertIn(('finished', 'OmniNativeCut'), r['hooks'])
        self.assertNotIn('download_ranges', r['options'])    # yt-dlp's ffmpeg range download is never used here

    def test_mp4_refused_falls_back_to_mkv_with_keyframe_note(self):
        def remux(source, target, start, end, tags, cancel):
            if target.endswith('.mp4'):
                raise RuntimeError('Invalid argument')
            Path(target).write_bytes(b'cut')
            return False
        r = self.run_native(remux)
        self.assertEqual([t for _, t, *_ in r['remux']], ['Talk [v1].f137 (clip 1m20s-3m45s).mp4',
                                                          'Talk [v1].f137 (clip 1m20s-3m45s).mkv'])
        self.assertIn('MKV and WebM files start at a keyframe', r['result']['clip_note'])

    def test_user_chose_mkv(self):
        r = self.run_native(self.writes(False), container='mkv')
        self.assertEqual([t for _, t, *_ in r['remux']], ['Talk [v1].f137 (clip 1m20s-3m45s).mkv'])

    def test_cut_failure_fails_the_job_and_keeps_no_partial(self):
        def remux(source, target, start, end, tags, cancel):
            raise RuntimeError('Nothing to save in that part of the video')
        r = self.run_native(remux)
        self.assertIn('Could not cut the clip', r['error'])

    def test_cancel_during_cut_is_an_interruption(self):
        def remux(source, target, start, end, tags, cancel):
            raise RuntimeError('Immediate exit requested')
        with mock.patch.object(adapters, '_native_remux', wraps=adapters._native_remux):
            source = self.tmp / 'a.mkv'
            source.write_bytes(b'x')
            with self.assertRaises(InterruptedError):
                adapters._native_remux(remux, source, (1, 2), None, False, INFO, lambda: True, lambda d: None)

    def test_clip_outside_the_video_is_refused_before_fetching(self):
        r = self.run_native(self.writes(True), info=dict(INFO, duration=100))
        self.assertIn('ends after', r['error'])
        self.assertNotIn('fetched', r)

    def test_audio_clip(self):
        r = self.run_native(self.writes(True), audio=True, streams=(AUDIO,))
        self.assertEqual([t for _, t, *_ in r['remux']], ['Talk [v1].f140 (clip 1m20s-3m45s).m4a'])

    def test_whole_hls_ts_is_remuxed_into_the_chosen_type(self):
        ts = dict(VIDEO, protocol='m3u8_native', ext='mp4', acodec='mp4a')
        with mock.patch.object(adapters, '_refuse_live_playlist', lambda *a: None), \
                mock.patch.object(adapters, '_name_transport_stream', lambda p: Path(p).rename(Path(p).with_suffix('.ts')) or Path(p).with_suffix('.ts')):
            r = self.run_native(self.writes(True), clip=None, container='mp4', streams=(ts,))
        self.assertEqual(r['remux'][0][1:4], ('Talk [v1].f137.mp4', 0, None))
        self.assertEqual(r['files'], ['Talk [v1].f137.mp4'])
        self.assertNotIn('clip_note', r['result'])
        self.assertIn(('started', 'OmniNativeRemux'), r['hooks'])

    def test_whole_video_without_type_choice_is_untouched(self):
        r = self.run_native(self.writes(True), clip=None)
        self.assertEqual(r['remux'], [])
        self.assertEqual(r['files'], ['Talk [v1].f137.merged.mkv'])

    def test_failed_whole_remux_keeps_the_saved_file(self):
        def remux(source, target, start, end, tags, cancel):
            raise RuntimeError('Invalid data')
        ts = dict(VIDEO, protocol='m3u8_native', acodec='mp4a')
        with mock.patch.object(adapters, '_refuse_live_playlist', lambda *a: None), \
                mock.patch.object(adapters, '_name_transport_stream', lambda p: Path(p).rename(Path(p).with_suffix('.ts')) or Path(p).with_suffix('.ts')):
            r = self.run_native(remux, clip=None, container='mkv', streams=(ts,))
        self.assertEqual(r['files'], ['Talk [v1].f137.ts'])


class WorkerNote(unittest.TestCase):
    def test_worker_prefers_the_adapters_own_clip_note(self):
        tmp = Path(tempfile.mkdtemp())
        jobs = worker.Jobs(tmp, str(tmp / 'history.json'))
        jobs.set_paused(True)
        try:
            class Adapter:
                def download(self, url, folder, audio, hook, metadata, cancelled, postprocess_hook, **kw):
                    out = Path(folder) / 'Talk (clip 1m20s-3m45s).mkv'
                    out.write_bytes(b'media')
                    return {'filepath': str(out), 'clip_note': clips.note(kw['clip'], False, clips.KEYFRAME_CONTAINER)}
            jobs.ytdlp_adapter = lambda: Adapter
            with mock.patch('importlib.util.find_spec', return_value=object()):
                key = jobs.create(URL, False, clip_start='1:20', clip_end='3:45')
                with jobs.lock:
                    job = dict(jobs.jobs[key])
                (tmp / key).mkdir()
                jobs.clip_cut_exact = lambda: True
                jobs._route(key, job, tmp / key)
            with jobs.lock:
                done = dict(jobs.jobs[key])
            self.assertIn('MKV and WebM files start at a keyframe', json.dumps(done))
        finally:
            jobs.close()
            shutil.rmtree(tmp, ignore_errors=True)


def _probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,start_time:format_tags:stream=codec_type',
                          '-of', 'json', str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _decoded_frames(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                          '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip())


HOST = os.environ.get('OMNI_NATIVE_HOST_DIR')


@unittest.skipUnless(HOST and shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'needs OMNI_NATIVE_HOST_DIR (host _omni_native.so) and ffmpeg/ffprobe for the sample')
class RealCut(unittest.TestCase):
    """A real stream-copy cut through the host build of the binding (same C source, LGPL FFmpeg 7.1.5)."""
    @classmethod
    def setUpClass(cls):
        # Loaded under its own name but kept out of sys.modules/sys.path, so the fake-module tests that
        # run in the same process still see "no in-process FFmpeg" unless they install a fake.
        import importlib.util
        spec = importlib.util.spec_from_file_location('_omni_native', os.path.join(HOST, '_omni_native.so'))
        before = sys.modules.get('_omni_native')
        cls.native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.native)
        if before is None:   # a single-phase extension registers itself in sys.modules; undo that
            sys.modules.pop('_omni_native', None)
        else:
            sys.modules['_omni_native'] = before
        cls.tmp = Path(tempfile.mkdtemp())
        # 10 s, 30 fps, keyframe every 2 s (60 frames), B-frames, AAC: the shape of a site's MP4.
        # The generator (the system ffmpeg) is test-only; nothing here ships.
        cls.sample = cls.tmp / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30:duration=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=10',
                        '-c:v', 'libx264', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0', '-bf', '2',
                        '-c:a', 'aac', '-shortest', str(cls.sample)], check=True)
        cls.ts = cls.tmp / 'sample.ts'
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(cls.sample), '-c', 'copy', '-f', 'mpegts', str(cls.ts)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_mp4_cut_starts_exactly(self):
        out = self.tmp / 'cut.mp4'
        exact = self.native.remux(str(self.sample), str(out), 3.0, 7.0, {'title': 'Talk', 'artist': 'Someone'}, None)
        self.assertTrue(exact)
        probe = _probe(out)
        self.assertAlmostEqual(float(probe['format']['duration']), 4.0, delta=0.15)
        self.assertEqual(probe['format']['tags'].get('title'), 'Talk')
        self.assertEqual(probe['format']['tags'].get('artist'), 'Someone')
        self.assertEqual(sorted(s['codec_type'] for s in probe['streams']), ['audio', 'video'])
        # 3.0 s is 1 s past the keyframe at 2.0 s: the edit list hides those 30 frames, 4 s = 120 frames show.
        self.assertAlmostEqual(_decoded_frames(out), 120, delta=3)

    def test_mkv_cut_starts_at_the_keyframe(self):
        out = self.tmp / 'cut.mkv'
        exact = self.native.remux(str(self.sample), str(out), 3.0, 7.0, None, None)
        self.assertFalse(exact)
        self.assertAlmostEqual(_decoded_frames(out), 150, delta=3)   # from the keyframe at 2.0 s

    def test_ts_remux_whole_into_mp4(self):
        out = self.tmp / 'whole.mp4'
        self.assertTrue(self.native.remux(str(self.ts), str(out)))
        probe = _probe(out)
        self.assertAlmostEqual(float(probe['format']['duration']), 10.0, delta=0.15)
        self.assertAlmostEqual(float(probe['format'].get('start_time', 0)), 0.0, delta=0.1)
        self.assertAlmostEqual(_decoded_frames(out), 300, delta=3)

    def test_ts_cut_into_mp4(self):
        out = self.tmp / 'tscut.mp4'
        self.assertTrue(self.native.remux(str(self.ts), str(out), 1.5, 4.5))
        self.assertAlmostEqual(float(_probe(out)['format']['duration']), 3.0, delta=0.2)

    def test_merge_still_works_on_the_minimal_build(self):
        # The worker's existing join (merge) now runs on the same minimal LGPL FFmpeg: YouTube-shaped
        # H.264+AAC (MP4/M4A) and VP9+Opus (WebM) separate streams.
        def make(name, *args):
            subprocess.run(['ffmpeg', '-v', 'error', *args, str(self.tmp / name)], check=True)
            return str(self.tmp / name)
        v = make('v.mp4', '-i', str(self.sample), '-an', '-c', 'copy')
        a = make('a.m4a', '-i', str(self.sample), '-vn', '-c', 'copy')
        out = self.tmp / 'joined.mp4'
        self.native.merge(v, a, str(out))
        self.assertEqual(sorted(s['codec_type'] for s in _probe(out)['streams']), ['audio', 'video'])
        try:
            vw = make('v.webm', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30:duration=3', '-c:v', 'libvpx-vp9',
                      '-deadline', 'realtime', '-g', '30')
            aw = make('a.webm', '-f', 'lavfi', '-i', 'sine=sample_rate=48000:duration=3', '-c:a', 'libopus')
        except subprocess.CalledProcessError:
            self.skipTest('the system ffmpeg has no VP9/Opus encoder for the sample')
        out = self.tmp / 'joined.mkv'
        self.native.merge(vw, aw, str(out))
        self.assertEqual(sorted(s['codec_type'] for s in _probe(out)['streams']), ['audio', 'video'])
        cut = self.tmp / 'joined-cut.mkv'
        self.native.remux(str(out), str(cut), 1.0, 2.0)
        # MKV starts at the keyframe at or before 1.0 s (VP9 keyframe spacing is the encoder's choice).
        self.assertTrue(0.95 <= float(_probe(cut)['format']['duration']) <= 2.1)

    def test_existing_output_is_never_replaced(self):
        out = self.tmp / 'exists.mp4'
        out.write_bytes(b'keep')
        with self.assertRaises(RuntimeError):
            self.native.remux(str(self.sample), str(out), 1.0, 2.0)
        self.assertEqual(out.read_bytes(), b'keep')

    def test_cancel_removes_the_partial_file(self):
        out = self.tmp / 'cancel.mp4'
        with self.assertRaises(RuntimeError):
            self.native.remux(str(self.sample), str(out), 1.0, 9.0, None, lambda: True)
        self.assertFalse(out.exists())

    def test_bad_arguments(self):
        for args in ((-1.0, 2.0), (5.0, 2.0), (1.0, 0.0)):
            with self.assertRaises(ValueError):
                self.native.remux(str(self.sample), str(self.tmp / 'bad.mp4'), *args)
        with self.assertRaises(RuntimeError):
            self.native.remux('relative.mp4', str(self.tmp / 'bad.mp4'))
        with self.assertRaises(TypeError):
            self.native.remux(str(self.sample), str(self.tmp / 'bad.mp4'), 0.0, None, {'title': 5})


if __name__ == '__main__':
    unittest.main()
