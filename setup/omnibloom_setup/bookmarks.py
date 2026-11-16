"""Import the PC's browser bookmarks into Omni (/data/omni/bookmarks.txt).

Reads Chrome, Edge and Brave (the Chromium "Bookmarks" file in each profile) and Firefox (places.sqlite, copied to a temp
folder first because Firefox keeps it locked; the copy is opened read-only). Only http:// and https:// pages are kept,
each address once, bookmarks-bar / toolbar ones first, so they win when Omni's 500-bookmark limit is reached.

On the console nothing is removed: the bookmarks already there stay exactly as they are (same bytes, same order) and new
ones are added after them. The old file is parked beside the new one (like every other Setup write).

Bookmarks are personal: this module never logs an address or a title; only counts leave it, and the bookmarks themselves
go nowhere but the console.
"""
import configparser
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
from collections import namedtuple

from . import config

Bookmark = namedtuple("Bookmark", "url title bar")   # bar: on the bookmarks bar / Firefox toolbar


class Source:
    """One browser profile with bookmarks."""

    def __init__(self, browser, profile, path, kind):
        self.browser, self.profile, self.path, self.kind = browser, profile, path, kind
        self.count = 0          # usable bookmarks (http/https, once each); set by find_sources
        self.error = None       # short reason it couldn't be read (never contents)

    @property
    def label(self):
        return "%s: %s" % (self.browser, self.profile)

    def read(self):
        return read_chromium(self.path) if self.kind == "chromium" else read_firefox(self.path)

    def __repr__(self):   # no paths with user names in logs or test output
        return "<Source %s %d>" % (self.label, self.count)


# -- cleaning (Omni's limits) ---------------------------------------------------------------------------------------
def clean_url(url):
    """The address as Omni will store it, or None when Omni can't take it (not a web page, too long, odd characters)."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    head, sep, rest = url.partition("://")
    if not sep or head.lower() not in ("http", "https") or not rest:
        return None
    url = head.lower() + "://" + rest       # Omni only checks a lower-case "http://" / "https://"
    if any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f for c in url):
        return None
    if len(url.encode("utf-8", "surrogatepass")) > config.OMNI_BOOKMARK_URL_MAX:
        return None                         # cutting an address breaks it: leave it out instead
    try:
        url.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return url


def clean_title(title):
    """One line, no tabs or control characters, at most OMNI_BOOKMARK_TITLE_MAX bytes of UTF-8 (cut on a character)."""
    if not isinstance(title, str):
        return ""
    title = "".join(" " if (c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f) else c for c in title)
    title = " ".join(title.split())
    data = title.encode("utf-8", "replace")
    if len(data) > config.OMNI_BOOKMARK_TITLE_MAX:
        data = data[:config.OMNI_BOOKMARK_TITLE_MAX].decode("utf-8", "ignore").encode("utf-8")
        title = data.decode("utf-8").rstrip()
    else:
        title = data.decode("utf-8")
    return title


# -- readers ----------------------------------------------------------------------------------------------------------
def read_chromium(path):
    """Bookmarks from a Chromium "Bookmarks" file: the bookmarks bar first, then Other and Mobile, in the browser's order."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    roots = doc.get("roots") or {}
    out = []

    def walk(node, bar, depth=0):
        if not isinstance(node, dict) or depth > 64:
            return
        if node.get("type") == "url":
            out.append(Bookmark(node.get("url"), node.get("name") or "", bar))
        for child in node.get("children") or []:
            walk(child, bar, depth + 1)

    walk(roots.get("bookmark_bar"), True)
    for key in ("other", "synced"):
        walk(roots.get(key), False)
    return out


FIREFOX_ROOTS = ("toolbar_____", "menu________", "unfiled_____", "mobile______")


def read_firefox(path):
    """Bookmarks from a Firefox places.sqlite: toolbar first, then the menu, Other and Mobile, in Firefox's order."""
    tmp = tempfile.mkdtemp(prefix="omnibloom-ff-")
    try:
        copy = os.path.join(tmp, "places.sqlite")
        shutil.copyfile(path, copy)
        if os.path.exists(path + "-wal"):           # recent changes live here until Firefox checkpoints
            shutil.copyfile(path + "-wal", copy + "-wal")
        db = sqlite3.connect(pathlib.Path(copy).as_uri() + "?mode=ro", uri=True)
        try:
            rows = db.execute("SELECT b.id, b.type, b.parent, b.position, b.title, b.guid, p.url FROM moz_bookmarks b "
                              "LEFT JOIN moz_places p ON p.id = b.fk").fetchall()
        finally:
            db.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    children = {}
    by_guid = {}
    for row in rows:
        children.setdefault(row[2], []).append(row)
        by_guid[row[5]] = row
    for kids in children.values():
        kids.sort(key=lambda r: (r[3] if r[3] is not None else 0, r[0]))
    out = []
    seen = set()

    def walk(node_id, bar, depth=0):
        if node_id in seen or depth > 64:
            return
        seen.add(node_id)
        for row in children.get(node_id, ()):
            if row[1] == 1:
                out.append(Bookmark(row[6], row[4] or "", bar))
            elif row[1] == 2:
                walk(row[0], bar, depth + 1)

    for guid in FIREFOX_ROOTS:
        if guid in by_guid:
            walk(by_guid[guid][0], guid == "toolbar_____")
    return out


# -- finding profiles ----------------------------------------------------------------------------------------------------
def _chromium_dirs(plat, env, home):
    if plat.startswith("win"):
        local = env.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return [("Chrome", os.path.join(local, "Google", "Chrome", "User Data")),
                ("Edge", os.path.join(local, "Microsoft", "Edge", "User Data")),
                ("Brave", os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"))]
    if plat == "darwin":
        sup = os.path.join(home, "Library", "Application Support")
        return [("Chrome", os.path.join(sup, "Google", "Chrome")),
                ("Edge", os.path.join(sup, "Microsoft Edge")),
                ("Brave", os.path.join(sup, "BraveSoftware", "Brave-Browser"))]
    cfg = env.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return [("Chrome", os.path.join(cfg, "google-chrome")),
            ("Chrome", os.path.join(cfg, "chromium")),
            ("Edge", os.path.join(cfg, "microsoft-edge")),
            ("Brave", os.path.join(cfg, "BraveSoftware", "Brave-Browser"))]


def _firefox_dirs(plat, env, home):
    if plat.startswith("win"):
        return [os.path.join(env.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "Mozilla", "Firefox")]
    if plat == "darwin":
        return [os.path.join(home, "Library", "Application Support", "Firefox")]
    return [os.path.join(home, ".mozilla", "firefox"), os.path.join(home, "snap", "firefox", "common", ".mozilla", "firefox")]


def _chromium_sources(browser, base):
    if not os.path.isdir(base):
        return []
    names = {}
    try:
        with open(os.path.join(base, "Local State"), encoding="utf-8") as f:
            cache = (json.load(f).get("profile") or {}).get("info_cache") or {}
        names = {k: (v or {}).get("name") for k, v in cache.items() if isinstance(v, dict)}
    except (OSError, ValueError, AttributeError):
        pass
    out = []
    for d in sorted(os.listdir(base)):
        path = os.path.join(base, d, "Bookmarks")
        if os.path.isfile(path):
            out.append(Source(browser, names.get(d) or d, path, "chromium"))
    return out


def _firefox_sources(base):
    if not os.path.isdir(base):
        return []
    found = {}   # real path -> name
    ini = configparser.RawConfigParser()
    try:
        ini.read(os.path.join(base, "profiles.ini"), encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        pass
    for sec in ini.sections():
        if not sec.lower().startswith("profile") or not ini.has_option(sec, "Path"):
            continue
        p = ini.get(sec, "Path")
        if ini.has_option(sec, "IsRelative") and ini.get(sec, "IsRelative").strip() == "1" or not os.path.isabs(p):
            p = os.path.join(base, p)
        if os.path.isfile(os.path.join(p, "places.sqlite")):
            found[os.path.realpath(p)] = ini.get(sec, "Name") if ini.has_option(sec, "Name") else None
    for folder in (base, os.path.join(base, "Profiles")):
        if not os.path.isdir(folder):
            continue
        for d in sorted(os.listdir(folder)):
            p = os.path.join(folder, d)
            if os.path.isfile(os.path.join(p, "places.sqlite")):
                found.setdefault(os.path.realpath(p), None)
    out = []
    for p, name in sorted(found.items()):
        d = os.path.basename(p)
        out.append(Source("Firefox", name or (d.split(".", 1)[1] if "." in d else d), os.path.join(p, "places.sqlite"), "firefox"))
    return out


def find_sources(plat=None, env=None, home=None):
    """Every browser profile with bookmarks on this PC, each with `count` (usable bookmarks) or `error` set."""
    plat = plat or sys.platform
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    sources = []
    for browser, base in _chromium_dirs(plat, env, home):
        sources += _chromium_sources(browser, base)
    for base in _firefox_dirs(plat, env, home):
        sources += _firefox_sources(base)
    for s in sources:
        try:
            s.count = len(collect([s]))
        except Exception as e:   # unreadable, locked, odd format: shown as such, never fatal
            s.error = type(e).__name__
    return sources


def collect(sources):
    """The bookmarks to import from these sources: cleaned, each address once, bookmarks-bar ones first."""
    items = []
    for s in sources:
        items += s.read()
    items.sort(key=lambda b: not b.bar)      # stable: browser order kept within each group
    out, seen = [], set()
    for b in items:
        url = clean_url(b.url)
        if url and url not in seen:
            seen.add(url)
            out.append(Bookmark(url, clean_title(b.title), b.bar))
    return out


# -- the console file ------------------------------------------------------------------------------------------------------
def omni_entries(data):
    """The (url, title) pairs Omni loads from this bookmarks.txt, read the way OmniBookmarks.h reads it (fgets with a
    2400-byte buffer, so a longer line counts as several; the first 500 entries)."""
    out = []
    i, n, chunk = 0, len(data), config.OMNI_BOOKMARK_LINE_BUFFER - 1
    while i < n and len(out) < config.OMNI_BOOKMARK_MAX:
        end = data.find(b"\n", i, i + chunk)
        stop = end + 1 if end >= 0 else min(i + chunk, n)
        line = data[i:stop].split(b"\0", 1)[0].rstrip(b"\r\n")
        i = stop
        url, _, title = line.partition(b"\t")
        if url:
            out.append((url, title or url))
    return out


def merge(existing, bookmarks):
    """New bookmarks.txt bytes: `existing` unchanged, then the bookmarks Omni doesn't have yet, while there's room.
    Returns (data, added, already_there, no_room)."""
    existing = existing or b""
    entries = omni_entries(existing)
    have = {u for u, _ in entries}
    room = config.OMNI_BOOKMARK_MAX - len(entries)
    lines, already, no_room = [], 0, 0
    for b in bookmarks:
        u = b.url.encode("utf-8")
        if u in have:
            already += 1
        elif len(lines) >= room:
            no_room += 1
        else:
            have.add(u)
            lines.append(u + b"\t" + b.title.encode("utf-8") + b"\n")
    if not lines:
        return existing, 0, already, no_room
    data = existing
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data + b"".join(lines), len(lines), already, no_room


def import_to_console(console, bookmarks, log=lambda m: None):
    """Add `bookmarks` to Omni's bookmarks on the console. Nothing already there is removed; the old file is parked as
    bookmarks.txt.before-setup-<time>. Returns {"added", "already", "no_room", "total"}."""
    from . import installer   # here, so this module loads without the installer's imports
    path = config.OMNI_BOOKMARKS
    existing = console.read(path) if console.exists(path) else b""
    data, added, already, no_room = merge(existing, bookmarks)
    if added:
        installer._replace(console, path, data, ".before-setup-" + installer._stamp())
        if console.read(path) != data:
            raise IOError("Couldn't write Omni's bookmarks; the earlier file was kept beside it as a backup.")
    total = len(omni_entries(data))
    log("Bookmarks: %d added, %d already in Omni, %d left out (Omni keeps up to %d)."
        % (added, already, no_room, config.OMNI_BOOKMARK_MAX))
    return {"added": added, "already": already, "no_room": no_room, "total": total}
