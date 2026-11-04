"""Refresh an owned Java ready file without launching or discovering anything.

The local native lifecycle owner creates/deletes this file. Its existence alone
never establishes availability: authenticated health.ready=true is required.
An active job keeps the original endpoint/token through cancellation/release.
"""
import json
from pathlib import Path
import re
import threading
import time
from jd_adapter import JDownloaderAdapter


class ReadyFileJDownloaderAdapter(JDownloaderAdapter):
    def __init__(self, path, timeout=2, job_timeout=1800):
        super().__init__(timeout=timeout, job_timeout=job_timeout)
        self.ready_path = Path(path)
        self._ready_lock = threading.Lock()
        self._active_download = False
        self._config_at = None
        self._config_error = 'Native Java worker has not supplied a ready file.'

    def _refresh_locked(self, force=False):
        if self._active_download or self.poisoned:
            return
        now = time.monotonic()
        if not force and self._config_at is not None and now-self._config_at < 3:
            return
        self._config_at = now
        candidate = None
        try:
            if self.ready_path.is_symlink():
                raise ValueError('A symbolic-link Java ready file is unsupported.')
            with self.ready_path.open('rb') as source:
                raw = source.read(8193)
            if len(raw) > 8192:
                raise ValueError('Java ready file exceeds its limit.')
            value = json.loads(raw)
            if not isinstance(value, dict) or type(value.get('protocol')) is not int or value['protocol'] != 2:
                raise ValueError('Java ready file has an unsupported protocol.')
            if (not isinstance(value.get('session'), str)
                    or re.fullmatch(r'[0-9a-f]{32}', value['session']) is None
                    or not isinstance(value.get('install_id'), str)
                    or re.fullmatch(r'[A-Za-z0-9._-]{1,128}', value['install_id']) is None
                    or type(value.get('native_pid')) is not int or value['native_pid'] <= 0):
                raise ValueError('Java ready file has an invalid native identity.')
            # Constructor performs exact loopback/port/token validation.
            checked = JDownloaderAdapter(value)
            candidate = dict(checked.config)
            self._config_error = ''
        except FileNotFoundError:
            self._config_error = 'Native Java worker is not running.'
        except (OSError, ValueError, RecursionError):
            self._config_error = 'Native Java ready file is invalid or unavailable.'
        if candidate != self.config:
            self.config = candidate
            self._health = None
            self._health_at = 0

    def capabilities(self):
        with self._ready_lock:
            self._refresh_locked()
            error = self._config_error
            # Keep configuration bound throughout the inherited health request.
            value = super().capabilities()
        if self.config is None and not self.poisoned:
            value['jdownloader_status'] = error
        return value

    def call(self, action, **parameters):
        value = super().call(action, **parameters)
        if action == 'health' and self.config is not None:
            if (value.get('session') != self.config['session']
                    or value.get('install_id') != self.config['install_id']
                    or type(value.get('native_pid')) is not int
                    or value['native_pid'] != self.config['native_pid']):
                raise ValueError('Authenticated Java native identity differs from readiness.')
            if value.get('draining') is True or value.get('startup_error'):
                raise ValueError('Native Java is draining or its startup failed.')
        return value

    def refresh_ready(self):
        """Discard the availability cache after an owned native launch finished."""
        with self._ready_lock:
            self._refresh_locked(force=True)
            self._health = None
            self._health_at = 0

    def download(self, key, url, destination, update, cancelled):
        with self._ready_lock:
            if self._active_download:
                raise RuntimeError('The Java adapter already owns a download.')
            self._refresh_locked(force=True)
            if super().capabilities().get('jdownloader') is not True:
                raise RuntimeError('Native JDownloader is not ready.')
            self._active_download = True
        try:
            return super().download(key, url, destination, update, cancelled)
        finally:
            with self._ready_lock:
                self._active_download = False
                self._config_at = None
