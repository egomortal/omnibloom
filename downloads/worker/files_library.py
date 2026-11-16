# SPDX-License-Identifier: GPL-3.0-or-later
"""Library of finished downloads: list, stream, trash (OMNI_DL_LIBRARY_V1).

Only the save roots are ever read or changed:
  console storage -> <downloads folder>/Saved        (always)
  USB drive N     -> /mnt/usbN/Omni Downloads         (only while the drive is mounted)
Each root has a hidden ".trash" folder that mirrors the root's layout. "Delete" moves a file there first; only a file
already in the trash can be deleted for real.

The GUI never sends a path. Every file is named by an opaque id: HMAC-SHA256(key, root id + area + relative path),
32 hex chars, where the key is derived from the worker's session token (a restart makes every id and link void).
An id is resolvable only after a listing (or a job lookup) put it into a bounded in-memory index; the relative path
from the index is checked again on every use: plain names only, no hidden parts, no symbolic link anywhere from the
root down, a regular file, and its resolved path still inside the resolved root.

Streaming links: a <video src> cannot send the X-Omni-Token header, so a token holder asks POST /api/files/link and
gets /api/files/stream?id=<id>&exp=<unix seconds>&sig=<hex>, sig = HMAC-SHA256(key, "stream\\0" + id + "\\0" + exp).
A link works for LINK_TTL seconds and only for that one file.
"""
import hashlib
import hmac
import os
import re
import stat
import threading
import time
from collections import OrderedDict
from pathlib import Path

import save_places

TRASH = '.trash'
LINK_TTL = 2 * 60 * 60          # a long film keeps playing; the player asks for a fresh link when one expires
MAX_INDEX = 50000               # ids remembered per worker session
MAX_SCAN = 20000                # directory entries looked at per listing
MAX_DEPTH = 8
MAX_PAGE = 100
CHUNK = 256 * 1024              # bytes read from disk per write
MAX_RANGE_BYTES = 8 * 1024 * 1024   # one 206 answer at most; the player asks again for the rest
_ID = re.compile(r'[0-9a-f]{32}\Z')
_SIG = re.compile(r'[0-9a-f]{64}\Z')
_RANGE = re.compile(r'\s*bytes\s*=\s*(\d{0,19})\s*-\s*(\d{0,19})\s*\Z')

KINDS = {}
for _ext, _mime in (('.mp4', 'video/mp4'), ('.m4v', 'video/mp4'), ('.webm', 'video/webm'), ('.mkv', 'video/x-matroska'),
                    ('.mov', 'video/quicktime'), ('.ts', 'video/mp2t'), ('.ogv', 'video/ogg')):
    KINDS[_ext] = ('video', _mime)
for _ext, _mime in (('.m4a', 'audio/mp4'), ('.mp3', 'audio/mpeg'), ('.aac', 'audio/aac'), ('.ogg', 'audio/ogg'),
                    ('.oga', 'audio/ogg'), ('.opus', 'audio/ogg'), ('.flac', 'audio/flac'), ('.wav', 'audio/wav'),
                    ('.weba', 'audio/webm')):
    KINDS[_ext] = ('audio', _mime)
for _ext, _mime in (('.png', 'image/png'), ('.jpg', 'image/jpeg'), ('.jpeg', 'image/jpeg'), ('.gif', 'image/gif'),
                    ('.webp', 'image/webp')):
    KINDS[_ext] = ('image', _mime)
KINDS['.pdf'] = ('pdf', 'application/pdf')
KINDS['.txt'] = ('text', 'text/plain; charset=utf-8')
KINDS['.vtt'] = ('text', 'text/vtt; charset=utf-8')
KINDS['.srt'] = ('text', 'text/plain; charset=utf-8')
OTHER = ('other', 'application/octet-stream')

# OMNI_DL_LIBRARY_SEARCH_V1: the Library's filter chips and sort orders.
CATEGORIES = ('video', 'audio', 'image', 'document', 'archive', 'other')
SORTS = ('newest', 'oldest', 'name', 'size', 'type')
MAX_QUERY = 100
_DOCUMENT_EXT = frozenset(('.pdf', '.txt', '.vtt', '.srt', '.ass', '.doc', '.docx', '.odt', '.rtf', '.epub', '.mobi',
                           '.md', '.csv', '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp'))
_ARCHIVE_EXT = frozenset(('.zip', '.rar', '.7z', '.tar', '.gz', '.tgz', '.bz2', '.tbz2', '.xz', '.txz', '.zst', '.lz',
                          '.lzma', '.cab'))


class NotFound(Exception):
    """The id is unknown, expired with a restart, or its file is gone or no longer safe to use."""


class Unsatisfiable(Exception):
    pass


def kind_of(name):
    return KINDS.get(os.path.splitext(name)[1].lower(), OTHER)


def category_of(name):
    """The Library chip a file belongs to: video, audio, image, document, archive or other."""
    ext = os.path.splitext(name)[1].lower()
    file_kind = KINDS.get(ext, OTHER)[0]
    if file_kind in ('video', 'audio', 'image'):
        return file_kind
    if file_kind in ('pdf', 'text') or ext in _DOCUMENT_EXT:
        return 'document'
    if ext in _ARCHIVE_EXT:
        return 'archive'
    return 'other'


def parse_categories(value):
    """'video,audio' -> ('video', 'audio'); '' -> () meaning every category. ValueError on anything else."""
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError('Unknown library filter.')
    parts = tuple(value.split(',')) if value else ()
    if any(part not in CATEGORIES for part in parts) or len(set(parts)) != len(parts):
        raise ValueError('Unknown library filter.')
    return parts


def _query_ok(q):
    return isinstance(q, str) and len(q) <= MAX_QUERY and not any(ord(c) < 32 or ord(c) == 127 for c in q)


def parse_range(header, size):
    """'bytes=a-b' / 'bytes=a-' / 'bytes=-n' -> (start, end) inclusive, capped to MAX_RANGE_BYTES.
    None -> serve the whole file (no header, or one we ignore: several ranges, bad syntax). Unsatisfiable raised."""
    if header is None:
        return None
    match = _RANGE.fullmatch(header)
    if not match:
        return None
    first, last = match.groups()
    if first == '' and last == '':
        return None
    if first == '':
        count = int(last)
        if count == 0 or size == 0:
            raise Unsatisfiable()
        start, end = max(0, size - count), size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
        if last and end < start:
            return None
        if start >= size:
            raise Unsatisfiable()
        end = min(end, size - 1)
    return start, min(end, start + MAX_RANGE_BYTES - 1)


def quote_name(name):
    """RFC 5987 value for Content-Disposition filename*: UTF-8, percent-encoded, nothing that could split a header."""
    return ''.join(chr(b) if chr(b).isalnum() and b < 128 or chr(b) in '._-' else '%%%02X' % b
                   for b in name.encode('utf-8', 'replace'))[:600] or 'file'


def _plain_parts(rel):
    parts = rel.split('/')
    if not rel or any(part in ('', '.', '..') or part.startswith('.') or '\\' in part or '\0' in part for part in parts):
        raise NotFound('Not a library file.')
    return parts


class Library:
    def __init__(self, internal, token, usb_roots=save_places.USB_ROOTS, now=time.time):
        self.internal = Path(internal)
        self.usb_roots = usb_roots
        self.key = hashlib.sha256(b'omni-library-v1\0' + str(token).encode()).digest()
        self.now = now
        self.index = OrderedDict()
        self.lock = threading.Lock()

    # ---- roots and ids ------------------------------------------------------------------------------------------
    def roots(self):
        """{root id: (label, Path)} for the roots that exist now; a root that is a symbolic link is left out."""
        out = {}
        candidates = [('internal', 'Console storage', self.internal / save_places.INTERNAL_FOLDER)]
        for number, root in enumerate(self.usb_roots):
            if save_places.mounted(root):
                candidates.append(('usb%d' % number, 'USB drive %d' % (number + 1), Path(root) / save_places.USB_FOLDER))
        for root_id, label, path in candidates:
            try:
                info = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISDIR(info.st_mode):
                out[root_id] = (label, path)
        return out

    def file_id(self, root_id, area, rel):
        fid = hmac.new(self.key, ('%s\0%s\0%s' % (root_id, area, rel)).encode('utf-8', 'surrogateescape'),
                       hashlib.sha256).hexdigest()[:32]
        with self.lock:
            self.index[fid] = (root_id, area, rel)
            self.index.move_to_end(fid)
            while len(self.index) > MAX_INDEX:
                self.index.popitem(last=False)
        return fid

    def resolve(self, fid):
        """id -> (root_id, area, rel, Path, lstat) after checking the whole chain again. NotFound otherwise."""
        if not isinstance(fid, str) or not _ID.fullmatch(fid):
            raise NotFound('Unknown file.')
        with self.lock:
            entry = self.index.get(fid)
        if entry is None:
            raise NotFound('Unknown file. Refresh the library.')
        root_id, area, rel = entry
        roots = self.roots()
        if root_id not in roots:
            raise NotFound('That drive is not connected.')
        root = roots[root_id][1]
        path = self._checked(root, area, rel)
        return root_id, area, rel, path, os.lstat(path)

    def _checked(self, root, area, rel):
        parts = _plain_parts(rel)
        base = root / TRASH if area == 'trash' else root
        chain = [root] + ([base] if area == 'trash' else [])
        path = base
        for part in parts:
            path = path / part
            chain.append(path)
        try:
            for step in chain:
                if stat.S_ISLNK(os.lstat(step).st_mode):
                    raise NotFound('Symbolic links are not served.')
            if not stat.S_ISREG(os.lstat(path).st_mode):
                raise NotFound('Not a regular file.')
            path.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (OSError, ValueError):
            raise NotFound('The file is gone.')
        return path

    # ---- listing ------------------------------------------------------------------------------------------------
    def _scan(self, base, budget):
        """(rel, lstat) of regular files under base: no hidden names, no symbolic links, bounded depth and entries."""
        out = []
        stack = [(base, '', 0)]
        while stack and budget[0] > 0:
            folder, prefix, depth = stack.pop()
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        budget[0] -= 1
                        if budget[0] <= 0:
                            break
                        if entry.name.startswith('.') or entry.is_symlink():
                            continue
                        rel = prefix + entry.name
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if depth + 1 < MAX_DEPTH:
                                    stack.append((Path(entry.path), rel + '/', depth + 1))
                            elif entry.is_file(follow_symlinks=False):
                                out.append((rel, entry.stat(follow_symlinks=False)))
                        except OSError:
                            continue
            except OSError:
                continue
        return out

    def listing(self, kind='all', area='files', offset=0, limit=50, jobs=(), categories=(), q='', sort='newest'):
        """One page of saved files. kind: the old All/Video/Audio/Other tabs; categories: the chips (any of
        CATEGORIES, empty = all); q: case-insensitive text in the name or the download's title; sort: one of SORTS."""
        if kind not in ('all', 'video', 'audio', 'other') or area not in ('files', 'trash'):
            raise ValueError('Unknown library filter.')
        if type(offset) is not int or type(limit) is not int or not 0 <= offset <= 10 ** 6 or not 1 <= limit <= MAX_PAGE:
            raise ValueError('Invalid page.')
        if isinstance(categories, str):
            categories = parse_categories(categories)
        if not isinstance(categories, (tuple, list)) or any(c not in CATEGORIES for c in categories):
            raise ValueError('Unknown library filter.')
        if sort not in SORTS:
            raise ValueError('Unknown library sort.')
        if not _query_ok(q):
            raise ValueError('Invalid search.')
        needle = ' '.join(q.split()).casefold()
        wanted = frozenset(categories)
        titles = {}
        for job in jobs:
            if job.get('state') == 'completed' and not job.get('demo') and job.get('filepath'):
                titles[str(job['filepath'])] = str(job.get('title') or '')[:200]
        budget = [MAX_SCAN]
        rows = []
        for root_id, (label, root) in self.roots().items():
            base = root / TRASH if area == 'trash' else root
            if area == 'trash':
                try:
                    if not stat.S_ISDIR(os.lstat(base).st_mode):
                        continue
                except OSError:
                    continue
            for rel, info in self._scan(base, budget):
                file_kind, mime = kind_of(rel)
                if kind == 'video' and file_kind != 'video' or kind == 'audio' and file_kind != 'audio' \
                        or kind == 'other' and file_kind in ('video', 'audio'):
                    continue
                category = category_of(rel)
                if wanted and category not in wanted:
                    continue
                folder, _, name = rel.rpartition('/')
                title = titles.get(str(base / rel), '')
                if needle and needle not in name.casefold() and needle not in title.casefold():
                    continue
                rows.append(dict(root_id=root_id, rel=rel, name=name, folder=folder, place=root_id, place_label=label,
                                 size=info.st_size, mtime=int(info.st_mtime), kind=file_kind, mime=mime.split(';')[0],
                                 category=category, job_title=title))
        if sort == 'oldest':
            rows.sort(key=lambda row: (row['mtime'], row['name'].casefold(), row['name']))
        elif sort == 'name':
            rows.sort(key=lambda row: (row['name'].casefold(), row['name'], -row['mtime']))
        elif sort == 'size':
            rows.sort(key=lambda row: (-row['size'], row['name'].casefold(), row['name']))
        elif sort == 'type':
            rows.sort(key=lambda row: (CATEGORIES.index(row['category']), os.path.splitext(row['name'])[1].lower(),
                                       row['name'].casefold(), row['name']))
        else:
            rows.sort(key=lambda row: (-row['mtime'], row['name']))
        page = rows[offset:offset + limit]
        for row in page:
            row['id'] = self.file_id(row.pop('root_id'), area, row.pop('rel'))
        return dict(files=page, total=len(rows), offset=offset, limit=limit, area=area, kind=kind,
                    categories=list(categories), q=q, sort=sort, truncated=budget[0] <= 0)

    def id_for_job(self, job):
        """A finished job's file, if it lies inside a save root (files area)."""
        if not isinstance(job, dict) or job.get('state') != 'completed' or job.get('demo') or not job.get('filepath'):
            raise NotFound('That download has no saved file.')
        target = Path(str(job['filepath']))
        for root_id, (_, root) in self.roots().items():
            try:
                rel = target.relative_to(root)
            except ValueError:
                continue
            rel = '/'.join(rel.parts)
            self._checked(root, 'files', rel)
            return self.file_id(root_id, 'files', rel)
        raise NotFound('That file is not in a save place.')

    def describe(self, fid):
        root_id, area, rel, path, info = self.resolve(fid)
        file_kind, mime = kind_of(rel)
        return dict(id=fid, name=rel.rpartition('/')[2], kind=file_kind, mime=mime.split(';')[0], size=info.st_size,
                    area=area, place=root_id, folder=rel.rpartition('/')[0])   # OMNI_DL_FOLDER_PLAY_V1: as the Library rows show it

    # ---- signed stream links -----------------------------------------------------------------------------------
    def sign(self, fid, exp):
        return hmac.new(self.key, ('stream\0%s\0%d' % (fid, exp)).encode(), hashlib.sha256).hexdigest()

    def link(self, fid):
        self.resolve(fid)
        exp = int(self.now()) + LINK_TTL
        return '/api/files/stream?id=%s&exp=%d&sig=%s' % (fid, exp, self.sign(fid, exp)), exp

    def check_link(self, fid, exp, sig):
        if not isinstance(fid, str) or not _ID.fullmatch(fid) or not isinstance(sig, str) or not _SIG.fullmatch(sig) \
                or not isinstance(exp, str) or not exp.isdigit() or len(exp) > 12:
            return False
        exp = int(exp)
        now = int(self.now())
        if exp < now or exp > now + LINK_TTL + 60:
            return False
        return hmac.compare_digest(self.sign(fid, exp), sig)

    def open(self, fid):
        """(file object, size, kind, mime, name) for a checked file, opened without following links."""
        root_id, area, rel, path, before = self.resolve(fid)
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        try:
            handle = os.fdopen(os.open(path, flags), 'rb')
        except OSError:
            raise NotFound('The file is gone.')
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            handle.close()
            raise NotFound('The file changed while opening.')
        file_kind, mime = kind_of(rel)
        return handle, opened.st_size, file_kind, mime, rel.rpartition('/')[2]

    # ---- trash ------------------------------------------------------------------------------------------------
    def _free(self, target):
        stem, ext = os.path.splitext(target.name)
        for n in range(1, 1000):
            candidate = target.with_name(stem + ext if n == 1 else '%s (%d)%s' % (stem, n, ext))
            if not os.path.lexists(candidate):
                return candidate
        raise ValueError('Too many files with this name.')

    def _make_dirs(self, root, folder):
        """Create root/<folder parts> one level at a time, refusing any symbolic link on the way."""
        path = root
        for part in folder:
            path = path / part
            try:
                os.mkdir(path)
            except FileExistsError:
                pass
            if not stat.S_ISDIR(os.lstat(path).st_mode):
                raise ValueError('The folder is not a plain folder.')
        return path

    def _prune(self, folder, stop):
        while folder != stop and stop in folder.parents:
            try:
                os.rmdir(folder)
            except OSError:
                return
            folder = folder.parent

    def trash(self, fid):
        root_id, area, rel, path, _ = self.resolve(fid)
        if area != 'files':
            raise ValueError('That file is already in the trash.')
        root = self.roots()[root_id][1]
        parts = rel.split('/')
        folder = self._make_dirs(root, [TRASH] + parts[:-1])
        target = self._free(folder / parts[-1])
        os.rename(path, target)
        return dict(trashed=True, id=self.file_id(root_id, 'trash', '/'.join(target.relative_to(root / TRASH).parts)))

    def restore(self, fid):
        root_id, area, rel, path, _ = self.resolve(fid)
        if area != 'trash':
            raise ValueError('Only a file in the trash can be restored.')
        root = self.roots()[root_id][1]
        parts = rel.split('/')
        folder = self._make_dirs(root, parts[:-1])
        target = self._free(folder / parts[-1])
        os.rename(path, target)
        self._prune(path.parent, root / TRASH)
        return dict(restored=True, id=self.file_id(root_id, 'files', '/'.join(target.relative_to(root).parts)))

    def delete(self, fid):
        root_id, area, rel, path, _ = self.resolve(fid)
        if area != 'trash':
            raise ValueError('Move the file to the trash first; only files in the trash can be deleted.')
        os.unlink(path)
        self._prune(path.parent, self.roots()[root_id][1] / TRASH)
        with self.lock:
            self.index.pop(fid, None)
        return dict(deleted=True)
