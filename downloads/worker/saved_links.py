"""Explicitly saved URLs, separate from URL-free download history.

Only successful explicit saves persist URLs. A missing state path is clearly
memory-only. Invalid existing storage is preserved and made read-only; writes
commit atomically before their new in-memory snapshot becomes visible.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import threading
import time
from urllib.parse import urlsplit

MAX_LINKS = 64
MAX_REPLAYS = 128
MAX_BYTES = 1024 * 1024
LOCK_TIMEOUT = 2.0


def validate_http_url(url):
    """The same submitted-URL policy used by download jobs and saved links."""
    if not isinstance(url, str) or len(url) > 4096:
        raise ValueError('URL must be text (up to 4096 characters).')
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or '\\' in url
            or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in url)):
        raise ValueError('Enter an HTTP or HTTPS URL without embedded credentials.')
    # Accessing port also validates malformed/out-of-range port strings.
    if parsed.port == 0:
        raise ValueError('URL port must be between 1 and 65535.')
    return url


def _hex(value, length):
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)


def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, stat.S_IMODE(info.st_mode), info.st_mtime_ns)


def _url_hash(url):
    try:
        return hashlib.sha256(url.encode('utf-8')).hexdigest()
    except UnicodeError as error:
        raise ValueError('Saved URL must contain valid Unicode.') from error


def _unique(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate saved-links field')
        result[name] = value
    return result


class SavedLinksUnavailable(Exception):
    """Storage or contention failure; no mutation was acknowledged."""


class _ChangedStorage(Exception):
    pass


class SavedLinks:
    def __init__(self, path=None):
        self.path = None
        self.persistent = path is not None
        self.links = []
        self.replays = []
        self.error = ''
        self.writable = True
        self.lock = threading.Lock()  # Never acquire Jobs.lock or start a dispatcher.
        self._fingerprint = None
        self._parent_identity = None
        if path is not None:
            try:
                raw = Path(path).absolute()
                # Bind an intentionally supplied parent alias once. A later
                # parent replacement must never redirect writes elsewhere.
                try:
                    self.path = raw.parent.resolve() / raw.name
                except RuntimeError as error:
                    raise _ChangedStorage('Saved-links parent cannot be resolved') from error
                self._load()
            except (OSError, ValueError, RecursionError, _ChangedStorage):
                self.writable = False
                self.error = 'Saved links could not be loaded; existing storage was preserved.'

    @contextmanager
    def _locked(self):
        if not self.lock.acquire(timeout=LOCK_TIMEOUT):
            raise SavedLinksUnavailable('Saved links are busy; retry shortly.')
        try:
            yield
        finally:
            self.lock.release()

    def _check_parent(self):
        try:
            resolved = self.path.parent.resolve()
        except RuntimeError as error:
            raise _ChangedStorage('Saved-links parent cannot be resolved') from error
        if resolved != self.path.parent:
            raise _ChangedStorage('Saved-links parent changed')
        try:
            parent = self.path.parent.lstat()
        except FileNotFoundError:
            if self._parent_identity is not None:
                raise _ChangedStorage('Saved-links parent disappeared')
            return
        if not stat.S_ISDIR(parent.st_mode):
            raise _ChangedStorage('Saved-links parent is not a real directory')
        identity = (parent.st_dev, parent.st_ino)
        if self._parent_identity is not None and identity != self._parent_identity:
            raise _ChangedStorage('Saved-links parent identity changed')
        self._parent_identity = identity

    def _current(self):
        self._check_parent()
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode):
            raise _ChangedStorage('Saved-links storage is not a regular file')
        return _fingerprint(info)

    def _load(self):
        before = self._current()
        if before is None:
            return
        if before[2] > MAX_BYTES:
            raise ValueError('Saved-links storage exceeds size limit')
        descriptor = os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                             | getattr(os, 'O_NONBLOCK', 0))
        try:
            if _fingerprint(os.fstat(descriptor)) != before:
                raise _ChangedStorage('Saved-links storage changed while opening')
            with os.fdopen(descriptor, 'rb') as source:
                descriptor = -1
                content = source.read(MAX_BYTES + 1)
                if _fingerprint(os.fstat(source.fileno())) != before:
                    raise _ChangedStorage('Saved-links storage changed while reading')
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if len(content) > MAX_BYTES or self._current() != before:
            raise _ChangedStorage('Saved-links storage changed or exceeds size limit')
        document = json.loads(content.decode('utf-8'), object_pairs_hook=_unique)
        if (not isinstance(document, dict) or set(document) != {'version', 'links', 'replays'}
                or type(document['version']) is not int or document['version'] != 1
                or not isinstance(document['links'], list) or len(document['links']) > MAX_LINKS
                or not isinstance(document['replays'], list) or len(document['replays']) > MAX_REPLAYS):
            raise ValueError('Unsupported saved-links format')
        ids, urls, request_ids, hashes_by_id = set(), set(), set(), {}
        for link in document['links']:
            if (not isinstance(link, dict) or set(link) != {'id', 'url', 'created_at'}
                    or not _hex(link['id'], 16) or type(link['created_at']) is not int
                    or not 0 <= link['created_at'] <= 2 ** 53 - 1):
                raise ValueError('Invalid saved link')
            validate_http_url(link['url'])
            if link['id'] in ids or link['url'] in urls:
                raise ValueError('Duplicate saved link')
            ids.add(link['id'])
            urls.add(link['url'])
            hashes_by_id[link['id']] = _url_hash(link['url'])
        for replay in document['replays']:
            if (not isinstance(replay, dict) or set(replay) != {'request_id', 'url_sha256', 'id'}
                    or not _hex(replay['request_id'], 32) or not _hex(replay['id'], 16)
                    or not _hex(replay['url_sha256'], 64) or replay['request_id'] in request_ids):
                raise ValueError('Invalid saved-links replay receipt')
            if hashes_by_id.get(replay['id'], replay['url_sha256']) != replay['url_sha256']:
                raise ValueError('Saved-links replay receipt differs from its link')
            request_ids.add(replay['request_id'])
            hashes_by_id[replay['id']] = replay['url_sha256']
        self.links, self.replays = document['links'], document['replays']
        self._fingerprint = before

    def snapshot(self):
        with self._locked():
            return dict(links=[dict(link) for link in self.links], max_links=MAX_LINKS,
                        error=self.error, writable=self.writable, persistent=self.persistent)

    def _guard_storage(self):
        if not self.writable:
            raise SavedLinksUnavailable(self.error)
        if self.path is not None:
            try:
                if self._current() != self._fingerprint:
                    raise _ChangedStorage('Saved-links storage changed outside this worker')
            except (OSError, _ChangedStorage) as error:
                self.writable = False
                self.error = 'Saved links changed outside this worker; existing storage was preserved.'
                raise SavedLinksUnavailable(self.error) from error

    def _persist(self, links, replays):
        if not self.writable:
            raise SavedLinksUnavailable(self.error)
        content = json.dumps(dict(version=1, links=links, replays=replays), ensure_ascii=True,
                             separators=(',', ':')).encode('ascii')
        if len(content) > MAX_BYTES:
            raise ValueError('Saved links exceed the storage size limit; remove a link first.')
        if self.path is None:
            return
        temporary = None
        temporary_identity = None
        try:
            if self._current() != self._fingerprint:
                raise _ChangedStorage('Saved-links storage changed outside this worker')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._check_parent()
            with tempfile.NamedTemporaryFile(mode='wb', dir=self.path.parent,
                                             prefix='.' + self.path.name + '.', suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                opened = os.fstat(output.fileno())
                temporary_identity = (opened.st_dev, opened.st_ino)
                if output.write(content) != len(content):
                    raise OSError('Short saved-links write')
                output.flush()
                os.fsync(output.fileno())
                committed = _fingerprint(os.fstat(output.fileno()))
            if self._current() != self._fingerprint or _fingerprint(temporary.lstat()) != committed:
                raise _ChangedStorage('Saved-links storage changed before publication')
            os.replace(temporary, self.path)
            temporary = None
            # No fallible storage operation occurs after the atomic commit.
            self._fingerprint = committed
        except _ChangedStorage as error:
            self.writable = False
            self.error = 'Saved links changed outside this worker; existing storage was preserved.'
            raise SavedLinksUnavailable(self.error) from error
        except OSError as error:
            self.error = 'Saved links could not be saved; the previous list was kept.'
            raise SavedLinksUnavailable(self.error) from error
        finally:
            if temporary is not None and temporary_identity is not None:
                try:
                    current = temporary.lstat()
                    if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == temporary_identity:
                        temporary.unlink()
                except OSError:
                    pass  # Never remove a colliding/replaced temporary file.

    def save(self, url, request_id):
        validate_http_url(url)
        digest = _url_hash(url)
        if not _hex(request_id, 32):
            raise ValueError('request_id must contain 32 lowercase hexadecimal characters.')
        with self._locked():
            self._guard_storage()
            for replay in self.replays:
                if replay['request_id'] == request_id:
                    if replay['url_sha256'] != digest:
                        raise ValueError('request_id was already used for a different saved link.')
                    return dict(id=replay['id'], created=False,
                                present=any(link['id'] == replay['id'] for link in self.links), replayed=True)
            existing = next((link for link in self.links if link['url'] == url), None)
            links = list(self.links)
            if existing is not None:
                key = existing['id']
            else:
                if len(links) == MAX_LINKS:
                    raise ValueError('Saved links are full (64 links); remove a link first.')
                used = {link['id'] for link in links} | {item['id'] for item in self.replays}
                key = None
                for _ in range(8):
                    candidate = secrets.token_hex(8)
                    if candidate not in used:
                        key = candidate
                        break
                if key is None:
                    raise SavedLinksUnavailable('Could not allocate a saved-link ID; retry.')
                links.append(dict(id=key, url=url, created_at=max(0, int(time.time() * 1000))))
            replays = (self.replays + [dict(request_id=request_id, url_sha256=digest, id=key)])[-MAX_REPLAYS:]
            self._persist(links, replays)
            self.links, self.replays, self.error = links, replays, ''
            return dict(id=key, created=existing is None, present=True, replayed=False)

    def delete(self, key):
        if not _hex(key, 16):
            raise ValueError('Saved-link id must contain 16 lowercase hexadecimal characters.')
        with self._locked():
            self._guard_storage()
            links = [link for link in self.links if link['id'] != key]
            if len(links) == len(self.links):
                return dict(removed=False)
            self._persist(links, self.replays)  # Tombstones prevent retry resurrection.
            self.links, self.error = links, ''
            return dict(removed=True)
