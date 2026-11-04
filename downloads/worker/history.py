"""Bounded, atomic local history. Never persists submitted URLs or cookies."""
import json
import os
from pathlib import Path
import tempfile

TERMINAL = frozenset(('completed', 'failed', 'cancelled', 'interrupted'))
MAX_JOBS = 100
MAX_PENDING = 8
MAX_BYTES = 1024 * 1024


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
    return dict(id=key, title=title[:300] if isinstance(title, str) else 'Previous job',
                demo=value.get('demo') is True, audio=value.get('audio') is True,
                state=state[:32], engine=engine, engine_requested=requested,
                note=note[:400] if isinstance(note, str) else '',
                filepath=filepath[:4096] if isinstance(filepath, str) else '')


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
                state = saved['state'] if saved['state'] in TERMINAL else 'interrupted'
                saved['state'] = state
                # A duplicate is replaced by its latest occurrence and position.
                jobs.pop(key, None)
                jobs[key] = dict(saved, url='', progress=100 if state == 'completed' else 0,
                                 error='Worker stopped; submit the link again.' if state == 'interrupted' else '',
                                 cancel=state != 'completed', restored=True)
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
