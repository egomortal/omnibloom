"""OMNI_DL_ALREADY_V1: "Already in the Library" check for the new-download form.

When a job completes, the worker records a keyed fingerprint of what was saved: HMAC-SHA256 with a random per-install
key over the media identity (a YouTube video id, or the address without tracking parameters) plus audio/video. Only the
fingerprint and the saved file's path are stored (library-seen.json beside the state file), never the address, so the
history stays URL-free and the file cannot be matched against a list of known videos without the key.
A check answers with the saved file's name only while that file still exists; missing files are pruned.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

MAX_ITEMS = 2000
MAX_BYTES = 1024 * 1024
YT_HOSTS = {'youtube.com', 'm.youtube.com', 'music.youtube.com', 'www.youtube.com', 'youtube-nocookie.com',
            'www.youtube-nocookie.com'}
YT_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
TRACKING = re.compile(r'^(utm_[a-z]+|fbclid|gclid|dclid|msclkid|mc_[a-z]+|igshid|si|feature|ref|ref_src|spm)$', re.I)


def identity(url):
    """A stable media identity for an http(s) address, or None. YouTube watch/shorts/embed/youtu.be links of one video
    share an identity; other addresses drop the fragment, 'www.', tracking parameters and parameter order."""
    if not isinstance(url, str) or len(url) > 4096:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip('.')
    path = parts.path or '/'
    query = parse_qsl(parts.query, keep_blank_values=True)
    if host in YT_HOSTS:
        vid = None
        if path == '/watch':
            vid = dict(query).get('v')
        else:
            m = re.match(r'^/(?:shorts|embed|live|v)/([^/?#]+)', path)
            vid = m.group(1) if m else None
        if vid and YT_ID.match(vid):
            return 'yt:' + vid
    if host == 'youtu.be':
        vid = path.strip('/').split('/')[0]
        if YT_ID.match(vid):
            return 'yt:' + vid
    if host.startswith('www.'):
        host = host[4:]
    port = parts.port
    kept = sorted((k, v) for k, v in query if not TRACKING.match(k))
    return 'u:' + host + (':%d' % port if port and port not in (80, 443) else '') + path + ('?' + urlencode(kept) if kept else '')


class Seen:
    def __init__(self, path=None, exists=os.path.isfile, clock=time.time):
        self.path = Path(path) if path else None
        self.exists = exists
        self.clock = clock
        self.lock = threading.Lock()
        self.key = None
        self.items = {}
        self._load()

    def _load(self):
        data = None
        if self.path is not None:
            try:
                if self.path.stat().st_size <= MAX_BYTES:
                    data = json.loads(self.path.read_text('utf-8'))
            except (OSError, ValueError):
                data = None
        if isinstance(data, dict) and isinstance(data.get('key'), str) and re.fullmatch(r'[0-9a-f]{64}', data['key']):
            self.key = bytes.fromhex(data['key'])
            items = data.get('items') if isinstance(data.get('items'), dict) else {}
            for fp, entry in items.items():
                if re.fullmatch(r'[0-9a-f]{40}', str(fp)) and isinstance(entry, dict) and isinstance(entry.get('file'), str) \
                        and 0 < len(entry['file']) <= 4096 and isinstance(entry.get('t'), (int, float)):
                    self.items[fp] = {'file': entry['file'], 't': entry['t']}
        if self.key is None:
            self.key = secrets.token_bytes(32)

    def fingerprint(self, url, audio):
        ident = identity(url)
        if ident is None or type(audio) is not bool:
            return None
        msg = (ident + '\0' + ('a' if audio else 'v')).encode('utf-8')
        return hmac.new(self.key, msg, hashlib.sha256).hexdigest()[:40]

    def _save(self):
        if self.path is None:
            return
        if len(self.items) > MAX_ITEMS:   # the oldest go first
            for fp in sorted(self.items, key=lambda k: self.items[k]['t'])[:len(self.items) - MAX_ITEMS]:
                del self.items[fp]
        tmp = self.path.with_name(self.path.name + '.tmp')
        try:
            tmp.write_text(json.dumps({'key': self.key.hex(), 'items': self.items}, separators=(',', ':')), 'utf-8')
            os.replace(tmp, self.path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass

    def record(self, url, audio, filepath):
        """After a job completes: remember what was saved. Demo jobs and jobs without a file are not recorded."""
        fp = self.fingerprint(url, audio)
        if fp is None or not isinstance(filepath, str) or not filepath or len(filepath) > 4096:
            return False
        with self.lock:
            self.items[fp] = {'file': filepath, 't': self.clock()}
            self._save()
        return True

    def check(self, url, audio):
        """{'already': bool, 'name': saved file name or ''}. A file that is gone is forgotten."""
        fp = self.fingerprint(url, audio)
        if fp is None:
            return {'already': False, 'name': ''}
        with self.lock:
            entry = self.items.get(fp)
            if entry is None:
                return {'already': False, 'name': ''}
            if not self.exists(entry['file']):
                del self.items[fp]
                self._save()
                return {'already': False, 'name': ''}
            return {'already': True, 'name': os.path.basename(entry['file'])[:200]}
