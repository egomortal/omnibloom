"""Desktop and optional native-binding implementations of the worker boundary.

The staged PS5 candidate passed bounded native QuickJS/EJS, direct HTTPS yt-dlp
download, tiny loopback DASH/remux and worker API tests; see PS5-WORKER.md for
receipt and artifact scope. Local tests also cover native bindings and the GUI.
Actual Omni GUI/playback integration and live target YouTube extraction remain
unproven; the recorded YouTube attempt was blocked at DNS/TCP connection.
Desktop FFmpeg subprocess execution is explicitly not a console implementation.

downloader-1 (2026-10-26): the native path also accepts HLS through yt-dlp's
pure-Python HlsFD (segments fetched and concatenated in-process, AES-128 via
yt-dlp's built-in AES), DASH segment generators, a generic-extractor retry when
a site extractor fails, and a bounded direct-file fallback. No ffmpeg
executable or subprocess is used; FFmpegFD delegation is refused explicitly.
"""
from presets import preset_options
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
DEPS = ROOT / '.deps'
if DEPS.is_dir() and str(DEPS) not in sys.path:
    sys.path.insert(0, str(DEPS))


# OMNI_EGRESS_GUARD_V2 (downloader-8, audit DW-01 download side): the download itself, not only the
# deep check, is confined to public addresses. Every yt-dlp download (site extractor, generic page,
# HLS/DASH fragments, the live-playlist check) and every direct file download goes through the
# loopback egress guard (egress_guard.py), which allows public unicast addresses only and pins each
# connection to the address it checked (so DNS can't switch it to a LAN address in between). The
# submitted link is also checked up front, so a local/private link gets a clear message.
PRIVATE_LINK = 'This link points at a local or private address; Omni only downloads from the internet.'


def guard_url():
    """The worker's shared loopback egress guard (started on first use)."""
    import probe
    from egress_guard import shared_guard
    return shared_guard(probe.public_address).url


def check_public_link(url):
    """Refuse a link whose host resolves to a local/private address (before any request is made)."""
    import probe
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise NoFallback('Enter an HTTP or HTTPS link.')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    try:
        probe.resolve_within(probe.public_address, parts.hostname, port, probe.SOCKET_TIMEOUT)
    except probe.Refused as error:
        raise NoFallback(PRIVATE_LINK) from error
    except TimeoutError as error:
        raise RuntimeError("The site's address couldn't be looked up in time.") from error
    except probe.Problem as error:
        raise RuntimeError(str(error) or "The site's address could not be found.") from error


def guard_options(options):
    """Route yt-dlp through the guard; drop the per-request proxy overrides that could bypass it."""
    options['proxy'] = guard_url()
    options['geo_verification_proxy'] = None
    headers = options.get('http_headers')
    if isinstance(headers, dict):
        options['http_headers'] = {k: v for k, v in headers.items() if str(k).lower() != 'ytdl-request-proxy'}
    return options


class NoFallback(Exception):
    """An outcome another engine must not retry (DRM, disk full, cancellation)."""


class EngineUnavailable(RuntimeError):
    """The engine could not start for this job; another engine may take it."""


_URL_TEXT = re.compile(r'https?://\S+', re.I)


def redact_urls(text, limit=300):
    """Short, URL-free reason text that is safe for persisted history notes."""
    text = _URL_TEXT.sub('<link>', str(text or ''))
    text = re.sub(r'^\s*ERROR:\s*', '', text)
    text = ' '.join(text.split())
    return text[:limit]


def classify_failure(error):
    """Raise NoFallback for errors no other engine may work around."""
    if isinstance(error, (InterruptedError, NoFallback)):
        raise error
    message = str(error)
    lowered = redact_urls(message, 2000).lower()
    if re.search(r'\b(?:drm|widevine|playready|fairplay)\b', lowered):
        raise NoFallback('This media is DRM-protected. Omni does not download protected streams.') from error
    if isinstance(error, OSError) and getattr(error, 'errno', None) == 28 or 'no space left' in lowered:
        raise NoFallback('The download storage is full.') from error
    return message


class QuickJSAdapter:
    def evaluate(self, source):
        if importlib.util.find_spec('_omni_native') is not None:
            import _omni_native
            return _omni_native.evaluate(source)
        import quickjs
        context = quickjs.Context()
        context.set_memory_limit(512 * 1024 * 1024)
        context.set_max_stack_size(4 * 1024 * 1024)
        context.set_time_limit(30)
        # Keep output inside the JS context: no filesystem/network/host callbacks.
        context.eval('globalThis.__omniOutput=[]; globalThis.console={log:(...v)=>__omniOutput.push(v.map(String).join(" "))};')
        context.eval(source)
        return '\n'.join(json.loads(context.eval('JSON.stringify(__omniOutput)')))


def _register_challenge_provider():
    """Pinned EJS internal API adapter, independent of yt-dlp's subprocess runner."""
    global _provider
    if _provider is not None:
        return _provider
    from yt_dlp.extractor.youtube.jsc._builtin.ejs import EJSBaseJCP
    from yt_dlp.extractor.youtube.jsc.provider import register_provider, register_preference
    from yt_dlp.extractor.youtube.pot._provider import BuiltinIEContentProvider
    from yt_dlp.utils._jsruntime import JsRuntimeInfo

    @register_provider
    class OmniEmbeddedJCP(EJSBaseJCP, BuiltinIEContentProvider):
        PROVIDER_NAME = 'omni_embedded'
        JS_RUNTIME_NAME = 'omni_embedded'

        @property
        def runtime_info(self):
            if importlib.util.find_spec('quickjs') is None and importlib.util.find_spec('_omni_native') is None:
                return None
            # The Python wheel doesn't expose its underlying engine version.
            return JsRuntimeInfo('omni_embedded', '<embedded>', 'unknown', ())

        def _run_js_runtime(self, stdin):
            return QuickJSAdapter().evaluate(stdin)

    @register_preference(OmniEmbeddedJCP)
    def prefer_embedded(provider, requests):
        return 2000
    _provider = OmniEmbeddedJCP
    return _provider


class FFmpegAdapter:
    def __init__(self):
        self.executable = os.environ.get('OMNI_FFMPEG') or shutil.which('ffmpeg')
        if not self.executable:
            try:
                import imageio_ffmpeg
                self.executable = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                pass

    def run(self, arguments, timeout=60, cwd=None, cancelled=None):
        if not self.executable:
            raise RuntimeError('No local FFmpeg executable available')
        if cancelled and cancelled():
            raise InterruptedError('Cancelled')
        command = [self.executable, '-nostdin', '-hide_banner', *arguments]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
        deadline = time.monotonic() + timeout
        try:
            while True:
                if cancelled and cancelled():
                    raise InterruptedError('Cancelled')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.communicate()
            raise
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        if result.returncode:
            raise RuntimeError('FFmpeg failed: ' + result.stderr[-1600:])
        return result

    def merge(self, video, audio, output, cancelled=None):
        output = Path(output)
        if output.exists():
            raise ValueError('Output already exists')
        if importlib.util.find_spec('_omni_native') is not None:
            import _omni_native
            _omni_native.merge(str(video), str(audio), str(output), cancelled)
            return output
        descriptor, name = tempfile.mkstemp(prefix='.omni-merge-', suffix=output.suffix, dir=output.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            self.run(['-i', str(video), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
                      '-c', 'copy', '-y', str(temporary)], cancelled=cancelled)
            if cancelled and cancelled():
                raise InterruptedError('Cancelled')
            # Publish without replacing a destination created while remuxing.
            os.link(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return output


_provider = None
_provider_lock = threading.Lock()


def install_challenge_provider():
    with _provider_lock:
        return _register_challenge_provider()


class PythonYtdlpAdapter:
    def options(self, folder, audio, hook, postprocess_hook=lambda _: None, fmt=None, referer=None, preset=None, subtitle_lang=None):
        global _provider
        import yt_dlp
        install_challenge_provider()
        ffmpeg = FFmpegAdapter()
        options = dict(outtmpl=str(Path(folder) / '%(title).120s [%(id)s].%(ext)s'),
                    noplaylist=True, restrictfilenames=True, quiet=True, no_warnings=True,
                    socket_timeout=20, retries=2, cachedir=False,
                    progress_hooks=[hook], postprocessor_hooks=[postprocess_hook], noprogress=True,
                    format=fmt or ('bestaudio' if audio else 'bestvideo+bestaudio/best'),
                    ffmpeg_location=ffmpeg.executable, js_runtimes={})
        options.update(preset_options(preset, subtitle_lang))
        if referer:
            # OMNI_DOWNLOADS_PROBE_V5: the grabbing page's origin, as the browser itself sends it.
            options['http_headers'] = {'Referer': referer}
        return guard_options(options)   # OMNI_EGRESS_GUARD_V2: always last, so nothing above can remove it

    @staticmethod
    def extract(ydl, url, cancelled=lambda: False, attempts=None):
        """Matching site extractor first, then yt-dlp's generic page extractor.

        yt-dlp itself stops at the first suitable extractor; a broken or
        changed site extractor would otherwise hide media the generic
        extractor (video tags, JSON-LD, embedded HLS/DASH manifests) can find.
        """
        import yt_dlp
        attempts = attempts if attempts is not None else []
        try:
            info = ydl.extract_info(url, download=False)
            attempts.append('yt-dlp extractor')
            return info
        except yt_dlp.utils.DownloadError as error:
            classify_failure(error)
            message = str(error)
            if cancelled():
                raise InterruptedError('Cancelled')
            if '[generic]' in message.lower() or 'unsupported url' in message.lower():
                attempts.append('yt-dlp generic')
                raise
            first = error
        attempts.append('yt-dlp extractor')
        try:
            info = ydl.extract_info(url, download=False, force_generic_extractor=True)
            attempts.append('yt-dlp generic')
            return info
        except yt_dlp.utils.DownloadError as error:
            classify_failure(error)
            attempts.append('yt-dlp generic')
            raise yt_dlp.utils.DownloadError(
                'Site extractor: ' + redact_urls(first, 240) + ' | generic: ' + redact_urls(error, 240)) from error

    def download(self, url, folder, audio=False, hook=lambda _: None, metadata=lambda _: None, cancelled=lambda: False, postprocess_hook=lambda _: None,
                 fmt=None, referer=None, preset=None, subtitle_lang=None):
        import yt_dlp
        check_public_link(url)
        options = self.options(folder, audio, hook, postprocess_hook, fmt=fmt, referer=referer, preset=preset, subtitle_lang=subtitle_lang)
        with yt_dlp.YoutubeDL(options) as ydl:
            info = self.extract(ydl, url, cancelled)
            if cancelled():
                raise InterruptedError('Cancelled')
            metadata(info)
            return ydl.process_ie_result(info, download=True)


class NativePythonYtdlpAdapter(PythonYtdlpAdapter):
    """Explicit native-binding path: download individual streams, remux via C.

    Uses pinned yt-dlp resolved-format dictionaries; never its FFmpeg subprocess
    postprocessor. Live streams/playlists and conversion are not supported here.
    HLS uses yt-dlp's in-process HlsFD; a single MPEG-TS result keeps a .ts name.
    """
    ALLOWED_PROTOCOLS = frozenset(('http', 'https', 'http_dash_segments',
                                   'http_dash_segments_generator', 'm3u8_native', 'm3u8'))
    def download(self, url, folder, audio=False, hook=lambda _: None, metadata=lambda _: None,
                 cancelled=lambda: False, postprocess_hook=lambda _: None, fmt=None, referer=None, preset=None, subtitle_lang=None):
        if importlib.util.find_spec('_omni_native') is None:
            raise RuntimeError('Native CPython binding is required')
        import yt_dlp
        check_public_link(url)
        folder = Path(folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        options = self.options(folder, audio, hook, postprocess_hook, fmt=fmt, referer=referer, preset=preset, subtitle_lang=subtitle_lang)
        _forbid_external_ffmpeg()
        # hls_prefer_native/external_downloader=native keep every HLS/DASH
        # stream on yt-dlp's in-process fragment downloaders. A missing
        # fragment fails the job instead of silently producing a gap.
        options.update(ffmpeg_location=None, fixup='never', postprocessors=[],
                       hls_prefer_native=True, external_downloader={'default': 'native'},
                       skip_unavailable_fragments=False, fragment_retries=3,
                       outtmpl=str(folder / '%(title).100s [%(id)s].f%(format_id)s.%(ext)s'))
        with yt_dlp.YoutubeDL(options) as ydl:
            info = self.extract(ydl, url, cancelled)
            if not isinstance(info, dict):
                raise ValueError('No supported media found')
            if (info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming')
                    or info.get('_type') in ('playlist', 'multi_video')):
                raise ValueError('Live streams and playlists are not supported; open one video and paste its link.')
            metadata(info)
            selection = (info.get('requested_downloads') or [info])[0]
            streams = selection.get('requested_formats') or [selection]
            if len(streams) > 2:
                raise ValueError('Native prototype supports at most one audio and one video stream')
            # HLS/RTMP and other protocols can select an external FFmpeg downloader,
            # even with postprocessing disabled. Fail before any stream starts.
            # FFmpeg-only protocols (RTMP, RTSP, f4m, ...) are refused before
            # any stream starts. 'm3u8' is rewritten to yt-dlp's native HLS.
            for stream in streams:
                protocol = str(stream.get('protocol', 'unknown'))
                if '+' in protocol or protocol not in self.ALLOWED_PROTOCOLS:
                    raise ValueError('This stream type needs FFmpeg, which the console does not have: ' + protocol[:40])
                if protocol == 'm3u8':
                    stream['protocol'] = 'm3u8_native'
                if protocol.startswith('m3u8'):
                    _refuse_live_playlist(ydl, stream)
            files = []
            for stream in streams:
                if cancelled():
                    raise InterruptedError('Cancelled')
                item = {**info, **stream}
                for field in ('requested_formats', 'requested_downloads', '__postprocessors', '_filename', 'filepath'):
                    item.pop(field, None)
                path = Path(ydl.prepare_filename(item))
                ydl.process_info(item)
                if not path.is_file():
                    raise RuntimeError('Expected downloaded stream is missing')
                if str(item.get('protocol', '')).startswith('m3u8'):
                    path = _name_transport_stream(path)
                files.append(path)
            if cancelled():
                raise InterruptedError('Cancelled')
            if len(files) == 2:
                video_index = next((i for i, stream in enumerate(streams) if stream.get('vcodec') not in (None, 'none')), None)
                if video_index is None:
                    raise ValueError('Selection has no video stream')
                output = files[video_index].with_suffix('.merged.mkv')
                postprocess_hook({'status': 'started', 'postprocessor': 'OmniNativeMerger'})
                FFmpegAdapter().merge(files[video_index], files[1 - video_index], output, cancelled)
                postprocess_hook({'status': 'finished', 'postprocessor': 'OmniNativeMerger'})
            else:
                output = _name_unknown_extension(files[0], url)
            return dict(id=info.get('id'), title=info.get('title'), filepath=str(output), native=True,
                        protocols=sorted({str(stream.get('protocol')) for stream in streams}))


def _refuse_live_playlist(ydl, stream, limit=4 * 1024 * 1024):
    """A media playlist without ENDLIST is live/event: HlsFD would save only
    the segments listed right now. Refuse instead of producing a short clip."""
    import yt_dlp
    text = stream.get('hls_media_playlist_data')
    if not isinstance(text, str):
        request = yt_dlp.networking.Request(stream['url'], headers=stream.get('http_headers') or {})
        with ydl.urlopen(request) as response:
            text = response.read(limit + 1).decode('utf-8', 'replace')
        if len(text) > limit:
            raise ValueError('HLS playlist exceeds its size limit.')
    if '#EXT-X-STREAM-INF' in text:
        return  # Master playlist URL; HlsFD resolves it to the selected media playlist.
    if '#EXT-X-ENDLIST' not in text and '#EXT-X-PLAYLIST-TYPE:VOD' not in text:
        raise ValueError('This HLS stream is live (its playlist has no end); live streams are not supported.')


def _forbid_external_ffmpeg():
    """The console has no ffmpeg executable and no subprocess support.

    yt-dlp's HlsFD hands unsupported playlists (SAMPLE-AES, live) to FFmpegFD.
    Make that an immediate, explicit error instead of a subprocess attempt.
    """
    from yt_dlp.downloader.external import FFmpegFD
    if getattr(FFmpegFD.real_download, '_omni_forbidden', False):
        return

    def refuse(self, filename, info_dict):
        raise ValueError('This stream needs FFmpeg (encrypted or live HLS), which the console does not have.')
    refuse._omni_forbidden = True
    FFmpegFD.real_download = refuse
    # HlsFD/format selection probe FFmpegFD.available(), which would spawn
    # `ffmpeg -bsfs`. Answer it directly: no executable exists on the console.
    FFmpegFD.available = classmethod(lambda cls, path=None: False)


def _name_transport_stream(path):
    """HlsFD concatenates segments into a file yt-dlp names .mp4.

    Without FFmpeg's fixup the bytes stay MPEG-TS (or raw ADTS AAC for HLS
    packed audio); give the file an honest .ts/.aac name (never replacing an
    existing file). fMP4 HLS stays .mp4.
    """
    path = Path(path)
    try:
        with path.open('rb') as source:
            head = source.read(189)
            if head[:3] == b'ID3' and len(head) >= 10:
                # HLS packed audio starts with an ID3 timestamp tag (syncsafe size).
                size = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
                source.seek(10 + size)
                audio = source.read(2)
            else:
                audio = head[:2]
    except OSError:
        return path
    suffix = None
    if len(head) == 189 and head[0] == 0x47 and head[188] == 0x47:
        suffix = '.ts'
    elif len(audio) == 2 and audio[0] == 0xFF and (audio[1] & 0xF6) == 0xF0:
        suffix = '.aac'
    if suffix and path.suffix.lower() != suffix:
        target = path.with_suffix(suffix)
        try:
            os.link(path, target)
        except OSError:
            return path
        path.unlink()
        return target
    return path


def _name_unknown_extension(path, url):
    """yt-dlp's generic extractor names non-media direct files *.unknown_video."""
    path = Path(path)
    if path.suffix != '.unknown_video':
        return path
    suffix = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).suffix
    suffix = suffix if re.fullmatch(r'\.[A-Za-z0-9]{1,8}', suffix or '') else '.bin'
    target = path.with_suffix(suffix)
    try:
        os.link(path, target)
    except OSError:
        return path
    path.unlink()
    return target


class DirectFileAdapter:
    """Bounded plain HTTP(S) GET of a direct file link; never a web page.

    Redirects stay HTTP(S) and are re-validated. No cookies, credentials or
    request headers from the browser are used. Output is created exclusively.
    """
    CHUNK = 256 * 1024
    RESERVE = 256 * 1024 * 1024
    MAX_REDIRECTS = 5
    PAGE_TYPES = ('text/html', 'application/xhtml+xml')
    MANIFEST_TYPES = ('mpegurl', 'dash+xml')

    def __init__(self, validate=None, timeout=20, referer=None):
        self.validate = validate
        self.timeout = timeout
        self.referer = referer

    def _opener(self):
        validate = self.validate

        class Redirects(urllib.request.HTTPRedirectHandler):
            max_redirections = DirectFileAdapter.MAX_REDIRECTS

            def redirect_request(self, request, fp, code, message, headers, newurl):
                newurl = urllib.parse.urljoin(request.full_url, newurl)
                if urllib.parse.urlsplit(newurl).scheme not in ('http', 'https'):
                    raise urllib.error.HTTPError(newurl, code, 'Redirect left HTTP(S)', headers, fp)
                if validate is not None:
                    validate(newurl)
                check_public_link(newurl)   # a clear message; the guard below enforces it either way
                return super().redirect_request(request, fp, code, message, headers, newurl)
        context = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE') or None)
        guard = guard_url()   # OMNI_EGRESS_GUARD_V2: every connection, redirects included, via the guard
        return urllib.request.build_opener(urllib.request.ProxyHandler({'http': guard, 'https': guard}),
                                           Redirects, urllib.request.HTTPSHandler(context=context))

    @staticmethod
    def _name(response, url):
        name = ''
        disposition = response.headers.get('Content-Disposition') or ''
        match = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", disposition, re.I) or re.search(r'filename\s*=\s*"?([^";]+)"?', disposition, re.I)
        if match:
            name = urllib.parse.unquote(match.group(1))
        if not name:
            name = urllib.parse.unquote(urllib.parse.urlsplit(response.geturl() or url).path.rsplit('/', 1)[-1])
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', name.replace('\\', '/').rsplit('/', 1)[-1]).strip('._')[:120]
        return name or 'download'

    def download(self, url, folder, hook=lambda _: None, metadata=lambda _: None, cancelled=lambda: False):
        folder = Path(folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        headers = {'User-Agent': 'Mozilla/5.0 (PlayStation; PlayStation 5) Omni', 'Accept': '*/*'}
        if self.referer:
            headers['Referer'] = self.referer
        check_public_link(url)
        request = urllib.request.Request(url, headers=headers)
        try:
            response = self._opener().open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            if error.msg == 'Redirect left HTTP(S)':
                raise ValueError('Direct download redirected to a non-HTTP(S) address; refused.') from error
            raise RuntimeError(f'Direct download was refused by the server (HTTP {error.code}).') from error
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as error:
            raise RuntimeError('Direct download could not connect: ' + redact_urls(getattr(error, 'reason', error), 160)) from error
        with response:
            kind = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if kind in self.PAGE_TYPES:
                raise ValueError('This link opens a web page, not a file.')
            if any(item in kind for item in self.MANIFEST_TYPES):
                raise ValueError('This link is a streaming playlist; it cannot be saved as a plain file.')
            first = response.read(min(self.CHUNK, 65536))
            if not kind and first.lstrip()[:15].lower().startswith((b'<!doctype html', b'<html')):
                raise ValueError('This link opens a web page, not a file.')
            total = response.headers.get('Content-Length')
            total = int(total) if total and total.isdigit() else None
            limit = None
            try:
                limit = shutil.disk_usage(folder).free - self.RESERVE
            except (OSError, AttributeError):
                pass
            if limit is not None and total is not None and total > limit:
                raise NoFallback('Not enough free storage for this file.')
            name = self._name(response, url)
            metadata({'title': name})
            descriptor, temporary = tempfile.mkstemp(prefix='.omni-direct-', suffix='.part', dir=folder)
            temporary = Path(temporary)
            written = 0
            try:
                with os.fdopen(descriptor, 'wb') as target:
                    chunk = first
                    while chunk:
                        if cancelled():
                            raise InterruptedError('Cancelled')
                        target.write(chunk)
                        written += len(chunk)
                        if limit is not None and written > limit:
                            raise NoFallback('Not enough free storage for this file.')
                        hook({'status': 'downloading', 'downloaded_bytes': written, 'total_bytes': total})
                        chunk = response.read(self.CHUNK)
                if total is not None and written != total:
                    raise RuntimeError('Direct download ended early.')
                output = folder / name
                stem, suffix, counter = output.stem, output.suffix, 1
                while True:
                    try:
                        os.link(temporary, output)
                        break
                    except FileExistsError:
                        counter += 1
                        if counter > 99:
                            raise
                        output = folder / f'{stem}-{counter}{suffix}'
            finally:
                temporary.unlink(missing_ok=True)
        hook({'status': 'finished', 'downloaded_bytes': written, 'total_bytes': written})
        return dict(title=name, filepath=str(output), direct=True)


def capabilities():
    ffmpeg = FFmpegAdapter()
    native = importlib.util.find_spec('_omni_native') is not None
    return dict(ytdlp=importlib.util.find_spec('yt_dlp') is not None,
                ffmpeg=native or bool(ffmpeg.executable), quickjs=native or importlib.util.find_spec('quickjs') is not None,
                backend='native-c-bindings' if native else 'desktop-python; embedded-quickjs; desktop-ffmpeg', ps5_ready=False)
