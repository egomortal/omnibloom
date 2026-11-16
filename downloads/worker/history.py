"""Bounded, atomic local history. Never persists cookies.

OMNI_DL_RESUME_V1: submitted links and download choices are persisted ONLY for jobs that can still be resumed
(paused, or unfinished when the worker stopped, which load as 'interrupted'); finished, failed and cancelled
records stay link-free. A paused job loads as 'paused', not 'interrupted'.
"""
import json
import os
import re
from pathlib import Path
import tempfile

TERMINAL = frozenset(('completed', 'failed', 'cancelled', 'interrupted'))
# Not terminal, but not queued either: the job waits for the user (its partial files are kept).
PAUSED = 'paused'
# States whose records keep the link and choices, so the job can be resumed after a restart.
LINK_FREE = frozenset(('completed', 'failed', 'cancelled'))
MAX_JOBS = 100
MAX_PENDING = 8
MAX_BYTES = 1024 * 1024
_HEX32 = re.compile(r'[0-9a-f]{32}\Z')


def _text(value, limit, pattern=None):
    if not isinstance(value, str) or not value or len(value) > limit or not value.isprintable():
        return None
    if pattern is not None and not re.fullmatch(pattern, value):
        return None
    return value


def _count(value):
    return value if type(value) is int and 0 <= value <= 10 ** 15 else None


def _resume_fields(value):
    """The link and choices a resumable job needs; {} when the link is not usable. Re-validated on resume."""
    url = _text(value.get('url'), 4096, r'(?i)https?://\S+')
    if url is None:
        return {}
    request_id = value.get('request_id')
    return dict(url=url,
                referer=_text(value.get('referer'), 4096, r'(?i)https?://\S+'),
                format=_text(value.get('format'), 400),
                quality_key=value.get('quality_key')[:2000] if isinstance(value.get('quality_key'), str) else '',
                preset=_text(value.get('preset'), 32, r'[a-z0-9-]+'),
                subtitle_lang=_text(value.get('subtitle_lang'), 20, r'[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8}){0,2}'),
                container=value.get('container') if value.get('container') in ('mp4', 'mkv', 'm4a', 'webm') else None,
                save_place=_text(value.get('save_place'), 8, r'internal|usb[0-7]'),
                save_folder=_text(value.get('save_folder'), 80),
                save_name=_text(value.get('save_name'), 80),
                direct=value.get('direct') is True,
                auto_fallback=value.get('auto_fallback') is not False,
                request_id=request_id if isinstance(request_id, str) and _HEX32.match(request_id) else None,
                downloaded_bytes=_count(value.get('downloaded_bytes')),
                total_bytes=_count(value.get('total_bytes')),
                attempt=_count(value.get('attempt')) or 1,
                retries=_count(value.get('retries')) or 0)


def _record(value):
    """Copy only the supported fields, without stringifying untrusted objects."""
    if not isinstance(value, dict):
        raise ValueError('Invalid history record')
    key = value.get('id')
    if not isinstance(key, str) or len(key) != 16 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid history job ID')
    state = value.get('state')
    if not isinstance(state, str):
        raise ValueError('Invalid history job state')
    title = value.get('title')
    filepath = value.get('filepath')
    engine = value.get('engine', 'ytdlp')
    if engine not in ('ytdlp', 'jdownloader'):
        raise ValueError('Invalid history engine')
    requested = value.get('engine_requested', engine)
    if requested not in ('ytdlp', 'jdownloader'):
        requested = engine
    # The routing note is worker-written and URL-free (see adapters.redact_urls).
    note = value.get('note')
    record = dict(id=key, title=title[:300] if isinstance(title, str) else 'Previous job',
                  demo=value.get('demo') is True, audio=value.get('audio') is True,
                  state=state[:32], engine=engine, engine_requested=requested,
                  note=note[:400] if isinstance(note, str) else '',
                  filepath=filepath[:4096] if isinstance(filepath, str) else '')
    if record['state'] not in LINK_FREE:
        record.update(_resume_fields(value))   # OMNI_DL_RESUME_V1
    return record


class History:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.error = ''

    def load(self):
        self.error = ''
        if self.path is None:
            return {}
        try:
            # Bound the read itself: a file can grow between stat() and read().
            with self.path.open('rb') as source:
                content = source.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError('History exceeds size limit')
            value = json.loads(content.decode('utf-8'))
            if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1 or not isinstance(value.get('jobs'), list):
                raise ValueError('Unsupported history format')
            jobs = {}
            skipped = 0
            for value in value['jobs'][-MAX_JOBS:]:
                try:
                    saved = _record(value)
                except ValueError:
                    skipped += 1
                    continue
                key = saved['id']
                # OMNI_DL_RESUME_V1: a paused job (or one the user was pausing) stays paused across a restart.
                state = saved['state'] if saved['state'] in TERMINAL else PAUSED if saved['state'] in (PAUSED, 'pausing') else 'interrupted'
                saved['state'] = state
                resumable = bool(saved.get('url')) and state in (PAUSED, 'interrupted')
                if state == PAUSED and not resumable:
                    state = saved['state'] = 'interrupted'
                # A duplicate is replaced by its latest occurrence and position.
                jobs.pop(key, None)
                total, done = saved.get('total_bytes'), saved.get('downloaded_bytes')
                progress = 100 if state == 'completed' else min(100, int(100 * done / total)) if resumable and total and done else 0
                error = ''
                if state == 'interrupted':
                    error = 'Worker stopped; resume to continue.' if resumable else 'Worker stopped; submit the link again.'
                jobs[key] = dict(saved, url=saved.get('url', '') if resumable else '', progress=progress, error=error,
                                 cancel=state != 'completed' and not resumable, pause=False, restored=True)
            if skipped:
                self.error = f'History omitted {skipped} invalid record(s).'
            return jobs
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, RecursionError) as error:
            self.error = 'History could not be loaded: ' + str(error)[:200]
            return {}

    def save(self, jobs):
        if self.path is None:
            return
        temporary = None
        try:
            if not isinstance(jobs, dict):
                raise ValueError('Jobs must be a dictionary')
            # Select newest records without copying an arbitrarily large mapping.
            recent = []
            for value in reversed(jobs.values()):
                recent.append(value)
                if len(recent) == MAX_JOBS:
                    break
            prefix, suffix = b'{"version":1,"jobs":[', b']}'
            remaining = MAX_BYTES - len(prefix) - len(suffix)
            records = []
            skipped = 0
            for value in recent:
                try:
                    record = _record(value)
                except ValueError:
                    skipped += 1
                    continue
                encoded = json.dumps(record, ensure_ascii=True, separators=(',', ':')).encode('ascii')
                size = len(encoded) + bool(records)
                if size > remaining:
                    break
                records.append(encoded)
                remaining -= size
            content = prefix + b','.join(reversed(records)) + suffix
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Same-directory replacement stays atomic; unique names prevent
            # concurrent writers from replacing or cleaning up each other's temp.
            with tempfile.NamedTemporaryFile(mode='wb', dir=self.path.parent,
                                             prefix=f'.{self.path.name}.', suffix='.tmp', delete=False) as target:
                temporary = Path(target.name)
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
            temporary = None
            self.error = f'History omitted {skipped} invalid record(s).' if skipped else ''
        except (OSError, ValueError) as error:
            self.error = 'History could not be saved: ' + str(error)[:200]
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
