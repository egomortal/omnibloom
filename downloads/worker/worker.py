"""Common on-console API; native runtime launch is an optional owned lifecycle hook.

downloader-1: every real job walks an engine route. The user's go-to engine is
tried first; on failure the other engine takes the job automatically (yt-dlp
route: site extractor -> generic extractor -> direct file). DRM, full storage,
cancellation and an unconfirmed Java cleanup never fall through.
"""
import importlib.util
import gc
from collections import deque
from adapters import (PythonYtdlpAdapter, NativePythonYtdlpAdapter, DirectFileAdapter, NoFallback, Paused,
                      EngineUnavailable, capabilities, classify_failure, redact_urls)
import json
import io
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from history import History, TERMINAL, PAUSED, MAX_JOBS, MAX_PENDING
from saved_links import SavedLinks, SavedLinksUnavailable, validate_http_url
from jd_adapter import JDownloaderAdapter
from schedule_policy import Policy, RateLimiter
from presets import preset_options
from probe import Prober, quality_format, site_probe  # OMNI_DOWNLOADS_PROBE_V5
import save_places  # OMNI_DL_SAVE_V1
import files_library  # OMNI_DL_LIBRARY_V1
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
MAX_HTTP_REQUESTS = 16
REQUEST_TIMEOUT = 5
MAX_BODY_BYTES = 8192
ENGINE_NAMES = {'ytdlp': 'yt-dlp', 'jdownloader': 'JDownloader'}
# OMNI_SMALL_COMFORTS_V1: every finished (non-demo) download is noted here as "job id<TAB>title", newest last, at most
# DONE_KEEP lines; Omni checks the file's stamp every 5 s and shows "Downloaded: <title>" once when the user is on
# another tab. Written only when its folder exists (the console's /data/omni); replaced atomically; best effort.
DONE_FILE = os.environ.get('OMNI_DOWNLOADS_DONE_FILE', '/data/omni/downloads-done.txt')
DONE_KEEP = 8
# OMNI_DL_PROGRESS_V1: /api/active counts every job not finished except these (paused: waits for the user; pausing /
# cancelling: about to stop).
ACTIVE_SKIP = frozenset((PAUSED, 'pausing', 'cancelling'))
# OMNI_DL_RESUME_V1: failed jobs are never retried automatically; Retry is the user's choice only.
AUTO_RETRY_LIMIT = 0
JOB_ID = frozenset('0123456789abcdef')
# Progress titles the worker shows while it works; the finished file's name is the better title then.
PLACEHOLDER_TITLES = frozenset(('', 'Saving the file', 'Downloading the file', 'Inspecting link', 'Starting JDownloader',
                                'Trying a direct file download', 'Media', 'File'))


def done_title(job):
    title = str(job.get('title') or '').strip()
    if title in PLACEHOLDER_TITLES or title.startswith('Switching to '):
        title = Path(str(job.get('filepath') or '')).name or 'a download'
    title = ''.join(' ' if ord(c) < 32 or ord(c) == 127 else c for c in title).strip()
    return title[:200] or 'a download'


def _console_offset(schedule_path):
    """Return offset_provider(now) reading <state>/tz-offset.json {"utcOffsetMinutes": int}; None when unavailable."""
    def provider(now):
        if not schedule_path:
            return None
        try:
            with open(schedule_path.with_name("tz-offset.json"), "rb") as fh:
                data = json.loads(fh.read(512))
            value = data.get("utcOffsetMinutes")
            return value if type(value) is int and -840 <= value <= 840 else None
        except (OSError, ValueError, AttributeError):
            return None
    return provider


class Jobs:
    def __init__(self, folder, state_file=None, jd_adapter=None, jd_lifecycle=None, policy=None, done_file=DONE_FILE):
        self.folder = Path(folder)
        self.done_file = Path(done_file) if done_file else None  # OMNI_SMALL_COMFORTS_V1
        self.done_recent = deque(maxlen=DONE_KEEP)
        self.done_lock = threading.Lock()
        _sched = Path(state_file).with_name("schedule.json") if state_file else None
        # Schedule schema 2 (R3-045 fix): console-local minutes; the offset comes from the trusted host
        # (Omni writes tz-offset.json beside the state file). Missing or invalid offset => no scheduled starts.
        self.policy = policy or Policy(_sched, offset_provider=_console_offset(_sched))
        self.history = History(state_file)
        self.jobs = self.history.load()
        self.lock = threading.Lock()
        self.ready = threading.Condition(self.lock)
        self.pending = deque()
        self.active = None
        self.queue_paused = False
        self.dispatcher = None
        self.closed = False
        self.jd_adapter = jd_adapter or JDownloaderAdapter.from_environment()
        self.jd_lifecycle = jd_lifecycle

    def create(self, url, demo, audio=False, request_id=None, engine='ytdlp', auto_fallback=True, quality=None, referer=None, preset=None, subtitle_lang=None,
               container=None, save_place=None, save_folder=None, save_name=None, direct=False):
        if not isinstance(url, str) or len(url) > 4096 or type(demo) is not bool or type(audio) is not bool:
            raise ValueError('URL must be text (up to 4096 characters); demo and audio must be booleans.')
        # OMNI_FILE_DOWNLOADS_V1: an original (non-media) file, e.g. a PDF or ZIP Omni handed over from a page.
        # The yt-dlp route skips the extractors and saves it with the direct file download; nothing to convert.
        if type(direct) is not bool:
            raise ValueError('direct must be a boolean.')
        if direct and (audio or quality is not None or preset is not None or container is not None):
            raise ValueError('An original file is saved as it is: no audio, quality, preset or file type choice.')
        validate_http_url(url)
        if engine not in ('ytdlp', 'jdownloader'):
            raise ValueError('Choose yt-dlp or JDownloader.')
        if type(auto_fallback) is not bool:
            raise ValueError('auto_fallback must be a boolean.')
        if engine == 'jdownloader' and audio:
            raise ValueError('JDownloader keeps original file formats; audio-only is a yt-dlp option.')
        # OMNI_DOWNLOADS_PROBE_V5: a checked quality choice becomes a yt-dlp format selector here,
        # never text from the GUI. JDownloader keeps original files, so it ignores the choice.
        options = preset_options(preset, subtitle_lang)
        if preset is not None:
            if engine != 'ytdlp' or quality is not None:
                raise ValueError('Presets require yt-dlp and cannot be combined with a custom quality.')
            audio = preset in ('audio-m4a', 'audio-opus')
            auto_fallback = False  # Never bypass a preset by falling back to another engine.
        fmt = options.get('format') or (quality_format(quality) if engine == 'ytdlp' else None)
        # OMNI_DL_SAVE_V1: the file type and where the finished file goes. Checked here; the GUI sends ids and plain
        # names, never paths. A job without save_place keeps the old behaviour (the file stays in its job folder).
        audio_job = audio or bool(isinstance(quality, dict) and quality.get('audio_only'))
        if container is not None:
            if container not in (('m4a', 'webm') if audio_job else ('mp4', 'mkv')):
                raise ValueError('File type must be ' + ('m4a or webm' if audio_job else 'mp4 or mkv') + ' for this download.')
            if audio_job and engine == 'ytdlp' and preset is None:
                fmt = 'bestaudio[ext=%s]/%s' % (container, fmt or 'bestaudio')
        if save_place is not None:
            save_places.base_for(save_places.check_place(save_place), self.folder)   # refuses a USB drive that is not there
        save_folder = save_places.clean_name(save_folder, 'The folder name')
        save_name = save_places.clean_name(save_name, 'The file name')
        if (save_folder or save_name) and save_place is None:
            raise ValueError('Choose where to save before naming a folder or file.')
        if referer is not None:
            validate_http_url(referer)
        choice = json.dumps({'quality':quality,'preset':preset,'subtitle_lang':subtitle_lang},sort_keys=True) if quality is not None or preset is not None else ''
        if container or save_place:
            choice += json.dumps({'container':container,'save':[save_place,save_folder,save_name]},sort_keys=True)
        if direct:
            choice += '{"direct":true}'
        if request_id is not None and (not isinstance(request_id, str) or len(request_id) != 32
                                       or any(c not in '0123456789abcdef' for c in request_id)):
            raise ValueError('request_id must contain 32 lowercase hexadecimal characters.')
        if not demo and engine == 'ytdlp' and not auto_fallback and not direct and importlib.util.find_spec('yt_dlp') is None:
            raise ValueError('yt-dlp is not installed in this Python runtime. Demo mode is available.')
        key = secrets.token_hex(8)
        with self.lock:
            if self.closed:
                raise ValueError('Download worker is shutting down.')
            if self.jd_adapter.poisoned:
                raise ValueError('Java cleanup was not confirmed; restart its isolated worker before adding jobs.')
            if request_id is not None:
                for job in self.jobs.values():
                    if job.get('request_id') == request_id:
                        if (job['url'], job['demo'], job['audio'], job.get('engine_requested', job.get('engine', 'ytdlp')), job.get('quality_key', '')) != (url, demo, audio, engine, choice):
                            raise ValueError('request_id was already used for a different download.')
                        return job['id']
            if self.waiting_count() >= MAX_PENDING:
                raise ValueError('Queue is full (8 pending jobs). Wait or cancel a job.')
            while len(self.jobs) >= MAX_JOBS:
                oldest = next((k for k, j in self.jobs.items()
                               if j['state'] in TERMINAL and k != self.active), None)
                if oldest is None:
                    raise ValueError('Queue is full')
                del self.jobs[oldest]
            self.jobs[key] = dict(id=key, url=url, demo=demo, audio=audio, state='queued', progress=0,
                                 title='Waiting', error='', cancel=False, request_id=request_id, engine=engine,
                                 engine_requested=engine, auto_fallback=auto_fallback, note='',
                                 format=fmt, quality_key=choice, referer=referer, preset=preset, subtitle_lang=subtitle_lang,
                                 container=container, save_place=save_place, save_folder=save_folder, save_name=save_name,
                                 direct=direct, downloaded_bytes=None, total_bytes=None, speed_bps=None, eta_seconds=None,
                                 pause=False, attempt=1, retries=0, resumed=False)
            self.pending.append(key)
            self.history.save(self.jobs)
            self._start_dispatcher(key)
            self.ready.notify_all()
        return key

    def waiting_count(self):
        """Jobs that hold a queue slot (running or waiting); paused jobs wait for the user and hold none."""
        return sum(j['state'] not in TERMINAL and j['state'] != PAUSED for j in self.jobs.values())

    def _start_dispatcher(self, key):
        """Called with the lock held, after `key` was queued."""
        if self.dispatcher is not None:
            return
        try:
            dispatcher = threading.Thread(target=self.dispatch, name='omni-download-dispatcher', daemon=True)
            dispatcher.start()
            self.dispatcher = dispatcher
        except RuntimeError as error:
            self.pending.remove(key)
            self.jobs[key].update(state='failed', error='Could not start the download worker.')
            self.history.save(self.jobs)
            raise ValueError('Could not start the download worker.') from error

    # ----- pause / resume / retry (OMNI_DL_RESUME_V1) -----------------------
    @staticmethod
    def _job_id(key):
        if not isinstance(key, str) or len(key) != 16 or not set(key) <= JOB_ID:
            raise ValueError('id must contain 16 lowercase hexadecimal characters.')
        return key

    def pause(self, key):
        """A waiting job is paused at once; a running one stops at its next progress report, keeping its partial files."""
        self._job_id(key)
        with self.ready:
            job = self.jobs.get(key)
            if job is None:
                raise ValueError('Unknown download.')
            if job['state'] in (PAUSED, 'pausing'):
                return job['state']
            if job['state'] in TERMINAL or job['state'] == 'cancelling' or job['cancel']:
                raise ValueError('Only waiting or running downloads can be paused.')
            if key in self.pending:
                self.pending.remove(key)
                job.update(state=PAUSED, pause=False, speed_bps=None, eta_seconds=None)
                self.history.save(self.jobs)
                self.ready.notify_all()
                return PAUSED
            if job.get('engine') == 'jdownloader':
                raise ValueError('A JDownloader download cannot be paused; cancel it instead.')
            job.update(pause=True, state='pausing')
            self.history.save(self.jobs)
            return 'pausing'

    def resume(self, key, retry=False):
        """Queue a paused, interrupted or failed job again with the same choices; its partial files are continued.
        Retry (failed jobs only) is the same with a fresh attempt counter."""
        self._job_id(key)
        with self.lock:
            job = self.jobs.get(key)
            if job is None:
                raise ValueError('Unknown download.')
            allowed = ('failed',) if retry else (PAUSED, 'interrupted', 'failed')
            if job['state'] not in allowed:
                raise ValueError('Only failed downloads can be retried.' if retry else
                                 'Only paused, interrupted or failed downloads can be resumed.')
            if not job.get('url'):
                raise ValueError("This download's link was not kept; submit the link again.")
            job = dict(job)
        # The kept choices are checked again, as a new job's are (the history file is only trusted so far).
        validate_http_url(job['url'])
        if job.get('referer') is not None:
            validate_http_url(job['referer'])
        if job.get('save_place') is not None:
            save_places.base_for(save_places.check_place(job['save_place']), self.folder)   # the USB drive must be there
        save_places.clean_name(job.get('save_folder'), 'The folder name')
        save_places.clean_name(job.get('save_name'), 'The file name')
        with self.ready:
            if self.closed:
                raise ValueError('Download worker is shutting down.')
            if self.jd_adapter.poisoned:
                raise ValueError('Java cleanup was not confirmed; restart its isolated worker before adding jobs.')
            current = self.jobs.get(key)
            if current is None or current['state'] != job['state']:
                raise ValueError('The download changed meanwhile; check the queue.')
            if self.waiting_count() >= MAX_PENDING:
                raise ValueError('Queue is full (8 pending jobs). Wait or cancel a job.')
            attempt = 1 if retry else int(current.get('attempt') or 1) + 1
            retries = int(current.get('retries') or 0) + (1 if retry else 0)
            current.update(state='queued', cancel=False, pause=False, error='', resumed=True, restored=False,
                           attempt=attempt, retries=retries, speed_bps=None, eta_seconds=None,
                           engine=current.get('engine_requested', current.get('engine', 'ytdlp')),
                           note=('Retry %d started by you.' % retries) if retry else 'Resumed by you; partial files are continued.')
            self.pending.append(key)
            self.history.save(self.jobs)
            self._start_dispatcher(key)
            self.ready.notify_all()
        return 'queued'

    def retry(self, key):
        return self.resume(key, retry=True)

    def pause_requested(self, key):
        if 'jobs' not in self.__dict__:   # a bare Jobs in unit tests
            return False
        with self.lock:
            return bool(self.jobs[key].get('pause'))

    def stop_reason(self, key):
        if self.cancelled(key):
            return 'cancel'
        return 'pause' if self.pause_requested(key) else None

    def check_stop(self, key):
        reason = self.stop_reason(key)
        if reason == 'cancel':
            raise InterruptedError('Cancelled')
        if reason == 'pause':
            raise Paused('Paused')

    def dispatch(self):
        """One owned thread consumes every job, including rapid cancel/recreate."""
        while True:
            with self.ready:
                while not self.closed and (not self.pending or self.queue_paused or not self.policy.allow_start()):
                    self.ready.wait(timeout=1)
                if self.closed:
                    return
                key = self.pending[0]
            self.run(key)

    def close(self, timeout=5):
        """Cancel owned work and wait up to timeout; active I/O is cooperative.

        Return False if an active adapter has not returned yet. Callers can
        retry close; no new work is admitted after the first call.
        """
        with self.ready:
            if not self.closed:
                self.closed = True
                for key in self.pending:
                    self.jobs[key].update(cancel=True, state='cancelled')
                self.pending.clear()
                if self.active is not None and self.jobs[self.active]['state'] not in TERMINAL:
                    self.jobs[self.active].update(cancel=True, state='cancelling')
                self.history.save(self.jobs)
                self.ready.notify_all()
            dispatcher = self.dispatcher
        if dispatcher is not None and dispatcher is not threading.current_thread():
            dispatcher.join(timeout)
        return dispatcher is None or not dispatcher.is_alive()

    def update(self, key, **values):
        finished = None
        with self.lock:
            job = self.jobs[key]
            if job['cancel']:
                if values.get('state') == 'completed':
                    values.update(state='cancelled', error='')
                elif values.get('state') not in TERMINAL:
                    values['state'] = 'cancelling'
            elif job.get('pause') and 'state' in values and values['state'] not in TERMINAL and values['state'] != PAUSED:
                values['state'] = 'pausing'   # OMNI_DL_RESUME_V1: until the job reaches its next progress report
            if values.get('state') in TERMINAL or values.get('state') == PAUSED:
                values['pause'] = False
            job.update(values)
            if values.get('state') in TERMINAL or values.get('state') == PAUSED:
                self.history.save(self.jobs)
            if values.get('state') == 'completed' and not job.get('demo'):
                finished = (str(key), done_title(job))  # OMNI_SMALL_COMFORTS_V1
        if finished:
            self.note_done(*finished)

    def note_done(self, key, title):
        """OMNI_SMALL_COMFORTS_V1: append "key<TAB>title" to the done file (outside the jobs lock; never raises)."""
        if self.done_file is None:
            return
        with self.done_lock:
            self.done_recent = deque((k, t) for k, t in self.done_recent if k != key)
            self.done_recent = deque(self.done_recent, maxlen=DONE_KEEP)
            self.done_recent.append((key, title))
            try:
                if not self.done_file.parent.is_dir():
                    return
                temp = self.done_file.with_name(self.done_file.name + '.tmp')
                with open(temp, 'w', encoding='utf-8', newline='\n') as handle:
                    handle.write(''.join(f'{k}\t{t}\n' for k, t in self.done_recent))
                os.replace(temp, self.done_file)
            except OSError:
                pass  # A notice is a comfort; the download itself already finished.

    def cancelled(self, key):
        with self.lock:
            return self.jobs[key]['cancel']

    def cancel(self, key):
        with self.ready:
            job = self.jobs[key]
            if job['state'] == 'interrupted' and job.get('url'):
                job.update(cancel=True, state='cancelled')   # OMNI_DL_RESUME_V1: give up a resumable job
                self.history.save(self.jobs)
            elif job['state'] not in TERMINAL:
                job['cancel'] = True
                if key in self.pending or key != self.active or job['state'] == PAUSED:   # waiting, or paused (nothing runs it)
                    if key in self.pending:
                        self.pending.remove(key)
                    job.update(state='cancelled', pause=False)
                    self.history.save(self.jobs)
                else:
                    job['state'] = 'cancelling'
                self.ready.notify_all()

    def snapshot(self):
        with self.lock:
            return [dict(j) for j in self.jobs.values()]

    def active_summary(self):
        """OMNI_DL_PROGRESS_V1: what Omni's top bar shows ("2 ↓ 45%"): how many jobs are working or waiting
        their turn, and one overall percent (the mean of their known progress; a queued job counts 0, a job still
        inspecting its link has none yet; -1 when no job has one). Counts only: no titles, links or job ids."""
        with self.lock:
            live = [j for j in self.jobs.values() if j.get('state') not in TERMINAL and j.get('state') not in ACTIVE_SKIP]
            known = [min(100.0, max(0.0, float(j['progress']))) for j in live
                     if isinstance(j.get('progress'), (int, float)) and not isinstance(j.get('progress'), bool)]
        percent = int(sum(known) / len(known)) if known else -1
        return dict(api_version=1, active=len(live), percent=percent)

    def set_paused(self, paused):
        if type(paused) is not bool:
            raise ValueError('paused must be a boolean.')
        with self.ready:
            if not paused and self.jd_adapter.poisoned:
                raise ValueError('Java cleanup was not confirmed; the queue must stay paused until its worker is restarted.')
            self.queue_paused = paused
            self.ready.notify_all()

    def run(self, key):
        with self.ready:
            while key in self.pending:
                if self.closed:
                    return
                if self.active is None and self.pending[0] == key and not self.queue_paused:
                    self.pending.popleft()
                    self.active = key
                    break
                self.ready.wait()
            else:
                return  # Cancelled/pruned before this thread acquired its turn.
        with self.lock:
            real_job = not self.jobs[key]['demo']
        try:
            try:
                if self.cancelled(key):
                    self.update(key, state='cancelled')
                else:
                    self._run(key)
            finally:
                # Closed yt-dlp objects contain cache/extractor/traceback cycles.
                # Collect only after _run's result/error frames have unwound so
                # completed media jobs do not wait for a generation-2 collection.
                if real_job:
                    gc.collect()
        except BaseException as error:
            # A library's SystemExit or a failed collection must not strand
            # the rest of the queue. The active record stays owned until this
            # failure is recorded, so concurrent pruning cannot remove it.
            reason = self.stop_reason(key)
            self.update(key, state='cancelled' if reason == 'cancel' else PAUSED if reason == 'pause' else 'failed',
                        error='' if reason else str(error)[:800])
        finally:
            with self.ready:
                if self.jd_adapter.poisoned:
                    self.queue_paused = True
                self.active = None
                self.ready.notify_all()

    def _run(self, key):
        with self.lock:
            job = dict(self.jobs[key])
        try:
            if job['demo']:
                self.update(key, state='extracting', title='Demo media • no network request')
                start = int(job.get('progress') or 0) if job.get('resumed') else 0
                for n in range(min(100, max(0, start)), 101):
                    self.check_stop(key)
                    self.update(key, state='downloading', progress=n)
                    time.sleep(.035)
                self.update(key, state='completed', title='Demo complete • no file was downloaded')
                return
            destination = save_places.work_folder(job.get('save_place') or 'internal', self.folder, key)
            destination.mkdir(parents=True, exist_ok=True)
            self._route(key, job, destination)
        except Exception as error:
            reason = self.stop_reason(key)
            if reason == 'pause':
                self.update(key, state=PAUSED, error='', speed_bps=None, eta_seconds=None)
            else:
                # OMNI_DL_RESUME_V1: AUTO_RETRY_LIMIT is 0, so a failed job waits for the user's Retry.
                self.update(key, state='cancelled' if reason == 'cancel' else 'failed', error='' if reason else str(error)[:800])

    # ----- engine routing -------------------------------------------------
    def engine_order(self, job):
        first = job.get('engine_requested', job['engine'])
        if not job.get('auto_fallback', True):
            return [first]
        other = 'jdownloader' if first == 'ytdlp' else 'ytdlp'
        return [first, other]

    def _route(self, key, job, destination):
        order = self.engine_order(job)
        reasons = []
        for index, engine in enumerate(order):
            self.check_stop(key)
            # A fallback engine gets its own sub-folder, except JDownloader: its Java bridge always writes to
            # <downloads>/<job id> (this job's folder), so checking its file against via-jdownloader/ refused every
            # finished JD-fallback download and reported it as failed.
            target = destination if index == 0 or engine == 'jdownloader' else destination / ('via-' + engine)
            if index:
                previous = ENGINE_NAMES[order[index - 1]]
                note = f'{previous} could not take this link ({redact_urls(reasons[-1][1], 160)}). {ENGINE_NAMES[engine]} took over automatically.'
                self.update(key, engine=engine, note=note, state='extracting', progress=None,
                            title=f'Switching to {ENGINE_NAMES[engine]}')
            else:
                self.update(key, engine=engine)
            try:
                if engine == 'jdownloader':
                    if job['audio']:
                        raise EngineUnavailable('audio-only is a yt-dlp option; JDownloader keeps original files')
                    result = self._run_jdownloader(key, job, target)
                else:
                    result = self._run_ytdlp(key, job, target)
            except InterruptedError:
                raise
            except NoFallback:
                raise
            except Exception as error:
                self.check_stop(key)
                if self.jd_adapter.poisoned:
                    raise RuntimeError('Java cleanup was not confirmed; restart its isolated worker.') from error
                message = classify_failure(error)  # Raises NoFallback for DRM/full disk.
                reasons.append((engine, message))
                continue
            how = result.get('via', ENGINE_NAMES[engine])
            if index:
                note = f'Downloaded by {how} after {ENGINE_NAMES[order[0]]} could not take it ({redact_urls(reasons[0][1], 160)}).'
            else:
                note = f'Downloaded by {how}.'
            filepath = result.get('filepath', '')
            if job.get('save_place') and filepath:
                # OMNI_DL_SAVE_V1: move the finished file to the chosen place under a free name.
                self.update(key, state='processing', progress=100, title='Saving the file')
                filepath = str(save_places.publish(filepath, job['save_place'], self.folder, job.get('save_folder'), job.get('save_name')))
                note += ' Saved to ' + filepath + '.'
            self.update(key, state='completed', progress=100, filepath=filepath, note=note[:400])
            return
        summary = ' | '.join(f'{ENGINE_NAMES[name]}: {redact_urls(message, 300)}' for name, message in reasons)
        if len(order) == 1:
            summary += ' | Automatic engine switching was off for this job.'
        raise RuntimeError(('No engine could download this link. ' + summary)[:800])

    def _run_jdownloader(self, key, job, destination):
        self.update(key, state='extracting', title='Starting JDownloader')
        if self.jd_lifecycle is not None:
            try:
                self.jd_lifecycle.ensure_started()
            except Exception as error:
                raise EngineUnavailable('JDownloader could not start: ' + str(error)[:200]) from error
        refresh_ready = getattr(self.jd_adapter, 'refresh_ready', None)
        if refresh_ready is not None:
            refresh_ready()
        if self.cancelled(key):
            raise InterruptedError('Cancelled')
        if self.jd_adapter.capabilities().get('jdownloader') is not True:
            raise EngineUnavailable('JDownloader is not ready')
        destination.mkdir(parents=True, exist_ok=True)
        result = self.jd_adapter.download(key, job['url'], destination,
            lambda changes: self.update(key, **changes), lambda: self.cancelled(key))
        if self.cancelled(key):
            raise InterruptedError('Cancelled')
        return dict(filepath=result['filepath'], via='JDownloader')

    def ytdlp_adapter(self):
        return NativePythonYtdlpAdapter if importlib.util.find_spec('_omni_native') is not None else PythonYtdlpAdapter

    def _run_ytdlp(self, key, job, destination):
        limiter = RateLimiter(self.policy.rate)
        downloaded, totals, expected = {}, {}, {}
        place = job.get('save_place') or 'internal'
        resumed = bool(job.get('resumed'))
        def hook(data):
            self.check_stop(key)   # cancel, or OMNI_DL_RESUME_V1 pause: stop here, keeping partial files
            if not save_places.still_there(place):
                raise NoFallback('The USB drive was disconnected during the download.')
            name = str(data.get('filename') or 'stream')
            count = max(0, int(data.get('downloaded_bytes') or 0))
            # A resumed stream first reports the bytes it already had; those are not charged to the rate limit again.
            before = downloaded.get(name, count if resumed else 0)
            try:
                limiter.charge(count if count < before else count - before, lambda: self.stop_reason(key) is not None)
            except InterruptedError:
                self.check_stop(key)
                raise
            downloaded[name] = count
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            if total:
                totals[name] = int(total)
            # OMNI_DL_SAVE_V1: one count over all the streams of the job (video + audio), not a percent that
            # restarts when the audio stream begins. The expected total comes from the chosen formats when known.
            done = sum(downloaded.values())
            whole = max(expected.get('size') or 0, sum(totals.values())) or None
            speed = data.get('speed')
            speed = int(speed) if isinstance(speed, (int, float)) and speed > 0 else None
            eta = int((whole - done) / speed) if whole and speed and whole > done else None
            progress = min(100, int(100 * done / whole)) if whole else None
            self.update(key, state='downloading' if data['status'] == 'downloading' else 'processing', progress=progress,
                        downloaded_bytes=done, total_bytes=whole, speed_bps=speed, eta_seconds=eta)
        def metadata(info):
            self.update(key, title=str(info.get('title') or 'Media')[:300])
            size = expected_size(info)
            if size:
                expected['size'] = size
                self.update(key, total_bytes=size)
                free = save_places.usage(destination)[0]
                if free is not None and free < size + save_places.MARGIN:
                    raise NoFallback('Not enough free space: this download needs about %s and the drive has %s free.'
                                     % (human_bytes(size), human_bytes(free)))
        if job.get('direct'):
            # OMNI_FILE_DOWNLOADS_V1: an original file goes straight to the direct download (yt-dlp not needed).
            self.update(key, state='extracting', title='Downloading the file')
            destination.mkdir(parents=True, exist_ok=True)
            result = DirectFileAdapter(validate=validate_http_url, referer=job.get('referer')).download(job['url'], destination, hook,
                lambda info: self.update(key, title=str(info.get('title') or 'File')[:300]),
                lambda: self.cancelled(key))
            return dict(filepath=result['filepath'], via='a direct file download')
        if importlib.util.find_spec('yt_dlp') is None:
            raise EngineUnavailable('yt-dlp is not installed in this runtime')
        self.update(key, state='extracting', title='Inspecting link')
        destination.mkdir(parents=True, exist_ok=True)
        try:
            result = self.ytdlp_adapter()().download(job['url'], destination, job['audio'], hook,
                metadata,
                lambda: self.cancelled(key),
                lambda data: self.update(key, state='processing', progress=None),
                fmt=job.get('format'), referer=job.get('referer'), preset=job.get('preset'), subtitle_lang=job.get('subtitle_lang'),
                container=job.get('container'))
        except (InterruptedError, NoFallback):
            raise
        except Exception as error:
            self.check_stop(key)
            classify_failure(error)
            if job['audio'] or job.get('preset') is not None:
                raise
            # Last yt-dlp-side step: a plain file link the extractors rejected.
            self.update(key, state='extracting', title='Trying a direct file download')
            try:
                result = DirectFileAdapter(validate=validate_http_url, referer=job.get('referer')).download(job['url'], destination / 'direct', hook,
                    lambda info: self.update(key, title=str(info.get('title') or 'File')[:300]),
                    lambda: self.cancelled(key))
            except (InterruptedError, NoFallback):
                raise
            except Exception as direct:
                raise RuntimeError(redact_urls(error, 300) + ' | direct file: ' + redact_urls(direct, 160)) from direct
            return dict(filepath=result['filepath'], via='a direct file download (yt-dlp route)')
        if self.cancelled(key):
            raise InterruptedError()
        filepath = result.get('filepath') or next((entry.get('filepath') for entry in result.get('requested_downloads', []) if entry.get('filepath')), '')
        protocols = result.get('protocols') or [entry.get('protocol') for entry in result.get('requested_downloads', [])] or []
        kind = ' (HLS)' if any(str(p).startswith('m3u8') for p in protocols) else ' (DASH)' if any('dash' in str(p) for p in protocols) else ''
        return dict(filepath=filepath, via='yt-dlp' + kind)


def expected_size(info):
    """Bytes of the chosen formats (video + audio), when yt-dlp knows them; else None."""
    if not isinstance(info, dict):
        return None
    chosen = info.get('requested_formats') or [info]
    sizes = [f.get('filesize') or f.get('filesize_approx') for f in chosen if isinstance(f, dict)]
    if not sizes or not all(isinstance(n, (int, float)) and n > 0 for n in sizes):
        return None
    return int(sum(sizes))


def human_bytes(n):
    for unit in ('bytes', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%d %s' % (n, unit)) if unit == 'bytes' else ('%.1f %s' % (n, unit))
        n /= 1024


class WorkerHTTPServer(ThreadingHTTPServer):
    """Bound request threads and idle socket lifetimes independently of media jobs."""
    request_queue_size = MAX_HTTP_REQUESTS

    def __init__(self, port, jobs):
        self.jobs = jobs
        self.saved_links = SavedLinks(jobs.history.path.with_name('saved-links.json') if jobs.history.path else None)
        self.token = secrets.token_urlsafe(32)
        self.runtime = capabilities()
        self.runtime.update(jdownloader=False, jdownloader_status='Local Java bridge not checked.', target_tested=False)
        self.runtime['probe'] = True  # OMNI_DOWNLOADS_PROBE_V5: the GUI checks links only when the worker can
        self.prober = Prober(site=_site_probe)
        self.request_slots = threading.BoundedSemaphore(MAX_HTTP_REQUESTS)
        self.library = files_library.Library(jobs.folder, self.token)  # OMNI_DL_LIBRARY_V1
        super().__init__(('127.0.0.1', port), WorkerHandler)

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            body = b'{"error":"Worker is busy; retry shortly."}'
            try:
                # Drain a small pending request before closing: unread bytes can
                # otherwise reset the TCP connection before the 503 is delivered.
                request.settimeout(.1)
                request.recv(MAX_BODY_BYTES + 8192)
                request.settimeout(1)
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n'
                                b'Connection: close\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()

    def server_close(self):
        try:
            super().server_close()
        finally:
            self.jobs_shutdown_complete = self.jobs.close()
            self.java_shutdown_complete = None
            if self.jobs_shutdown_complete and self.jobs.jd_lifecycle is not None:
                try:
                    self.java_shutdown_complete = self.jobs.jd_lifecycle.close() is True
                except Exception:
                    self.java_shutdown_complete = False


class DeadlineReader(io.RawIOBase):
    """Enforce a total header/body read deadline even when bytes keep trickling."""
    def __init__(self, raw, connection, deadline):
        self.raw = raw
        self.connection = connection
        self.deadline = deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Request read deadline exceeded')
        self.connection.settimeout(remaining)
        return self.raw.readinto(buffer)

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class WorkerHandler(BaseHTTPRequestHandler):
    MAX_STATIC_BYTES = 4 * 1024 * 1024
    ASSETS = {'/assets/app.js': ('app.js', 'text/javascript; charset=utf-8'),
     '/assets/art/abyss.webp': ('assets/art/abyss.webp', 'image/webp'),
     '/assets/art/arcade.webp': ('assets/art/arcade.webp', 'image/webp'),
     '/assets/art/atlas.webp': ('assets/art/atlas.webp', 'image/webp'),
     '/assets/art/aurora.webp': ('assets/art/aurora.webp', 'image/webp'),
     '/assets/art/bloom.webp': ('assets/art/bloom.webp', 'image/webp'),
     '/assets/art/cassette.webp': ('assets/art/cassette.webp', 'image/webp'),
     '/assets/art/cosmic.webp': ('assets/art/cosmic.webp', 'image/webp'),
     '/assets/art/kinetic.webp': ('assets/art/kinetic.webp', 'image/webp'),
     '/assets/art/loom.webp': ('assets/art/loom.webp', 'image/webp'),
     '/assets/art/metro.webp': ('assets/art/metro.webp', 'image/webp'),
     '/assets/art/prism.webp': ('assets/art/prism.webp', 'image/webp'),
     '/assets/art/relay.webp': ('assets/art/relay.webp', 'image/webp'),
     '/assets/art/sakura.webp': ('assets/art/sakura.webp', 'image/webp'),
     '/assets/art/solstice.webp': ('assets/art/solstice.webp', 'image/webp'),
     '/assets/art/tide.webp': ('assets/art/tide.webp', 'image/webp'),
     '/assets/brand-icon.png': ('assets/brand-icon.png', 'image/png'),
     '/assets/candidate-wire.js': ('assets/candidate-wire.js', 'text/javascript; charset=utf-8'),
     '/assets/favicon.svg': ('assets/favicon.svg', 'image/svg+xml'),
     '/assets/files-library.css': ('assets/files-library.css', 'text/css; charset=utf-8'),
     '/assets/files-library.js': ('assets/files-library.js', 'text/javascript; charset=utf-8'),
     '/assets/guide.css': ('assets/guide.css', 'text/css; charset=utf-8'),
     '/assets/guide.js': ('assets/guide.js', 'text/javascript; charset=utf-8'),
     '/assets/icons.svg': ('assets/icons.svg', 'image/svg+xml'),
     '/assets/job-details.css': ('assets/job-details.css', 'text/css; charset=utf-8'),
     '/assets/job-details.js': ('assets/job-details.js', 'text/javascript; charset=utf-8'),
     '/assets/landscape.svg': ('assets/landscape.svg', 'image/svg+xml'),
     '/assets/link-tools.js': ('assets/link-tools.js', 'text/javascript; charset=utf-8'),
     '/assets/nav-symbols.svg': ('assets/nav-symbols.svg', 'image/svg+xml'),
     '/assets/navigator.css': ('assets/navigator.css', 'text/css; charset=utf-8'),
     '/assets/navigator.js': ('assets/navigator.js', 'text/javascript; charset=utf-8'),
     '/assets/orbital.svg': ('assets/orbital.svg', 'image/svg+xml'),
     '/assets/player.css': ('assets/player.css', 'text/css; charset=utf-8'),
     '/assets/player.js': ('assets/player.js', 'text/javascript; charset=utf-8'),
     '/assets/production-api.js': ('assets/production-api.js', 'text/javascript; charset=utf-8'),
     '/assets/soundwave.svg': ('assets/soundwave.svg', 'image/svg+xml'),
     '/assets/styles.css': ('styles.css', 'text/css; charset=utf-8'),
     '/assets/universe-symbols.svg': ('assets/universe-symbols.svg', 'image/svg+xml'),
     '/assets/universes.css': ('assets/universes.css', 'text/css; charset=utf-8')}
    PAGES = {'/': 'index.html', '/downloads': 'index.html', '/integration-preview': 'integration/preview.html',
             '/player': 'player.html'}  # OMNI_DL_LIBRARY_V1: the player page (file id in the #fragment, never sent)
    # OMNIBLOOM_DL6_TOOLS (R3-043 presets, R3-046 library, R3-048 subtitle tools): exact allowlisted routes only.
    PAGES = dict(PAGES, **{'/tools/presets/': 'tools/presets/index.html', '/tools/subtitles/': 'tools/subtitles/index.html', '/tools/library/': 'tools/library/index.html'})
    ASSETS = dict(ASSETS, **{'/tools/library/app.js': ('tools/library/app.js', 'text/javascript; charset=utf-8'), '/tools/library/metadata.js': ('tools/library/metadata.js', 'text/javascript; charset=utf-8'), '/tools/library/style.css': ('tools/library/style.css', 'text/css; charset=utf-8'), '/tools/library/tv-controls.js': ('tools/library/tv-controls.js', 'text/javascript; charset=utf-8'), '/tools/presets/app.js': ('tools/presets/app.js', 'text/javascript; charset=utf-8'), '/tools/presets/host.js': ('tools/presets/host.js', 'text/javascript; charset=utf-8'), '/tools/presets/model.js': ('tools/presets/model.js', 'text/javascript; charset=utf-8'), '/tools/presets/style.css': ('tools/presets/style.css', 'text/css; charset=utf-8'), '/tools/presets/tv-controls.js': ('tools/presets/tv-controls.js', 'text/javascript; charset=utf-8'), '/tools/shared/components.css': ('tools/shared/components.css', 'text/css; charset=utf-8'), '/tools/shared/controller.js': ('tools/shared/controller.js', 'text/javascript; charset=utf-8'), '/tools/shared/fonts/OFL-Inter.txt': ('tools/shared/fonts/OFL-Inter.txt', 'text/plain; charset=utf-8'), '/tools/shared/fonts/OFL-Rajdhani.txt': ('tools/shared/fonts/OFL-Rajdhani.txt', 'text/plain; charset=utf-8'), '/tools/shared/fonts/inter-latin-400-normal.woff2': ('tools/shared/fonts/inter-latin-400-normal.woff2', 'font/woff2'), '/tools/shared/fonts/inter-latin-600-normal.woff2': ('tools/shared/fonts/inter-latin-600-normal.woff2', 'font/woff2'), '/tools/shared/fonts/rajdhani-latin-700-normal.woff2': ('tools/shared/fonts/rajdhani-latin-700-normal.woff2', 'font/woff2'), '/tools/shared/tokens.css': ('tools/shared/tokens.css', 'text/css; charset=utf-8'), '/tools/subtitles/app.js': ('tools/subtitles/app.js', 'text/javascript; charset=utf-8'), '/tools/subtitles/style.css': ('tools/subtitles/style.css', 'text/css; charset=utf-8'), '/tools/subtitles/subtitles.js': ('tools/subtitles/subtitles.js', 'text/javascript; charset=utf-8'), '/tools/subtitles/tv-controls.js': ('tools/subtitles/tv-controls.js', 'text/javascript; charset=utf-8')})
    # /OMNIBLOOM_DL6_TOOLS

    def setup(self):
        self.request.settimeout(REQUEST_TIMEOUT)
        super().setup()
        raw = self.rfile.detach()
        self.rfile = io.BufferedReader(DeadlineReader(raw, self.connection, time.monotonic() + REQUEST_TIMEOUT))

    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            pass  # The peer may close midway through headers or body.

    def log_message(self, *args):
        pass

    def send_body(self, status, body, content_type):
        self.connection.settimeout(REQUEST_TIMEOUT)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Length', str(len(body)))
        if content_type.startswith('text/html'):
            self.send_header('X-Frame-Options', 'SAMEORIGIN')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                             "style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'; "
                             "base-uri 'none'; object-src 'none'; form-action 'self'")
        try:
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, TimeoutError):
            pass  # A closed/expired GUI request must not affect a media job.

    def reply(self, status, value):
        self.send_body(status, json.dumps(value).encode(), 'application/json')

    def trusted_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def trusted(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        return (self.trusted_host() and self.headers.get('X-Omni-Token') == self.server.token
                and self.headers.get('Origin', origin) == origin)

    def static_bytes(self, relative):
        # Only fixed allowlist values reach this reader. Never decode user paths.
        candidate = ROOT
        parts = Path(relative).parts
        if not parts or Path(relative).is_absolute() or any(part in ('.', '..') for part in parts):
            raise ValueError('Invalid static asset path')
        for part in parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise ValueError('Symlinked static assets are not served')
        candidate.resolve(strict=True).relative_to(ROOT.resolve(strict=True))
        before = candidate.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > self.MAX_STATIC_BYTES:
            raise ValueError('Invalid static asset type or size')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(candidate, flags), 'rb') as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > self.MAX_STATIC_BYTES or (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
                raise ValueError('Static asset changed during open')
            body = handle.read(self.MAX_STATIC_BYTES + 1)
            after = os.fstat(handle.fileno())
            if len(body) != opened.st_size or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('Static asset changed or was truncated during read')
        if len(body) > self.MAX_STATIC_BYTES:
            raise ValueError('Static asset exceeds size limit')
        return body

    def do_GET(self):
        if not self.trusted_host():
            return self.reply(403, {'error': 'Forbidden host'})
        if self.path == '/api/health':
            return self.reply(200, dict(ok=True, service='omni-media-worker', api_version=1))
        if self.path == '/healthz':
            return self.reply(200, dict(service='omni-media-worker', api_version=1))
        if self.path == '/api/active':
            # OMNI_DL_PROGRESS_V1: read-only, counts only (no token: Omni's shell has none; the server listens on
            # 127.0.0.1 only and the Host check above keeps rebinding pages out).
            return self.reply(200, self.server.jobs.active_summary())
        if self.path in self.PAGES:
            try:
                body = self.static_bytes(self.PAGES[self.path]).decode('utf-8')
            except (OSError, ValueError, UnicodeError):
                return self.reply(404, {'error': 'Page unavailable'})
            return self.send_body(200, body.replace('__TOKEN__', self.server.token).encode(), 'text/html; charset=utf-8')
        if self.path in self.ASSETS:
            name, content_type = self.ASSETS[self.path]
            try:
                body = self.static_bytes(name)
            except (OSError, ValueError):
                return self.reply(404, {'error': 'Asset unavailable'})
            return self.send_body(200, body, content_type)
        if self.path == '/favicon.ico':
            return self.send_body(204, b'', 'image/x-icon')
        split = urlsplit(self.path)
        if split.path == '/api/files/stream':
            return self.files_stream(split.query)
        if not self.trusted():
            return self.reply(403, {'error': 'Forbidden'})
        if split.path == '/api/files':
            return self.files_list(split.query)
        if self.path == '/api/saved-links':
            try:
                return self.reply(200, self.server.saved_links.snapshot())
            except SavedLinksUnavailable as error:
                return self.reply(503, {'error': str(error)})
        if self.path == '/api/status':
            jobs = self.server.jobs
            self.server.runtime.update(jobs.jd_adapter.capabilities())
            lifecycle = dict(can_start=False, status='No native Java launcher configured.')
            if jobs.jd_lifecycle is not None:
                try:
                    value = jobs.jd_lifecycle.status()
                    if isinstance(value, dict):
                        # A lifecycle status is diagnostic, never a bridge token
                        # or arbitrary configuration dump sent to the GUI.
                        lifecycle = dict(can_start=value.get('can_start') is True,
                                         status=str(value.get('status', 'Native Java launcher'))[:300])
                except Exception:
                    lifecycle = dict(can_start=False, status='Native Java launcher status unavailable.')
            self.server.runtime['jd_lifecycle'] = lifecycle
            return self.reply(200, dict(api_version=1, presets_v1=True, service='omni-media-worker', jobs=jobs.snapshot(),
                                       **self.server.runtime, folder=str(jobs.folder),
                                       places=save_places.places(jobs.folder), save_v1=True,
                                       history_error=jobs.history.error, max_pending=MAX_PENDING,
                                       queue_paused=jobs.queue_paused))
        self.reply(404, {'error': 'Not found'})

    # ---- OMNI_DL_LIBRARY_V1: the library of saved files --------------------------------------------------------
    def files_list(self, query):
        try:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=8)
            if not set(params) <= {'kind', 'area', 'offset', 'limit'} or any(len(v) != 1 for v in params.values()):
                raise ValueError('Library listing takes kind, area, offset and limit once each.')
            one = {key: value[0] for key, value in params.items()}
            for key in ('offset', 'limit'):
                if key in one and not (one[key].isdigit() and len(one[key]) <= 7):
                    raise ValueError('Invalid page.')
            result = self.server.library.listing(one.get('kind', 'all'), one.get('area', 'files'),
                                                 int(one.get('offset', 0)), int(one.get('limit', 50)),
                                                 self.server.jobs.snapshot())
        except ValueError as error:
            return self.reply(400, {'error': str(error)})
        return self.reply(200, result)

    def files_stream(self, query, head=False):
        """A file from a save root, with Range support. Token header, or a signed link (a <video src> sends no headers)."""
        library = self.server.library
        try:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=4)
        except ValueError:
            params = {}
        one = {key: value[0] for key, value in params.items() if len(value) == 1}
        fid = one.get('id')
        signed = set(params) == {'id', 'exp', 'sig'} and library.check_link(fid, one.get('exp'), one.get('sig'))
        if not signed and not (set(params) == {'id'} and self.trusted()):
            return self.reply(403, {'error': 'Forbidden'})
        try:
            handle, size, kind, mime, name = library.open(fid)
        except files_library.NotFound as error:
            return self.reply(404, {'error': str(error)})
        with handle:
            try:
                byte_range = files_library.parse_range(self.headers.get('Range'), size)
            except files_library.Unsatisfiable:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%d' % size)
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            start, end = byte_range if byte_range else (0, size - 1)
            length = end - start + 1 if size else 0
            self.send_response(206 if byte_range else 200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            if byte_range:
                self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
            self.send_header('Cache-Control', 'private, no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            disposition = 'attachment' if kind == 'other' else 'inline'
            self.send_header('Content-Disposition', disposition + "; filename*=UTF-8''" + files_library.quote_name(name))
            if kind != 'pdf':
                # Chromium's PDF viewer does not run in a sandboxed document; every other type gets no script at all.
                self.send_header('Content-Security-Policy', "default-src 'none'; img-src 'self'; media-src 'self'; "
                                 "style-src 'unsafe-inline'; sandbox")
            try:
                self.end_headers()
                if head or not length:
                    return
                self.connection.settimeout(30)
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    data = handle.read(min(files_library.CHUNK, remaining))
                    if not data:
                        break  # truncated while serving: the short body tells the browser
                    self.wfile.write(data)
                    remaining -= len(data)
            except (ConnectionError, TimeoutError, OSError):
                self.close_connection = True

    def do_HEAD(self):
        split = urlsplit(self.path)
        if not self.trusted_host() or split.path != '/api/files/stream':
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        return self.files_stream(split.query, head=True)

    def files_post(self, path, body):
        library = self.server.library
        if path == '/api/files/link':
            if set(body) == {'job'}:
                job = next((j for j in self.server.jobs.snapshot() if j.get('id') == body['job']), None)
                fid = library.id_for_job(job)
            elif set(body) == {'id'}:
                fid = body['id']
            else:
                raise ValueError('A link needs only id or job.')
            info = library.describe(fid)
            url, exp = library.link(fid)
            return dict(info, url=url, expires=exp)
        if set(body) != {'id'}:
            raise ValueError('This request requires only id.')
        return getattr(library, path.rsplit('/', 1)[1])(body['id'])

    def do_POST(self):
        if not self.trusted():
            return self.reply(403, {'error': 'Forbidden'})
        try:
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                raise ValueError('One Content-Length header is required; chunked requests are unsupported.')
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError('Invalid request length')
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete request body')
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError('Request must be a JSON object')
            if self.path == '/api/saved-links':
                if set(body) != {'url', 'request_id'}:
                    raise ValueError('Saved-link request requires only url and request_id.')
                result = self.server.saved_links.save(body['url'], body['request_id'])
                return self.reply(201 if result['created'] else 200, result)
            if self.path == '/api/saved-links/delete':
                if set(body) != {'id'}:
                    raise ValueError('Saved-link deletion requires only id.')
                return self.reply(200, self.server.saved_links.delete(body['id']))
            if self.path == '/api/jobs':
                key = self.server.jobs.create(body['url'], body.get('demo', True), body.get('audio', False), body.get('request_id'),
                                              body.get('engine', 'ytdlp'), body.get('auto_fallback', True),
                                              body.get('quality'), body.get('referer'), body.get('preset'), body.get('subtitle_lang'),
                                              body.get('container'), body.get('save_place'), body.get('save_folder'), body.get('save_name'),
                                              body.get('direct', False))
                return self.reply(201, {'id': key})
            if self.path == '/api/probe':
                # OMNI_DOWNLOADS_PROBE_V5: read-only check of one grabbed link (public hosts only).
                if not set(body) <= {'url', 'referer', 'deep'} or 'url' not in body:
                    raise ValueError('Probe requires url, with optional referer and deep.')
                validate_http_url(body['url'])
                referer = body.get('referer')
                if referer is not None:
                    validate_http_url(referer)
                deep = body.get('deep', False)
                if type(deep) is not bool:
                    raise ValueError('deep must be a boolean.')
                return self.reply(200, self.server.prober.probe(body['url'], referer, deep))
            if self.path == '/api/cancel':
                self.server.jobs.cancel(body['id'])
                return self.reply(200, {'ok': True})
            if self.path in ('/api/jobs/pause', '/api/jobs/resume', '/api/jobs/retry'):
                # OMNI_DL_RESUME_V1: {id} only; the job keeps the choices it was created with.
                if set(body) != {'id'}:
                    raise ValueError('This request requires only id.')
                action = self.path.rsplit('/', 1)[1]
                state = getattr(self.server.jobs, action)(body['id'])
                return self.reply(200, {'ok': True, 'id': body['id'], 'state': state})
            if self.path in ('/api/files/link', '/api/files/trash', '/api/files/restore', '/api/files/delete'):
                try:
                    return self.reply(200, self.files_post(self.path, body))
                except files_library.NotFound as error:
                    return self.reply(404, {'error': str(error)})
                except OSError:
                    return self.reply(409, {'error': 'The file could not be changed. Check the drive and try again.'})
            if self.path == '/api/queue':
                self.server.jobs.set_paused(body['paused'])
                return self.reply(200, {'queue_paused': self.server.jobs.queue_paused})
            self.reply(404, {'error': 'Not found'})
        except TimeoutError:
            self.reply(408, {'error': 'Request body timed out'})
        except SavedLinksUnavailable as error:
            self.reply(503, {'error': str(error)})
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            self.reply(400, {'error': str(error)})


def _site_probe(url):
    """The page check uses the same yt-dlp setup as downloads (JS challenge provider included)."""
    from adapters import install_challenge_provider
    install_challenge_provider()
    return site_probe(url)


def make_server(port=0, folder=None, state_file=None, jd_adapter=None, jd_lifecycle=None):
    if state_file is not None and Path(state_file).name == 'saved-links.json':
        raise ValueError('Download history must use a different filename from saved-links.json.')
    jobs = Jobs(folder or ROOT / 'downloads', state_file, jd_adapter, jd_lifecycle)
    try:
        return WorkerHTTPServer(port, jobs)
    except BaseException:
        jobs.close()
        raise


if __name__ == '__main__':
    server = make_server(int(os.environ.get('OMNI_PROTOTYPE_PORT', '8765')))
    print(f'Omni local prototype: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
