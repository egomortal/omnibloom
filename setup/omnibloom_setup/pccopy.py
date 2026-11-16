"""Copy Omni's screenshots and the Downloads app's saved files from the PS5 to this PC.

What is looked at on the console (read-only unless the user ticks "move to the trash"):
    /data/omni/downloads/media-worker/Saved/                the Downloads app's "Console storage" save place
        Screenshots/<host>-<yyyymmdd>-<hhmmss>.png          Omni's screenshots (the Downloads > Saved > Screenshots tab)
        ... every other file                                saved downloads (any sub-folder)
        .trash/                                             the app's trash (mirrors the layout): never listed
Hidden names (starting with ".") are skipped everywhere, the same way the Downloads app's library does.

On the PC:  screenshots -> <Pictures>\\Omnibloom\\<name>          (default Pictures\\Omnibloom)
            downloads   -> <Downloads>\\Omnibloom\\<sub folders>\\<name>
Each file is fetched into "<name>.part" and renamed only when every byte arrived, so a stopped copy leaves no half
file; the next run carries on from where the .part ends (FTP REST). A file already on the PC with the same size and
the console's time (to the minute) is skipped; same size but a different time is fetched once and compared by
SHA-256 (identical: skipped). A different file under the same name is saved as "<name> (2).<ext>".

"Move to the trash after copying" (off by default) never deletes: it renames the console file into Saved/.trash/
(same sub-folder, " (n)" when taken), exactly where the Downloads app's own Delete puts it, so the app's Restore
brings it back. Only files whose copy on the PC was verified (size) are moved.

Console names are untrusted: names with control characters, slashes or ".." are skipped; every PC name is cleaned
for Windows (<>:"/\\|?* and control characters replaced, trailing dots/spaces removed, reserved device names
prefixed, length capped) and every target is checked to stay inside its folder. Logs name counts only.
"""
import calendar
import datetime
import hashlib
import os
import posixpath
import re
import shutil
import time
from collections import namedtuple

ROOT = "/data/omni/downloads/media-worker/Saved"
SHOTS = "Screenshots"
TRASH = ".trash"
MAX_DEPTH = 8
MAX_ENTRIES = 20000
SPACE_MARGIN = 64 * 1024 * 1024        # keep this much free on the PC after the copy
NAME_MAX = 150                         # characters per PC path part
CHUNK = 256 * 1024

Item = namedtuple("Item", "rel name size mtime kind group")   # rel: path under ROOT ("Screenshots/x.png")


class CopyError(Exception):
    """A copy that can't be done; the message is for the user."""


class Cancelled(Exception):
    pass


# -- kinds --------------------------------------------------------------------------------------------------------
KIND_LABELS = (("screenshot", "Screenshots"), ("video", "Videos"), ("audio", "Music and audio"),
               ("image", "Pictures"), ("other", "Other files"))
_EXT = {}
for _k, _exts in (("video", ".mp4 .m4v .webm .mkv .mov .ts .ogv .avi"),
                  ("audio", ".m4a .mp3 .aac .ogg .oga .opus .flac .wav .weba"),
                  ("image", ".png .jpg .jpeg .gif .webp .bmp")):
    for _e in _exts.split():
        _EXT[_e] = _k
_SHOT_RE = re.compile(r"-(\d{8})-(\d{6})\.png\Z", re.I)


def kind_of(rel):
    if rel.startswith(SHOTS + "/") and rel.lower().endswith(".png"):
        return "screenshot"
    return _EXT.get(os.path.splitext(rel)[1].lower(), "other")


def shot_time(name):
    """Epoch seconds from <host>-<yyyymmdd>-<hhmmss>.png (the console's local clock, taken as UTC), or None."""
    m = _SHOT_RE.search(name)
    if not m:
        return None
    try:
        return calendar.timegm(datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timetuple())
    except ValueError:
        return None


# -- console names ------------------------------------------------------------------------------------------------
def safe_console_name(name):
    """A name from the console that is fine to ask for over FTP and to map to the PC."""
    return (isinstance(name, str) and 0 < len(name) <= 255 and name not in (".", "..") and not name.startswith(".")
            and "/" not in name and "\\" not in name and not any(ord(c) < 0x20 or ord(c) == 0x7f for c in name))


_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$", "clock$"} | {"com%d" % i for i in range(10)} | \
            {"lpt%d" % i for i in range(10)} | {"com%s" % c for c in "¹²³"} | \
            {"lpt%s" % c for c in "¹²³"}


def windows_name(name):
    """One path part made safe for Windows (never empty, never "." or "..")."""
    out = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 0x20 or ord(c) == 0x7f else c for c in str(name))
    out = out.rstrip(" .").lstrip(" ")
    if not out or set(out) <= {"."}:
        out = "_"
    if out.split(".", 1)[0].rstrip(" ").lower() in _RESERVED:
        out = "_" + out
    if len(out) > NAME_MAX:
        stem, ext = os.path.splitext(out)
        ext = ext if len(ext) <= 16 else ""
        out = stem[:NAME_MAX - len(ext)].rstrip(" .") + ext
    return out


def _inside(root, path):
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    try:
        return os.path.commonpath([root, path]) == root and path != root
    except ValueError:            # another drive
        return False


def local_path(item, pictures, downloads):
    """Where an item goes on the PC, or None when it would leave its folder."""
    parts = item.rel.split("/")
    if item.group == "screenshots":
        base, parts = pictures, parts[1:]
    else:
        base = downloads
    if not parts:
        return None
    target = os.path.join(base, *[windows_name(p) for p in parts])
    return target if _inside(base, target) else None


def default_folders(home=None):
    """(Pictures\\Omnibloom, Downloads\\Omnibloom) of this user."""
    home = home or os.path.expanduser("~")
    return os.path.join(home, "Pictures", "Omnibloom"), os.path.join(home, "Downloads", "Omnibloom")


# -- listing ---------------------------------------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                       "dec"), 1)}


def _utc(y, mo, d, h, mi):
    return calendar.timegm(datetime.datetime(y, mo, d, h, mi).timetuple())     # ValueError on Feb 31


def parse_list_time(month, day, year_or_time, now=None):
    """Epoch seconds (UTC) of an `ls -l` date ("Nov 16 12:00" or "Nov 16 2025"), or None."""
    mon = _MONTHS.get(month[:3].lower())
    if not mon or not day.isdigit():
        return None
    now = now or time.time()
    try:
        if ":" in year_or_time:
            hh, mm = year_or_time.split(":", 1)
            year = time.gmtime(now).tm_year
            t = _utc(year, mon, int(day), int(hh), int(mm))
            if t > now + 86400:                  # no year means "within the last six months"
                t = _utc(year - 1, mon, int(day), int(hh), int(mm))
            return t
        return _utc(int(year_or_time), mon, int(day), 0, 0)
    except (ValueError, OverflowError):
        return None


def list_dir(console, path):
    """{name: {"dir", "size", "mtime"}} of a console folder ({} when missing). Over FTP the LIST times are read too;
    a console object without an FTP session (tests) falls back to its `listing`."""
    ftp = getattr(console, "ftp", None)
    if ftp is None:
        return {n: dict(e, mtime=e.get("mtime")) for n, e in (console.listing(path) or {}).items()}
    import ftplib
    lines = []
    try:
        ftp.retrlines("LIST " + path.rstrip("/") + "/", lines.append)
    except ftplib.error_perm:
        return {}
    out = {}
    for line in lines:
        parts = line.split(None, 8)
        if len(parts) < 9 or parts[8] in (".", ".."):
            continue
        try:
            size = int(parts[4])
        except ValueError:
            size = -1
        out[parts[8]] = {"dir": line.startswith("d"), "size": size, "link": line.startswith("l"),
                         "mtime": parse_list_time(parts[5], parts[6], parts[7])}
    return out


def scan(console):
    """Everything that can be copied: {"items": [Item] newest first, "skipped": names refused, "truncated": bool}."""
    items, skipped, budget = [], 0, [MAX_ENTRIES]
    stack = [("", 0)]
    while stack:
        rel_dir, depth = stack.pop()
        entries = list_dir(console, ROOT + ("/" + rel_dir if rel_dir else ""))
        for name, e in sorted(entries.items()):
            budget[0] -= 1
            if budget[0] < 0:
                break
            if name.startswith("."):          # .trash and other hidden names: never
                continue
            if not safe_console_name(name) or e.get("link"):
                skipped += 1
                continue
            rel = rel_dir + "/" + name if rel_dir else name
            if e.get("dir"):
                if depth + 1 < MAX_DEPTH:
                    stack.append((rel, depth + 1))
                continue
            if e.get("size", -1) < 0:
                skipped += 1
                continue
            kind = kind_of(rel)
            mtime = e.get("mtime")
            if kind == "screenshot":
                mtime = shot_time(name) or mtime
            items.append(Item(rel, name, e["size"], mtime, kind, "screenshots" if kind == "screenshot" else "downloads"))
        if budget[0] < 0:
            break
    items.sort(key=lambda i: (-(i.mtime or 0), i.rel))
    return {"items": items, "skipped": skipped, "truncated": budget[0] < 0}


def select(items, kinds=None, since=None, until=None):
    """The items of the given kinds (None: all) whose time is within [since, until) (epoch seconds, None: open)."""
    out = []
    for it in items:
        if kinds is not None and it.kind not in kinds:
            continue
        if since is not None and (it.mtime is None or it.mtime < since):
            continue
        if until is not None and (it.mtime is None or it.mtime >= until):
            continue
        out.append(it)
    return out


# -- copying ---------------------------------------------------------------------------------------------------------
def _free_local(target, taken):
    stem, ext = os.path.splitext(target)
    for n in range(2, 1000):
        cand = "%s (%d)%s" % (stem, n, ext)
        if cand not in taken and not os.path.lexists(cand) and not os.path.lexists(cand + ".part"):
            return cand
    raise CopyError("Too many files with the same name in %s." % os.path.dirname(target))


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _same_time(a, b):
    return a is not None and b is not None and abs(a - b) < 61


def _already_copied(target, item):
    """The PC file (target, or an earlier "name (n).ext" of it) with the item's size and time, else None."""
    stem, ext = os.path.splitext(target)
    for n in range(1, 1000):
        cand = target if n == 1 else "%s (%d)%s" % (stem, n, ext)
        if not os.path.lexists(cand):
            if n > 1:
                return None
            continue
        if os.path.isfile(cand) and os.path.getsize(cand) == item.size and _same_time(os.path.getmtime(cand), item.mtime):
            return cand
    return None


def _fetch(console, path, part, size, progress_bytes, cancel):
    """Fetch `path` into `part`, carrying on after what's already in it. Returns the part's final size."""
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if have > size:
        os.remove(part)
        have = 0
    if have == size:
        return have
    progress_bytes(have)
    ftp = getattr(console, "ftp", None)
    with open(part, "ab") as f:
        def sink(block):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            f.write(block)
            progress_bytes(len(block))
        if ftp is not None:
            try:
                ftp.retrbinary("RETR " + path, sink, blocksize=CHUNK, rest=have or None)
            except Cancelled:
                try:
                    ftp.abort()
                except Exception:
                    pass
                raise
        else:
            data = console.read(path)
            for i in range(have, len(data), CHUNK):
                sink(data[i:i + CHUNK])
    return os.path.getsize(part)


def needed_bytes(items, pictures, downloads):
    """Bytes still to fetch for these items (what's already in a .part or identical on the PC is not counted)."""
    total = 0
    for it in items:
        target = local_path(it, pictures, downloads)
        if not target:
            continue
        if _already_copied(target, it):
            continue
        part = target + ".part"
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        total += max(it.size - (have if have <= it.size else 0), 0)
    return total


def _free_space(folder):
    probe = os.path.abspath(folder)
    while not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return shutil.disk_usage(probe).free


def check_space(items, pictures, downloads, free=_free_space):
    """Raise CopyError when the PC lacks the room (per drive) for what's still to fetch."""
    need = {}
    for it in items:
        base = pictures if it.group == "screenshots" else downloads
        drive = os.path.splitdrive(os.path.abspath(base))[0].lower() or "/"
        need.setdefault(drive, [base, 0])[1] += needed_bytes([it], pictures, downloads)
    for drive, (base, n) in need.items():
        if n and free(base) < n + SPACE_MARGIN:
            raise CopyError("Not enough free space on this PC (%s): %d MB needed, %d MB free." % (
                drive or base, (n + SPACE_MARGIN) // 1048576, free(base) // 1048576))


def _trash(console, item):
    """Move ROOT/<rel> to ROOT/.trash/<rel> (" (n)" when taken), like the Downloads app's Delete. Returns new rel."""
    parts = item.rel.split("/")
    folder = ROOT + "/" + TRASH + ("/" + "/".join(parts[:-1]) if len(parts) > 1 else "")
    console.makedirs(folder)
    taken = set(list_dir(console, folder))
    stem, ext = posixpath.splitext(parts[-1])
    for n in range(1, 1000):
        cand = parts[-1] if n == 1 else "%s (%d)%s" % (stem, n, ext)
        if cand not in taken:
            console.rename(ROOT + "/" + item.rel, folder + "/" + cand)
            return posixpath.join(folder[len(ROOT) + 1:], cand)
    raise CopyError("Too many files with this name in the trash.")


def copy(console, items, pictures, downloads, move_to_trash=False, progress=None, cancel=None, log=lambda m: None,
         free=_free_space):
    """Copy `items` (from scan) to the PC. progress(done_bytes, total_bytes, index, count) is called as it goes.
    Returns {"copied", "same", "renamed", "bytes", "trashed", "failed": [(rel, reason)], "pictures", "downloads"}."""
    check_space(items, pictures, downloads, free)
    total = sum(it.size for it in items)
    done = [0]
    res = {"copied": 0, "same": 0, "renamed": 0, "bytes": 0, "trashed": 0, "failed": [], "pictures": pictures,
           "downloads": downloads}
    taken = set()
    for idx, it in enumerate(items):
        if cancel is not None and cancel.is_set():
            break
        start = done[0]

        def tick(n):
            done[0] += n
            if progress:
                progress(done[0], total, idx, len(items))

        target = local_path(it, pictures, downloads)
        if not target or not safe_console_name(it.name) or any(not safe_console_name(p) for p in it.rel.split("/")):
            res["failed"].append((it.rel, "name not allowed"))
            continue
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if target in taken:
                target = _free_local(target, taken)
            exists = os.path.isfile(target)
            earlier = _already_copied(target, it)
            if earlier:
                res["same"] += 1
                tick(it.size)
                final = earlier
            else:
                part = target + ".part"
                got = _fetch(console, ROOT + "/" + it.rel, part, it.size, tick, cancel)
                if got != it.size:
                    res["failed"].append((it.rel, "incomplete (%d of %d bytes)" % (got, it.size)))
                    done[0] = start + it.size
                    continue
                if exists and os.path.getsize(target) == it.size and _sha(target) == _sha(part):
                    os.remove(part)
                    res["same"] += 1
                    final = target
                else:
                    final = target
                    if exists:
                        final = _free_local(target, taken)
                        res["renamed"] += 1
                    os.replace(part, final)
                    if it.mtime is not None:
                        os.utime(final, (it.mtime, it.mtime))
                    res["copied"] += 1
                    res["bytes"] += it.size
            taken.add(final)
        except Cancelled:
            break
        except OSError as e:
            res["failed"].append((it.rel, str(e.strerror or e)))
            done[0] = start + it.size
            continue
        if move_to_trash and os.path.getsize(final) == it.size:
            try:
                _trash(console, it)
                res["trashed"] += 1
            except Exception as e:  # the PC copy is fine; the console file just stays where it was
                res["failed"].append((it.rel, "copied, but not moved to the trash: %s" % e))
    res["cancelled"] = bool(cancel is not None and cancel.is_set())
    log("Copy to PC: %d copied, %d already there, %d renamed, %d moved to the trash, %d failed%s." % (
        res["copied"], res["same"], res["renamed"], res["trashed"], len(res["failed"]),
        " (stopped)" if res["cancelled"] else ""))
    return res
