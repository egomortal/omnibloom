"""Import the PC's browser bookmarks into Omni (/data/omni/bookmarks.txt), or sync both ways.

Reads Chrome, Edge and Brave (the Chromium "Bookmarks" file in each profile) and Firefox (places.sqlite, copied to a temp
folder first because Firefox keeps it locked; the copy is opened read-only). Only http:// and https:// pages are kept,
and bookmarklets (javascript: addresses, up to 64 KB; Omni runs them since OMNI_BOOKMARKLETS_V1), each address once, bookmarks-bar / toolbar ones first, so they win when Omni's 500-bookmark limit is reached.

On the console nothing is removed: the bookmarks already there stay exactly as they are (same bytes, same order) and new
ones are added after them. The old file is parked beside the new one (like every other Setup write).

Each bookmark keeps one folder level: the folder it sits in directly under the bookmarks bar / Other / the Firefox menu
(deeper folders go into that top folder), written as Omni's third column (`url TAB title TAB folder`).

Sync (plan_sync / apply_sync): bookmarks only on the PC are added to the console as above; bookmarks only in Omni are
written to a Netscape-format HTML file the user imports into their browser themselves (the browser's own profile files
are never written). Two bookmarks are the same page when url_key() matches: host case, a trailing slash and tracking
parameters (utm_* and the like) don't count; bookmarklets are the same only when the whole address is. Nothing is removed
in either direction.

Bookmarks are personal: this module never logs an address or a title; only counts leave it, and the bookmarks themselves
go nowhere but the console (and, for a sync, the HTML file on this PC).
"""
import configparser
import datetime
import html
import json
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
from collections import namedtuple

from . import config

# bar: on the bookmarks bar / Firefox toolbar; folder: its (top-level) folder, "" when none
Bookmark = namedtuple("Bookmark", "url title bar folder", defaults=("",))


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
JS_SCHEME = "javascript:"
_C0_SPACE = "".join(chr(c) for c in range(0x21))


def is_bookmarklet(url):
    """True for a javascript: address (any case), as Omni tells a bookmarklet line from a web page."""
    if isinstance(url, bytes):
        return url[:len(JS_SCHEME)].lower() == JS_SCHEME.encode()
    return isinstance(url, str) and url[:len(JS_SCHEME)].lower() == JS_SCHEME


def _clean_bookmarklet(url):
    """A javascript: address cleaned the way browsers clean an address (URL Standard): leading / trailing C0 controls and
    spaces dropped, every tab, LF and CR removed (a browser drops them too, so they are never part of the code), any other
    control character percent-encoded. The rest stays exactly as it is (its %XX escapes are the code). None when empty
    or over OMNI_BOOKMARKLET_URL_MAX bytes (a cut bookmarklet is broken code)."""
    url = url.strip(_C0_SPACE).replace("\t", "").replace("\n", "").replace("\r", "")
    if not is_bookmarklet(url) or not url[len(JS_SCHEME):]:
        return None
    url = "".join("%%%02X" % ord(c) if ord(c) < 0x20 or ord(c) == 0x7f else c for c in url)
    try:
        size = len(url.encode("utf-8"))
    except UnicodeEncodeError:
        return None
    return url if size <= config.OMNI_BOOKMARKLET_URL_MAX else None


def clean_url(url):
    """The address as Omni will store it, or None when Omni can't take it (not a web page or bookmarklet, too long, odd
    characters). Web pages: http / https, at most OMNI_BOOKMARK_URL_MAX bytes; bookmarklets: see _clean_bookmarklet."""
    if not isinstance(url, str):
        return None
    if is_bookmarklet(url.lstrip(_C0_SPACE)):
        return _clean_bookmarklet(url)
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


def _clean_text(text, limit):
    if not isinstance(text, str):
        return ""
    text = "".join(" " if (c.isspace() or ord(c) < 0x20 or ord(c) == 0x7f) else c for c in text)
    text = " ".join(text.split())
    data = text.encode("utf-8", "replace")
    if len(data) > limit:
        data = data[:limit].decode("utf-8", "ignore").encode("utf-8")
        return data.decode("utf-8").rstrip()
    return data.decode("utf-8")


def clean_title(title):
    """One line, no tabs or control characters, at most OMNI_BOOKMARK_TITLE_MAX bytes of UTF-8 (cut on a character)."""
    return _clean_text(title, config.OMNI_BOOKMARK_TITLE_MAX)


def clean_folder(folder):
    """A folder name as Omni stores it: one line, no tabs, at most OMNI_BOOKMARK_FOLDER_MAX bytes (cut on a character)."""
    return _clean_text(folder, config.OMNI_BOOKMARK_FOLDER_MAX)


TRACKING_PARAMS = frozenset(("fbclid", "gclid", "dclid", "gbraid", "wbraid", "msclkid", "mc_cid", "mc_eid", "igshid",
                             "yclid", "twclid", "_hsenc", "_hsmi", "mkt_tok", "_ga", "_gl"))


def _is_tracking(name):
    name = urllib.parse.unquote_plus(name).strip().lower()
    return name.startswith("utm_") or name in TRACKING_PARAMS


def url_key(url):
    """What makes two bookmarks the same page: scheme and host in lower case (default port dropped), the path without a
    trailing slash, the query without tracking parameters (utm_*, fbclid, gclid...), the fragment as it is. Anything
    else (a bookmarklet) is matched by its exact address."""
    if isinstance(url, bytes):
        url = url.decode("utf-8", "replace")
    if not isinstance(url, str):
        return ""
    if is_bookmarklet(url):
        return url
    url = url.strip()
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    scheme = p.scheme.lower()
    if scheme not in ("http", "https") or not p.netloc:
        return url
    netloc = p.netloc.lower()
    default = ":80" if scheme == "http" else ":443"
    if netloc.endswith(default):
        netloc = netloc[:-len(default)]
    query = [kv for kv in p.query.split("&") if kv and not _is_tracking(kv.split("=", 1)[0])]
    return (scheme + "://" + netloc + p.path.rstrip("/") + ("?" + "&".join(query) if query else "")
            + ("#" + p.fragment if p.fragment else ""))


# -- readers ----------------------------------------------------------------------------------------------------------
def read_chromium(path):
    """Bookmarks from a Chromium "Bookmarks" file: the bookmarks bar first, then Other and Mobile, in the browser's order."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    roots = doc.get("roots") or {}
    out = []

    def walk(node, bar, folder="", depth=0):
        if not isinstance(node, dict) or depth > 64:
            return
        for child in node.get("children") or []:
            if not isinstance(child, dict):
                continue
            if child.get("type") == "url":
                out.append(Bookmark(child.get("url"), child.get("name") or "", bar, folder))
            else:   # a folder: a top one names the bookmarks in it, deeper ones are folded into it (Omni has one level)
                walk(child, bar, folder or (child.get("name") or ""), depth + 1)

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

    def walk(node_id, bar, folder="", depth=0):
        if node_id in seen or depth > 64:
            return
        seen.add(node_id)
        for row in children.get(node_id, ()):
            if row[1] == 1:
                out.append(Bookmark(row[6], row[4] or "", bar, folder))
            elif row[1] == 2:
                walk(row[0], bar, folder or (row[4] or ""), depth + 1)

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
    """The bookmarks to import from these sources: cleaned, each page once (url_key), bookmarks-bar ones first."""
    items = []
    for s in sources:
        items += s.read()
    items.sort(key=lambda b: not b.bar)      # stable: browser order kept within each group
    out, seen = [], set()
    for b in items:
        url = clean_url(b.url)
        key = url_key(url) if url else None
        if url and key not in seen:
            seen.add(key)
            out.append(Bookmark(url, clean_title(b.title), b.bar, clean_folder(getattr(b, "folder", ""))))
    return out


# -- the console file ------------------------------------------------------------------------------------------------------
def omni_lines(data):
    """The (url, title, folder) bytes Omni loads from this bookmarks.txt, read the way OmniBookmarks.h reads it (fgets
    with a 2400-byte buffer, so a longer line counts as several; the first 500 entries). `url TAB title [TAB folder]`:
    folder is b"" on old two-column lines, and a missing title is the address. A line that starts with "javascript:"
    (any case) is read whole up to OMNI_BOOKMARKLET_LINE_BUFFER - 1 bytes (65934; OmniBookmarkletsFile.h)."""
    out = []
    i, n = 0, len(data)
    while i < n and len(out) < config.OMNI_BOOKMARK_MAX:
        chunk = (config.OMNI_BOOKMARKLET_LINE_BUFFER if is_bookmarklet(data[i:i + len(JS_SCHEME)])
                 else config.OMNI_BOOKMARK_LINE_BUFFER) - 1
        end = data.find(b"\n", i, i + chunk)
        stop = end + 1 if end >= 0 else min(i + chunk, n)
        line = data[i:stop].split(b"\0", 1)[0].rstrip(b"\r\n")
        i = stop
        url, _, rest = line.partition(b"\t")
        title, _, folder = rest.partition(b"\t")
        if url:
            out.append((url, title or url, folder.split(b"\t", 1)[0]))
    return out


def omni_entries(data):
    """The (url, title) pairs Omni loads from this bookmarks.txt (see omni_lines; the folder column isn't the title)."""
    return [(u, t) for u, t, _ in omni_lines(data)]


def _line(b):
    line = b.url.encode("utf-8") + b"\t" + b.title.encode("utf-8")
    folder = clean_folder(getattr(b, "folder", ""))
    if folder:
        line += b"\t" + folder.encode("utf-8")
    return line + b"\n"


def merge(existing, bookmarks):
    """New bookmarks.txt bytes: `existing` unchanged, then the bookmarks Omni doesn't have yet (url_key), while there's
    room. Returns (data, added, already_there, no_room)."""
    existing = existing or b""
    entries = omni_entries(existing)
    have = {url_key(u) for u, _ in entries}
    room = config.OMNI_BOOKMARK_MAX - len(entries)
    lines, already, no_room = [], 0, 0
    for b in bookmarks:
        k = url_key(b.url)
        if k in have:
            already += 1
        elif len(lines) >= room:
            no_room += 1
        else:
            have.add(k)
            lines.append(_line(b))
    if not lines:
        return existing, 0, already, no_room
    data = existing
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data + b"".join(lines), len(lines), already, no_room


def read_console_file(console):
    """bookmarks.txt as it is on the console (b"" when there's none yet)."""
    path = config.OMNI_BOOKMARKS
    return console.read(path) if console.exists(path) else b""


def import_to_console(console, bookmarks, log=lambda m: None):
    """Add `bookmarks` to Omni's bookmarks on the console. Nothing already there is removed; the old file is parked as
    bookmarks.txt.before-setup-<time>. Returns {"added", "already", "no_room", "total"}."""
    from . import installer   # here, so this module loads without the installer's imports
    path = config.OMNI_BOOKMARKS
    existing = read_console_file(console)
    data, added, already, no_room = merge(existing, bookmarks)
    if added:
        installer._replace(console, path, data, ".before-setup-" + installer._stamp())
        if console.read(path) != data:
            raise IOError("Couldn't write Omni's bookmarks; the earlier file was kept beside it as a backup.")
    total = len(omni_entries(data))
    log("Bookmarks: %d added, %d already in Omni, %d left out (Omni keeps up to %d)."
        % (added, already, no_room, config.OMNI_BOOKMARK_MAX))
    return {"added": added, "already": already, "no_room": no_room, "total": total}


def console_bookmarks(data):
    """The bookmarks Omni has, from bookmarks.txt bytes, as Bookmark(url, title, False, folder) strings ("" title when
    the line had none)."""
    out = []
    for u, t, f in omni_lines(data or b""):
        url, title = u.decode("utf-8", "replace"), t.decode("utf-8", "replace")
        out.append(Bookmark(url, "" if t == u else title, False, f.decode("utf-8", "replace")))
    return out


# -- two-way sync ------------------------------------------------------------------------------------------------------------
class SyncPlan:
    """What a sync would do; nothing is changed by making one.
    to_console: PC-only bookmarks Omni has room for. to_pc: Omni-only web pages and bookmarklets, for the HTML file.
    cap_skipped: PC-only bookmarks left out because Omni keeps up to 500. not_web: Omni-only entries that aren't web
    pages or bookmarklets (not exported). in_both: PC bookmarks Omni already has."""

    def __init__(self):
        self.to_console, self.to_pc = [], []
        self.cap_skipped = self.not_web = self.in_both = 0
        self.pc_total = self.console_total = 0

    def counts(self):
        return {"to_console": len(self.to_console), "to_pc": len(self.to_pc), "cap_skipped": self.cap_skipped,
                "not_web": self.not_web, "in_both": self.in_both, "pc_total": self.pc_total,
                "console_total": self.console_total}

    def __repr__(self):   # counts only: never addresses or titles
        return "<SyncPlan %r>" % self.counts()


def plan_sync(pc_marks, console_data):
    """Compare the PC's bookmarks (from collect) with the console's bookmarks.txt bytes."""
    plan = SyncPlan()
    on_console = console_bookmarks(console_data)
    plan.pc_total, plan.console_total = len(pc_marks), len(on_console)
    console_keys = {url_key(b.url) for b in on_console}
    pc_keys = set()
    room = max(0, config.OMNI_BOOKMARK_MAX - len(on_console))
    for b in pc_marks:
        k = url_key(b.url)
        if k in pc_keys:
            continue
        pc_keys.add(k)
        if k in console_keys:
            plan.in_both += 1
        elif len(plan.to_console) >= room:
            plan.cap_skipped += 1
        else:
            plan.to_console.append(b)
    seen = set()
    for b in on_console:
        k = url_key(b.url)
        if k in pc_keys or k in seen:
            continue
        seen.add(k)
        url = clean_url(b.url)
        if not url:
            plan.not_web += 1
            continue
        plan.to_pc.append(Bookmark(url, clean_title(b.title), False, clean_folder(b.folder)))
    return plan


EXPORT_TOP_FOLDER = "From Omni (PS5)"


def export_html(marks, top_folder=EXPORT_TOP_FOLDER):
    """A Netscape bookmarks file (what every browser's "Import bookmarks from HTML file" reads), every text escaped. The
    bookmarks sit in one folder named `top_folder`, Omni's folders inside it, in Omni's order."""
    def esc(s):
        return html.escape(s or "", quote=True)

    def link(b, pad):
        title = b.title or ("Bookmarklet" if is_bookmarklet(b.url) else b.url)   # never the code as a title
        return '%s<DT><A HREF="%s">%s</A>\n' % (pad, esc(b.url), esc(title))

    loose, folders = [], {}
    for b in marks:
        if b.folder:
            folders.setdefault(b.folder, []).append(b)
        else:
            loose.append(b)
    out = ["<!DOCTYPE NETSCAPE-Bookmark-file-1>\n",
           "<!-- Made by Omnibloom Setup: import this file in your browser's bookmark settings. -->\n",
           '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n',
           "<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n",
           "    <DT><H3>%s</H3>\n    <DL><p>\n" % esc(top_folder)]
    for name, items in folders.items():
        out.append("        <DT><H3>%s</H3>\n        <DL><p>\n" % esc(name))
        out += [link(b, " " * 12) for b in items]
        out.append("        </DL><p>\n")
    out += [link(b, " " * 8) for b in loose]
    out.append("    </DL><p>\n</DL><p>\n")
    return "".join(out).encode("utf-8")


# A browser's own files: the export never goes there (nor into a profile folder Setup read from).
PROFILE_FILES = ("bookmarks", "bookmarks.bak", "places.sqlite", "places.sqlite-wal", "local state")


def default_export_path(folder=None, today=None, home=None):
    """<Downloads>/omni-bookmarks-<date>.html, with -2, -3... when that name is taken (nothing is overwritten)."""
    home = home or os.path.expanduser("~")
    if folder is None:
        folder = os.path.join(home, "Downloads")
        if not os.path.isdir(folder):
            folder = home
    day = (today or datetime.date.today()).strftime("%Y-%m-%d")
    path = os.path.join(folder, "omni-bookmarks-%s.html" % day)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "omni-bookmarks-%s-%d.html" % (day, n))
        n += 1
    return path


def write_export(path, marks, sources=()):
    """Write the HTML file for the PC's browser: a new .html file, never a browser's own file or profile folder, never
    over a file that's already there."""
    name = os.path.basename(path).lower()
    if name in PROFILE_FILES or not name.endswith((".html", ".htm")):
        raise ValueError("The bookmarks for this PC go in a new .html file, not into a browser's own files.")
    real = os.path.normcase(os.path.realpath(path))
    for s in sources:
        if not getattr(s, "path", None):
            continue
        prof = os.path.normcase(os.path.realpath(os.path.dirname(s.path)))
        if real.startswith(prof.rstrip(os.sep) + os.sep):
            raise ValueError("The bookmarks for this PC go in a new .html file, not into a browser's own folder.")
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "xb") as f:    # "x": never replaces a file that's already there
        f.write(export_html(marks))
    return path


def apply_sync(console, plan, export_path=None, sources=(), log=lambda m: None):
    """Do what `plan` says. The Omni-only bookmarks go to a new HTML file (`export_path`, default in Downloads); the
    PC-only ones are added to the console (bookmarks.txt is read again first, so nothing saved since the preview is lost;
    the old file is parked as bookmarks.txt.before-setup-<time>). Nothing is deleted anywhere. Logs counts only.
    Returns {"added", "already", "no_room", "total", "exported", "export_path"}."""
    result = {"added": 0, "already": 0, "no_room": plan.cap_skipped, "total": None, "exported": 0, "export_path": None}
    if plan.to_pc:
        result["export_path"] = write_export(export_path or default_export_path(), plan.to_pc, sources)
        result["exported"] = len(plan.to_pc)
    if plan.to_console:
        r = import_to_console(console, plan.to_console)
        result.update(added=r["added"], already=r["already"], no_room=r["no_room"] + plan.cap_skipped, total=r["total"])
    else:
        result["total"] = len(omni_entries(read_console_file(console)))
    log("Bookmark sync: %d added to Omni, %d saved for this PC's browser, %d left out (Omni keeps up to %d), "
        "%d not web pages." % (result["added"], result["exported"], result["no_room"], config.OMNI_BOOKMARK_MAX,
                               plan.not_web))
    return result
