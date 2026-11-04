"""Authenticated loopback client for the prototype's real Java JD bridge.

No console discovery, deployment, cloud login or external RPC endpoint exists here.
"""
import json
import math
import os
from pathlib import Path
import socket
import struct
import threading
import time

MAX_FRAME = 65536


class JDownloaderAdapter:
    def __init__(self, config=None, timeout=2, job_timeout=180):
        self.config = config
        self.timeout = timeout
        self.job_timeout = job_timeout
        self.poisoned = False
        self._health = None
        self._health_at = 0
        self._health_lock = threading.Lock()
        if config is not None:
            if config.get('host') != '127.0.0.1' or type(config.get('port')) is not int or not 1 <= config['port'] <= 65535:
                raise ValueError('Java bridge must use an explicit IPv4 loopback endpoint.')
            token = config.get('token')
            if not isinstance(token, str) or len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
                raise ValueError('Invalid Java bridge session token.')

    @classmethod
    def from_environment(cls):
        name = os.environ.get('OMNI_JD_BRIDGE_CONFIG')
        if not name:
            return cls()
        path = Path(name)
        with path.open('rb') as source:
            raw = source.read(8193)
        if len(raw) > 8192:
            raise ValueError('Java bridge configuration exceeds the limit.')
        return cls(json.loads(raw))

    @staticmethod
    def _read(connection, count, deadline):
        result = bytearray()
        while len(result) < count:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Java bridge response deadline reached.')
            connection.settimeout(remaining)
            part = connection.recv(count-len(result))
            if not part:
                raise ConnectionError('Java bridge closed an incomplete response.')
            result.extend(part)
        return bytes(result)

    def call(self, action, **parameters):
        if self.config is None:
            raise RuntimeError('Local JDownloader bridge is not configured.')
        identity = dict(token=self.config['token'], action=action)
        if 'session' in self.config:
            identity['session'] = self.config['session']
        payload = json.dumps(dict(**identity, **parameters),
                             separators=(',', ':')).encode('utf-8')
        if len(payload) > 8192:
            raise ValueError('Java bridge request exceeds the limit.')
        deadline = time.monotonic()+self.timeout
        with socket.create_connection(('127.0.0.1', self.config['port']), timeout=self.timeout) as connection:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Java bridge connection deadline reached.')
            connection.settimeout(remaining)
            connection.sendall(struct.pack('!I', len(payload)) + payload)
            length, = struct.unpack('!I', self._read(connection, 4, deadline))
            if not 0 < length <= MAX_FRAME:
                raise ValueError('Invalid Java bridge response size.')
            response = json.loads(self._read(connection, length, deadline))
        if not isinstance(response, dict):
            raise ValueError('Invalid Java bridge response.')
        if response.get('ok') is not True:
            raise RuntimeError(str(response.get('error', 'Java bridge request failed.'))[:300])
        return response

    def capabilities(self):
        if self.config is None:
            return dict(jdownloader=False, jdownloader_status='Local Java bridge is not configured.', target_tested=False)
        if self.poisoned:
            return dict(jdownloader=False, jdownloader_status='Java cleanup was not confirmed; restart its isolated worker before continuing.', target_tested=False)
        with self._health_lock:
            if time.monotonic()-self._health_at >= 3 or self._health is None:
                try:
                    value = self.call('health')
                    self._health = dict(jdownloader=value.get('ready') is True,
                                        jdownloader_status=str(value.get('status', 'Local Java worker'))[:300], target_tested=False)
                except (OSError, ValueError, RuntimeError) as error:
                    self._health = dict(jdownloader=False, jdownloader_status='Local Java worker unavailable: ' + str(error)[:200], target_tested=False)
                self._health_at = time.monotonic()
            return dict(self._health)

    def download(self, key, url, destination, update, cancelled):
        if self.poisoned:
            raise RuntimeError('Java cleanup was not confirmed; restart its isolated worker.')
        destination = Path(destination).resolve()
        submitted = False
        terminal = False
        try:
            # A repeated submit uses the same owned ID and exact URL in Java.
            # Do not retry with a new identity after an ambiguous transport error.
            submitted = True
            self.call('submit', id=key, url=url)
            deadline = time.monotonic() + self.job_timeout
            while time.monotonic() < deadline:
                if cancelled():
                    raise InterruptedError('Cancelled')
                value = self.call('status', id=key)
                state = value.get('state')
                if state not in ('extracting', 'downloading', 'processing', 'completed', 'failed', 'cancelled'):
                    raise ValueError('Java worker returned an invalid job state.')
                progress = value.get('progress')
                if progress is not None and (type(progress) not in (int, float) or not math.isfinite(progress) or not 0 <= progress <= 100):
                    raise ValueError('Java worker returned invalid progress.')
                # The shared worker publishes terminal state only after this
                # method verifies outputs and its finally block releases JD.
                update(dict(state='processing' if state in ('completed', 'failed', 'cancelled') else state,
                            progress=progress, title=str(value.get('title') or 'JDownloader')[:300]))
                if state in ('completed', 'failed', 'cancelled'):
                    terminal = True
                    if state != 'completed':
                        raise RuntimeError(str(value.get('error') or 'JDownloader did not complete the download.')[:300])
                    filepath = Path(value.get('filepath', '')).resolve()
                    if not filepath.is_relative_to(destination) or not filepath.is_file():
                        raise ValueError('Java worker returned a missing or unowned output path.')
                    return dict(filepath=str(filepath))
                time.sleep(.25)
            raise TimeoutError('JDownloader exceeded this prototype job deadline.')
        finally:
            if submitted:
                try:
                    # Stop the private JD download controller even after its
                    # final file completed; session teardown may lag the file.
                    self.call('cancel', id=key)
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        state = self.call('status', id=key).get('state')
                        if state in ('completed', 'failed', 'cancelled'):
                            terminal = True
                            try:
                                self.call('release', id=key)
                                break
                            except RuntimeError as error:
                                if 'still active' not in str(error):
                                    raise
                        time.sleep(.1)
                    else:
                        raise RuntimeError('Java job cleanup was not confirmed.')
                except (OSError, ValueError, RuntimeError):
                    self.poisoned = True
