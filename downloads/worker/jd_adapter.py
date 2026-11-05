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
# Audit JD-03: JDownloader opens its own connections (file-host plugins, their
# redirects and subrequests). The bridge must say it confines all of them to the
# same public-address-only policy as the yt-dlp guard before Omni hands it a
# link; until a bridge reports this exact policy, the engine stays switched off.
EGRESS_POLICY = 'omni-public-only-v1'
HELD_STATUS = ("JDownloader is held back: its own connections aren't covered by "
               "Omni's private-address check yet. yt-dlp keeps working.")


def check_submitted_url(url, resolver=None):
    """The submitted link itself must point at a public address (JD-03)."""
    import probe
    try:
        parts, port = probe.check_url(url)
        probe.resolve_within(resolver or probe.public_address, parts.hostname, port, probe.SOCKET_TIMEOUT)
    except probe.Refused as error:
        raise ValueError('JDownloader was not given this link: local or private address.') from error
    except (TimeoutError, probe.Problem) as error:
        raise ValueError("JDownloader was not given this link: its address couldn't be checked.") from error


def owned_output(destination, value):
    """Accept a finished file only if it is a regular file inside this job's
    folder, reached without any symbolic link (JD-03). Returns its path."""
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('Java worker returned a missing or unowned output path.')
    root = Path(os.path.abspath(destination))
    path = Path(os.path.abspath(os.path.join(root, value)))
    if path == root or not path.is_relative_to(root) or root.is_symlink():
        raise ValueError('Java worker returned a missing or unowned output path.')
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Java worker returned an output reached through a symbolic link.')
    if not path.is_file() or Path(os.path.realpath(path)) != Path(os.path.realpath(root)) / path.relative_to(root):
        raise ValueError('Java worker returned a missing or unowned output path.')
    return path


class JDownloaderAdapter:
    resolver = None  # None: probe.public_address (tests inject a fake resolver)

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
                    guarded = value.get('egress_policy') == EGRESS_POLICY
                    self._health = dict(jdownloader=value.get('ready') is True and guarded,
                                        jdownloader_status=(str(value.get('status', 'Local Java worker'))[:300] if guarded else HELD_STATUS),
                                        target_tested=False)
                except (OSError, ValueError, RuntimeError) as error:
                    self._health = dict(jdownloader=False, jdownloader_status='Local Java worker unavailable: ' + str(error)[:200], target_tested=False)
                self._health_at = time.monotonic()
            return dict(self._health)

    def download(self, key, url, destination, update, cancelled):
        if self.poisoned:
            raise RuntimeError('Java cleanup was not confirmed; restart its isolated worker.')
        if self.capabilities().get('jdownloader') is not True:
            raise RuntimeError(self.capabilities().get('jdownloader_status') or HELD_STATUS)
        check_submitted_url(url, self.resolver)
        destination = Path(destination)
        if destination.is_symlink():
            raise ValueError('The job folder must not be a symbolic link.')
        destination = destination.resolve()
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
                    return dict(filepath=str(owned_output(destination, value.get('filepath'))))
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
