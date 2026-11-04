"""Common on-console API; native runtime launch is an optional owned lifecycle hook.

downloader-1: every real job walks an engine route. The user's go-to engine is
tried first; on failure the other engine takes the job automatically (yt-dlp
route: site extractor -> generic extractor -> direct file). DRM, full storage,
cancellation and an unconfirmed Java cleanup never fall through.
"""
import importlib.util
import gc
from collections import deque
from adapters import (PythonYtdlpAdapter, NativePythonYtdlpAdapter, DirectFileAdapter, NoFallback,
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
from history import History, TERMINAL, MAX_JOBS, MAX_PENDING
from saved_links import SavedLinks, SavedLinksUnavailable, validate_http_url
from jd_adapter import JDownloaderAdapter
from schedule_policy import Policy, RateLimiter
from presets import preset_options
from probe import Prober, quality_format, site_probe  # OMNI_DOWNLOADS_PROBE_V5

ROOT = Path(__file__).resolve().parent
MAX_HTTP_REQUESTS = 16
REQUEST_TIMEOUT = 5
MAX_BODY_BYTES = 8192
ENGINE_NAMES = {'ytdlp': 'yt-dlp', 'jdownloader': 'JDownloader'}


class Jobs:
    def __init__(self, folder, state_file=None, jd_adapter=None, jd_lifecycle=None, policy=None):
        self.folder = Path(folder)
        self.policy = policy or Policy(Path(state_file).with_name("schedule.json") if state_file else None)
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

    def create(self, url, demo, audio=False, request_id=None, engine='ytdlp', auto_fallback=True, quality=None, referer=None, preset=None, subtitle_lang=None):
        if not isinstance(url, str) or len(url) > 4096 or type(demo) is not bool or type(audio) is not bool:
            raise ValueError('URL must be text (up to 4096 characters); demo and audio must be booleans.')
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
        if referer is not None:
            validate_http_url(referer)
        choice = json.dumps({'quality':quality,'preset':preset,'subtitle_lang':subtitle_lang},sort_keys=True) if quality is not None or preset is not None else ''
        if request_id is not None and (not isinstance(request_id, str) or len(request_id) != 32
                                       or any(c not in '0123456789abcdef' for c in request_id)):
            raise ValueError('request_id must contain 32 lowercase hexadecimal characters.')
        if not demo and engine == 'ytdlp' and not auto_fallback and importlib.util.find_spec('yt_dlp') is None:
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
            if sum(j['state'] not in TERMINAL for j in self.jobs.values()) >= MAX_PENDING:
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
                                 format=fmt, quality_key=choice, referer=referer, preset=preset, subtitle_lang=subtitle_lang)
            self.pending.append(key)
            self.history.save(self.jobs)
            if self.dispatcher is None:
                try:
                    dispatcher = threading.Thread(target=self.dispatch, name='omni-download-dispatcher', daemon=True)
                    dispatcher.start()
                    self.dispatcher = dispatcher
                except RuntimeError as error:
                    self.pending.remove(key)
                    self.jobs[key].update(state='failed', error='Could not start the download worker.')
                    self.history.save(self.jobs)
                    raise ValueError('Could not start the download worker.') from error
            self.ready.notify_all()
        return key

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
        with self.lock:
            job = self.jobs[key]
            if job['cancel']:
                if values.get('state') == 'completed':
                    values.update(state='cancelled', error='')
                elif values.get('state') not in TERMINAL:
                    values['state'] = 'cancelling'
            job.update(values)
            if values.get('state') in TERMINAL:
                self.history.save(self.jobs)

    def cancelled(self, key):
        with self.lock:
            return self.jobs[key]['cancel']

    def cancel(self, key):
        with self.ready:
            job = self.jobs[key]
            if job['state'] not in TERMINAL:
                job['cancel'] = True
                if key in self.pending:
                    self.pending.remove(key)
                    job['state'] = 'cancelled'
                    self.history.save(self.jobs)
                else:
                    job['state'] = 'cancelling'
                self.ready.notify_all()

    def snapshot(self):
        with self.lock:
            return [dict(j) for j in self.jobs.values()]

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
            cancelled = self.cancelled(key)
            self.update(key, state='cancelled' if cancelled else 'failed',
                        error='' if cancelled else str(error)[:800])
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
                for n in range(101):
                    if self.cancelled(key):
                        raise InterruptedError()
                    self.update(key, state='downloading', progress=n)
                    time.sleep(.035)
                self.update(key, state='completed', title='Demo complete • no file was downloaded')
                return
            destination = self.folder / key
            destination.mkdir(parents=True, exist_ok=True)
            self._route(key, job, destination)
        except Exception as error:
            self.update(key, state='cancelled' if self.cancelled(key) else 'failed', error='' if self.cancelled(key) else str(error)[:800])

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
            if self.cancelled(key):
                raise InterruptedError('Cancelled')
            target = destination if index == 0 else destination / ('via-' + engine)
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
                if self.cancelled(key):
                    raise InterruptedError('Cancelled') from error
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
            self.update(key, state='completed', progress=100, filepath=result.get('filepath', ''), note=note[:400])
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
        downloaded = {}
        def hook(data):
            if self.cancelled(key):
                raise InterruptedError('Cancelled')
            name = str(data.get('filename') or 'stream')
            count = max(0, int(data.get('downloaded_bytes') or 0))
            before = downloaded.get(name, 0)
            limiter.charge(count if count < before else count - before, lambda: self.cancelled(key))
            downloaded[name] = count
            total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
            progress = min(100, int(100 * data.get('downloaded_bytes', 0) / total)) if total else None
            self.update(key, state='downloading' if data['status'] == 'downloading' else 'processing', progress=progress)
        if importlib.util.find_spec('yt_dlp') is None:
            raise EngineUnavailable('yt-dlp is not installed in this runtime')
        self.update(key, state='extracting', title='Inspecting link')
        destination.mkdir(parents=True, exist_ok=True)
        try:
            result = self.ytdlp_adapter()().download(job['url'], destination, job['audio'], hook,
                lambda info: self.update(key, title=str(info.get('title') or 'Media')[:300]),
                lambda: self.cancelled(key),
                lambda data: self.update(key, state='processing', progress=None),
                fmt=job.get('format'), referer=job.get('referer'), preset=job.get('preset'), subtitle_lang=job.get('subtitle_lang'))
        except (InterruptedError, NoFallback):
            raise
        except Exception as error:
            if self.cancelled(key):
                raise InterruptedError('Cancelled') from error
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
    ASSETS = {'/assets/action-motion.css': ('assets/action-motion.css', 'text/css; charset=utf-8'),
     '/assets/app.js': ('app.js', 'text/javascript; charset=utf-8'),
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
     '/assets/production-api.js': ('assets/production-api.js', 'text/javascript; charset=utf-8'),
     '/assets/soundwave.svg': ('assets/soundwave.svg', 'image/svg+xml'),
     '/assets/styles.css': ('styles.css', 'text/css; charset=utf-8'),
     '/assets/universe-symbols.svg': ('assets/universe-symbols.svg', 'image/svg+xml'),
     '/assets/universes.css': ('assets/universes.css', 'text/css; charset=utf-8')}
    PAGES = {'/': 'index.html', '/downloads': 'index.html', '/integration-preview': 'integration/preview.html'}
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
        if self.path == '/healthz':
            return self.reply(200, dict(service='omni-media-worker', api_version=1))
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
        if not self.trusted():
            return self.reply(403, {'error': 'Forbidden'})
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
                                       history_error=jobs.history.error, max_pending=MAX_PENDING,
                                       queue_paused=jobs.queue_paused))
        self.reply(404, {'error': 'Not found'})

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
                                              body.get('quality'), body.get('referer'), body.get('preset'), body.get('subtitle_lang'))
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
