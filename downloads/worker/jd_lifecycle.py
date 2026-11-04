"""Owned on-console native JD launcher. No contact or launch at import.

Enabled only by a root-installed, target-accepted native-install.json. The local
PS5 hbldr service launches the native ELF; this module never starts a host child
process. A timed-out launch is ambiguous and is never retried with a new session.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import socket
import stat
import struct
import threading
import time
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

ROOT = Path('/data/omni-downloader/jdownloader')
SCHEMA = 'omni-jd-native-install/v1'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
IDENTITY = re.compile(r'[A-Za-z0-9._-]{1,128}\Z')
MANIFEST_KINDS = {'native-image', 'jdownloader'}
CRITICAL = {
    'native-image': {'java25/lib/modules', 'java25/lib/server/libjvm.so',
        'java25/release', 'java25/conf/security/java.security',
        'java25/lib/tzdb.dat', 'java25/lib/security/cacerts'},
    'jdownloader': {'runtime/Core.jar', 'runtime/JDownloader.jar',
        'runtime/classes/OmniJDownloaderBridge.class',
        'runtime/classes/org/jdownloader/api/myjdownloader/MyJDownloaderController.class'},
}


def relative_asset(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 512
            or '\\' in value or ':' in value or any(ord(c) < 32 for c in value)):
        raise ValueError('Noncanonical accepted asset path')
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in ('', '.', '..') for p in path.parts):
        raise ValueError('Noncanonical accepted asset path')
    return path


def regular_owned(root, relative):
    path = root
    parts = relative_asset(relative).parts
    for index, part in enumerate(parts):
        path = path / part
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or getattr(path, 'is_junction', lambda: False)():
            raise ValueError('Accepted asset indirection refused')
        if index < len(parts)-1 and not stat.S_ISDIR(mode):
            raise ValueError('Accepted asset ancestor is not a directory')
        if index == len(parts)-1 and not stat.S_ISREG(mode):
            raise ValueError('Accepted asset must be a regular file')
    return path


def file_hash(path):
    before = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('Accepted file changed during hash verification')
    return digest


def pinned_json(path, expected, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Accepted asset manifest hash differs')
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError('Accepted asset manifest must be a JSON object')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError('Native launcher redirect refused')


def read_json(path, maximum=8192):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Owned JSON must be a regular file')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Owned JSON exceeds its bound')
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError('Owned JSON object required')
    return value


def atomic_json(path, value):
    if path.is_symlink():
        raise ValueError('Refusing a symlink at owned JSON path')
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(8))
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class NativeLifecycle:
    def __init__(self, downloads, ready_path, *, root=ROOT, opener=None,
                 clock=time.monotonic, sleep=time.sleep):
        self.root = Path(root)
        self.downloads = Path(downloads)
        self.ready_path = Path(ready_path)
        self._opener = opener or build_opener(ProxyHandler({}), NoRedirect())
        self._clock, self._sleep = clock, sleep
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._keeper = None
        self._spec = None
        self._state = None
        self._can_start = False
        self._message = 'Native JDownloader runtime has not been accepted.'
        self._last_keepalive = 0.0
        self._prepare()

    def _prepare(self):
        try:
            if self.ready_path != self.root / 'bridge-ready.json':
                raise ValueError('Unexpected bridge-ready path')
            if not self.root.is_absolute() or self.root.is_symlink():
                raise ValueError('Native runtime root must be absolute and owned')
            if not self.downloads.is_absolute() or self.downloads.is_symlink():
                raise ValueError('Download root must be absolute and owned')
            spec = read_json(self.root / 'native-install.json')
            acceptance = spec.get('target_acceptance')
            if (spec.get('schema') != SCHEMA or spec.get('approved') is not True
                    or type(acceptance) is not dict or acceptance.get('passed') is not True
                    or not HEX64.fullmatch(str(acceptance.get('evidence_sha256', '')))):
                raise ValueError('Native target acceptance approval is absent')
            if not IDENTITY.fullmatch(str(spec.get('install_id', ''))):
                raise ValueError('Invalid native install identity')
            expected = spec.get('elf_sha256')
            size = spec.get('elf_bytes')
            if not isinstance(expected, str) or not HEX64.fullmatch(expected):
                raise ValueError('Native ELF hash required')
            if type(size) is not int or not 4096 <= size <= 512 * 1024 * 1024:
                raise ValueError('Native ELF size bound')
            seconds = spec.get('startup_seconds', 180)
            if type(seconds) is not int or not 5 <= seconds <= 600:
                raise ValueError('Native startup deadline bound')
            manifests = spec.get('asset_manifests')
            if (type(manifests) is not list or len(manifests) != 2
                    or {row.get('kind') for row in manifests if type(row) is dict} != MANIFEST_KINDS):
                raise ValueError('Pinned native-image and JDownloader manifests are required')
            for row in manifests:
                if (type(row) is not dict or set(row) != {'kind', 'path', 'sha256'}
                        or not isinstance(row['sha256'], str) or not HEX64.fullmatch(row['sha256'])):
                    raise ValueError('Accepted manifest pin shape differs')
                relative_asset(row['path'])
            self._spec = spec
            state_path = self.root / 'lifecycle-state.json'
            if state_path.exists():
                self._state = read_json(state_path)
                self._validate_state(self._state)
                if self._state['status'] != 'closed':
                    # Resume only this exact session. Never launch over an
                    # uncertain previous hbldr request or orphaned Java job.
                    self._can_start = True
                    self._message = 'Checking the existing owned Java session.'
                    return
            if self.ready_path.exists():
                raise ValueError('Unowned readiness file preserved; native launch refused')
            self._can_start = True
            self._message = 'Accepted native runtime can start on demand.'
        except (OSError, ValueError, TypeError, KeyError) as error:
            self._can_start = False
            self._message = str(error)[:220]

    def _verify_elf(self):
        path = regular_owned(self.root, 'java-worker.elf')
        if path.stat().st_size != self._spec['elf_bytes']:
            raise ValueError('Native ELF changed or is not a regular file')
        if file_hash(path) != self._spec['elf_sha256']:
            raise ValueError('Native ELF hash differs from the accepted install')

    def _verify_assets(self):
        # Expensive hashing is deliberately confined to explicit new launch.
        # A cached GUI status poll cannot start Java or read the image tree.
        if read_json(self.root / 'native-install.json') != self._spec:
            raise ValueError('Native install approval changed; reload before launch')
        self._verify_elf()
        for pin in self._spec['asset_manifests']:
            path = regular_owned(self.root, pin['path'])
            manifest = pinned_json(path, pin['sha256'], 4*1024*1024)
            kind = pin['kind']
            if kind == 'native-image':
                if (manifest.get('schema') != 'omni-java-native-image/v1'
                        or manifest.get('target_root') != str(self.root / 'native')):
                    raise ValueError('Native image manifest identity differs')
                base, prefix = self.root / 'native', 'java25'
            else:
                if (manifest.get('schema') != 'omni-jd-assets-manifest/v2'
                        or manifest.get('host_jre_included') is not False):
                    raise ValueError('Portable JDownloader manifest identity differs')
                base, prefix = self.root, 'runtime'
            rows = manifest.get('files')
            if type(rows) is not list or not 1 <= len(rows) <= 5000:
                raise ValueError('Accepted asset manifest count bound')
            names, folded, total = set(), set(), 0
            for row in rows:
                if type(row) is not dict or set(row) != {'path', 'bytes', 'sha256'}:
                    raise ValueError('Accepted asset manifest row shape differs')
                relative = relative_asset(row['path'])
                name = relative.as_posix()
                if (relative.parts[0] != prefix or len(relative.parts) < 2
                        or name.casefold() in folded or type(row['bytes']) is not int
                        or not 0 <= row['bytes'] <= 128*1024*1024
                        or not isinstance(row['sha256'], str) or not HEX64.fullmatch(row['sha256'])):
                    raise ValueError('Accepted asset manifest row invalid')
                names.add(name); folded.add(name.casefold()); total += row['bytes']
                if total > 512*1024*1024:
                    raise ValueError('Accepted asset total exceeds bound')
                asset = regular_owned(base, name)
                if asset.stat().st_size != row['bytes'] or file_hash(asset) != row['sha256']:
                    raise ValueError('Accepted asset bytes differ: ' + name)
            if not CRITICAL[kind] <= names:
                raise ValueError('Critical accepted asset absent from pinned manifest')
            if kind == 'jdownloader' and (manifest.get('file_count') != len(names) or manifest.get('asset_bytes') != total):
                raise ValueError('Portable accepted asset totals differ')
            # An extra old JAR/class can shadow a pinned class on the classpath.
            # Native image is immutable; only JD's explicitly mutable roots are
            # excluded. Every manifest-owned root still has an exact path set.
            immutable = {PurePosixPath(name).parts[1] for name in names}
            directories = {parent.as_posix() for name in names
                for parent in PurePosixPath(name).parents if parent.as_posix() != '.'}
            actual = set()
            tree = base / prefix
            for top in tree.iterdir():
                if top.is_symlink() or getattr(top, 'is_junction', lambda: False)():
                    raise ValueError('Accepted asset tree indirection refused')
                if kind == 'jdownloader' and top.name not in immutable:
                    if top.name in {'cfg', 'cache', 'logs', 'home', 'tmp', 'downloads', 'update', 'updates', 'backup', 'captchas'}:
                        continue
                pending = [top]
                while pending:
                    candidate = pending.pop()
                    if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
                        raise ValueError('Accepted asset tree indirection refused')
                    relative = candidate.relative_to(base).as_posix()
                    if candidate.is_dir():
                        if relative not in directories:
                            raise ValueError('Accepted immutable asset directory differs')
                        # Do not recursively materialize an unbounded corrupt
                        # tree. Only declared descendants can enter this stack.
                        with os.scandir(candidate) as entries:
                            for entry in entries:
                                child = Path(entry.path)
                                name = child.relative_to(base).as_posix()
                                if name not in names and name not in directories:
                                    raise ValueError('Accepted immutable asset path set differs')
                                pending.append(child)
                    elif candidate.is_file(): actual.add(relative)
                    else: raise ValueError('Accepted immutable asset type differs')
            if actual != names:
                raise ValueError('Accepted immutable asset path set differs')
        # A cooperating installer may have atomically switched generations
        # while the full inventory was read. Reject that attempt before launch.
        if read_json(self.root / 'native-install.json') != self._spec:
            raise ValueError('Native install approval changed during verification')
        for pin in self._spec['asset_manifests']:
            if file_hash(regular_owned(self.root, pin['path'])) != pin['sha256']:
                raise ValueError('Accepted manifest changed during verification')

    def _validate_state(self, state):
        if (state.get('schema') != 'omni-jd-lifecycle/v1'
                or state.get('install_id') != self._spec['install_id']
                or state.get('downloads') != str(self.downloads)
                or not HEX32.fullmatch(str(state.get('session', '')))
                or not HEX64.fullmatch(str(state.get('token', '')))
                or state.get('status') not in ('claimed', 'launching', 'uncertain', 'ready', 'closing', 'closed')):
            raise ValueError('Existing native lifecycle ownership differs; preserved')
        session_root = self.root / 'sessions' / state['session']
        if state.get('config') != str(session_root / 'config.json') or state.get('ready_file') != str(session_root / 'ready.json'):
            raise ValueError('Existing native lifecycle paths differ; preserved')
        if 'native_pid' in state and (type(state['native_pid']) is not int or state['native_pid'] <= 0):
            raise ValueError('Existing native PID identity is invalid; preserved')

    def _save(self):
        # Preserve each session's final state even after the root pointer later
        # advances to a new session. No token is exposed by status().
        owned = self.root / 'sessions' / self._state['session']
        if owned.is_dir() and not owned.is_symlink():
            atomic_json(owned / 'lifecycle-state.json', self._state)
        atomic_json(self.root / 'lifecycle-state.json', self._state)

    def _call(self, config, action):
        body = json.dumps(dict(token=config['token'], session=self._state['session'], action=action), separators=(',', ':')).encode()
        deadline = self._clock() + 2.0
        def read(connection, count):
            result = bytearray()
            while len(result) < count:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError('Native Java RPC deadline')
                connection.settimeout(remaining)
                part = connection.recv(count - len(result))
                if not part:
                    raise ConnectionError('Native Java RPC incomplete')
                result.extend(part)
            return bytes(result)
        with socket.create_connection(('127.0.0.1', config['port']), timeout=2) as connection:
            connection.settimeout(max(.001, deadline-self._clock()))
            connection.sendall(struct.pack('!I', len(body)) + body)
            length, = struct.unpack('!I', read(connection, 4))
            if not 0 < length <= 65536:
                raise ValueError('Native Java response bound')
            value = json.loads(read(connection, length))
        if type(value) is not dict or value.get('ok') is not True:
            raise ValueError('Native Java RPC refused')
        return value

    def _ready(self):
        ready = read_json(Path(self._state['ready_file']))
        if (ready.get('host') != '127.0.0.1' or ready.get('protocol') != 2
                or type(ready.get('port')) is not int or not 1 <= ready['port'] <= 65535
                or ready.get('token') != self._state['token']
                or ready.get('session') != self._state['session']
                or ready.get('install_id') != self._state['install_id']
                or type(ready.get('native_pid')) is not int or ready['native_pid'] <= 0):
            raise ValueError('Native Java readiness identity differs')
        health = self._call(ready, 'health')
        if (health.get('session') != self._state['session']
                or health.get('install_id') != self._state['install_id']
                or type(health.get('native_pid')) is not int or health['native_pid'] != ready['native_pid']):
            raise ValueError('Authenticated native session identity differs')
        known_pid = self._state.get('native_pid')
        if known_pid is not None and known_pid != health['native_pid']:
            raise ValueError('Native process identity changed')
        self._state['native_pid'] = health['native_pid']
        if health.get('startup_error'):
            raise ValueError('Native Java startup failed: ' + str(health['startup_error'])[:180])
        if health.get('ready') is not True:
            return None
        return ready, health

    def _launch(self):
        self._verify_assets()
        sessions = self.root / 'sessions'
        if sessions.is_symlink():
            raise ValueError('Sessions directory symlink refused')
        sessions.mkdir(exist_ok=True)
        session = secrets.token_hex(16)
        owned = sessions / session
        owned.mkdir(mode=0o700)
        for name in ('home', 'tmp'):
            (owned / name).mkdir(mode=0o700)
        self._state = dict(schema='omni-jd-lifecycle/v1', session=session,
            token=secrets.token_hex(32), install_id=self._spec['install_id'],
            downloads=str(self.downloads), config=str(owned / 'config.json'),
            ready_file=str(owned / 'ready.json'), status='claimed')
        self._save()  # Durable ownership before any possibly ambiguous launch.
        runtime = self.root / 'runtime'
        config = dict(token=self._state['token'], session=session,
            install_id=self._state['install_id'], port=0,
            downloads=str(self.downloads), ready_file=self._state['ready_file'],
            max_seconds=86400, idle_seconds=300, runtime=str(runtime),
            java_home=str(self.root / 'native/java25'), main_class='OmniJDownloaderBridge',
            classpath=[str(runtime / item) for item in ('classes', 'Core.jar',
                'JDownloader.jar', 'libs/*', 'extensions/*', '')],
            home=str(owned / 'home'), tmp=str(owned / 'tmp'),
            trace_file=str(owned / 'native.log'),
            native_receipt_file=str(owned / 'native-receipt.json'))
        with Path(self._state['config']).open('x', encoding='utf-8') as stream:
            json.dump(config, stream, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        self._state['status'] = 'launching'
        self._save()
        query = dict(path=str(self.root / 'java-worker.elf'),
            args='omni-jd-worker ' + self._state['config'] + ' jdownloader', cwd=str(self.root), daemon='1', pipe='0')
        try:
            with self._opener.open('http://127.0.0.1:8080/hbldr?' + urlencode(query), timeout=3) as response:
                raw = response.read(16385)
                if response.status != 200 or len(raw) > 16384:
                    raise ValueError('Native launch acknowledgement invalid')
            self._state['launch_acknowledged'] = True
        except (OSError, ValueError) as error:
            # Even timeout/refusal can follow successful native process creation.
            self._state['launch_acknowledged'] = False
            self._state['launch_error'] = type(error).__name__
        self._state['status'] = 'uncertain'
        self._save()

    def ensure_started(self):
        with self._lock:
            if self._state is not None and self._state.get('status') in ('claimed', 'launching', 'uncertain', 'ready', 'closing'):
                self._recover_absent_session()
            if not self._can_start:
                raise ValueError(self._message)
            if self._state is None or self._state['status'] == 'closed':
                self._launch()
            deadline = self._clock() + self._spec.get('startup_seconds', 180)
            last_error = 'Java is initializing'
            while self._clock() < deadline:
                try:
                    result = self._ready()
                    if result is not None:
                        ready, health = result
                        if health.get('draining') is True:
                            raise ValueError('Native Java session is draining; confirmed cleanup required')
                        if any(health.get(name) != 0 for name in ('jobs', 'core_crawled', 'core_downloads')):
                            raise ValueError('Existing native Java jobs require recovery; no new job admitted')
                        if self.ready_path.exists() and read_json(self.ready_path) != ready:
                            raise ValueError('Unowned stable readiness identity preserved')
                        atomic_json(self.ready_path, ready)
                        self._state['status'] = 'ready'
                        self._save()
                        self._message = 'Native JDownloader is ready.'
                        self._last_keepalive = 0
                        self._start_keeper()
                        return self.status()
                except (OSError, ValueError, KeyError, TypeError) as error:
                    last_error = str(error)[:180]
                    if isinstance(error, ValueError) and any(word in str(error) for word in ('identity', 'recovery', 'startup failed', 'draining')):
                        break
                self._sleep(.25)
            self._state['status'] = 'uncertain'
            self._save()
            self._can_start = False
            self._message = 'Native startup unconfirmed; no duplicate launch: ' + last_error
            raise ValueError(self._message)

    def _start_keeper(self):
        if self._keeper is not None and self._keeper.is_alive():
            return
        self._stop.clear()
        self._keeper = threading.Thread(target=self._keep_alive, name='owned-jd-keepalive', daemon=True)
        self._keeper.start()

    def _keep_alive(self):
        while not self._stop.wait(30):
            with self._lock:
                if not self._state or self._state['status'] != 'ready':
                    return
                try:
                    result = self._ready()
                    if result:
                        self._call(result[0], 'keepalive')
                        self._last_keepalive = self._clock()
                except (OSError, ValueError, KeyError, TypeError):
                    self._message = 'Owned Java session is unavailable; restart requires confirmed cleanup.'
                    self._can_start = False
                    return

    def status(self):
        # Startup holds the mutation lock, but GUI status must remain immediate.
        # No network calls, Java launch or disk reads happen on this path.
        acquired = self._lock.acquire(blocking=False)
        try:
            if not acquired:
                return dict(can_start=False, status='Starting or closing the owned Java session.', state='busy')
            return dict(can_start=self._can_start, status=self._message,
                        state=self._state.get('status', 'invalid') if self._state else 'unstarted')
        finally:
            if acquired:
                self._lock.release()

    def _pid_absent(self, pid):
        if type(pid) is not int or pid <= 0:
            return False
        with self._opener.open('http://127.0.0.1:8084/processes_list', timeout=2) as response:
            raw = response.read(1024 * 1024 + 1)
            if response.status != 200 or len(raw) > 1024 * 1024:
                return False
        value = json.loads(raw)
        if type(value) is not dict:
            return False
        rows = value.get('processes')
        if type(rows) is not list or len(rows) > 1024:
            return False
        ids = set()
        for row in rows:
            if type(row) is not dict or type(row.get('pid')) is not int or row['pid'] < 0 or row['pid'] in ids:
                return False
            ids.add(row['pid'])
        return pid not in ids

    def _recover_absent_session(self):
        """Retire only a proven-dead exact session; never kill or guess a PID."""
        pid = self._state.get('native_pid')
        if type(pid) is not int or pid <= 0:
            return False
        try:
            if not self._pid_absent(pid):
                return False
        except (OSError, ValueError, KeyError, TypeError):
            return False  # Failed/incomplete inventory is not absence proof.
        self._validate_state(self._state)
        owned = self.root / 'sessions' / self._state['session']
        if not owned.is_dir() or owned.is_symlink():
            raise ValueError('Existing native session directory identity differs; preserved')
        stable = None
        for path in (Path(self._state['ready_file']), self.ready_path):
            if not path.exists() and not path.is_symlink():
                continue
            ready = read_json(path)
            if (ready.get('host') != '127.0.0.1' or ready.get('protocol') != 2
                    or type(ready.get('port')) is not int or not 1 <= ready['port'] <= 65535
                    or ready.get('token') != self._state['token']
                    or ready.get('session') != self._state['session']
                    or ready.get('install_id') != self._state['install_id']
                    or type(ready.get('native_pid')) is not int or ready['native_pid'] != pid):
                raise ValueError('Readiness identity differs from proven absent session; preserved')
            if path == self.ready_path:
                stable = ready
        suffix = secrets.token_hex(8)
        retired = owned / ('retired-bridge-ready-' + suffix + '.json')
        checkpoint = dict(schema='omni-jd-dead-session-recovery/v1',
            previous_state=dict(self._state), native_pid=pid,
            absence_source='fresh-local-processes-list', observed_unix_seconds=time.time(),
            retired_ready=str(retired) if stable is not None else None)
        atomic_json(owned / ('recovery-checkpoint-' + suffix + '.json'), checkpoint)
        if stable is not None:
            # Preserve the exact old file for inspection; never unlink its data.
            # Recheck under the lifecycle mutation lock immediately before move.
            if read_json(self.ready_path) != stable:
                raise ValueError('Stable readiness identity changed during recovery; preserved')
            os.rename(self.ready_path, retired)
            if read_json(retired) != stable:
                raise ValueError('Retired readiness identity changed; launch refused')
        self._state['status'] = 'closed'
        self._state['recovery'] = dict(reason='known-native-pid-positively-absent', checkpoint='recovery-checkpoint-' + suffix + '.json')
        self._save()
        self._can_start = True
        self._message = 'Previous owned Java process is absent; a fresh session can start.'
        return True

    def close(self):
        self._stop.set()
        keeper = self._keeper
        if keeper is not None and keeper is not threading.current_thread():
            keeper.join(timeout=5)
            if keeper.is_alive():
                return False
        with self._lock:
            if self._state is None or self._state['status'] == 'closed':
                return True
            try:
                if self._recover_absent_session():
                    return True
                result = self._ready()
                if result is None:
                    return False
                ready, health = result
                if any(health.get(name) != 0 for name in ('jobs', 'core_crawled', 'core_downloads')):
                    return False
                self._call(ready, 'shutdown')
                self._state['status'] = 'closing'
                self._save()
                deadline = self._clock() + 8
                while self._clock() < deadline:
                    if self._pid_absent(health['native_pid']):
                        if self.ready_path.exists():
                            current = read_json(self.ready_path)
                            if current != ready:
                                return False
                            self.ready_path.unlink()
                        self._state['status'] = 'closed'
                        self._save()
                        self._message = 'Owned native Java session closed.'
                        return True
                    self._sleep(.25)
            except (OSError, ValueError, KeyError, TypeError):
                pass
            return False


def create_lifecycle(downloads, ready_path):
    return NativeLifecycle(downloads, ready_path)
