"""Seed Omni with your most-visited sites (S14): the top sites from this PC's browser history become a "Most visited"
bookmarks folder in Omni. Opt-in and previewed: nothing is read until you press the button, you see the list and untick
what you don't want, and only the chosen sites' home pages (https://host/) and a short title go to the console, through
the same bookmarks import as the rest of Setup (nothing already in Omni is removed; the old file is kept as a backup).

Read-only: each profile's History (Chromium) or places.sqlite (Firefox) is copied to a temp folder first (the browser
may hold a lock) and opened read-only. Never sent anywhere else; logs carry counts only, never a site.
Skipped: non-web addresses, IP addresses, localhost / .local / .internal / .lan / .home.arpa names, and anything whose
host looks like a login, mail or bank page (those you can still add yourself)."""
import ipaddress
import os
import shutil
import sqlite3
import tempfile
import urllib.parse
from collections import namedtuple

from . import bookmarks

TOP = 20
SCAN = 2000          # rows read per profile (most visited first)
FOLDER = "Most visited"
Site = namedtuple("Site", "host url title visits")
_LOCAL_SUFFIX = (".local", ".internal", ".lan", ".home.arpa", ".localdomain", ".intranet", ".corp")
_SENSITIVE = ("login.", "accounts.", "account.", "signin.", "auth.", "id.", "mail.", "webmail.", "outlook.",
              "bank", "banking", "paypal.", "secure.")


def site_of(url):
    """The host a history row counts for (lower case, without "www."/"m."), or None for anything not worth a tile."""
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    if host == "localhost" or "." not in host or host.endswith(_LOCAL_SUFFIX):
        return None
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix) and host.count(".") >= 2:
            host = host[len(prefix):]
    if any(host.startswith(s) or ("." + s) in host or s in host.split(".")[0] for s in _SENSITIVE):
        return None
    return host[:253]


def aggregate(rows, top=TOP):
    """rows: (url, title, visits). -> [Site] sorted by visits (ties: host), at most `top`. The title is the one of the
    host's most visited row (cleaned like a bookmark title), else the host itself."""
    by = {}
    for url, title, visits in rows:
        host = site_of(url)
        if not host:
            continue
        try:
            n = max(0, int(visits or 0))
        except (TypeError, ValueError):
            continue
        cur = by.get(host)
        if cur is None:
            by[host] = [n, n, title or ""]
        else:
            cur[0] += n
            if n > cur[1]:
                cur[1], cur[2] = n, title or cur[2]
    ranked = sorted(by.items(), key=lambda kv: (-kv[1][0], kv[0]))[:top]
    out = []
    for host, (total, _best, title) in ranked:
        clean = bookmarks.clean_title(title) if title else ""
        out.append(Site(host, "https://%s/" % host, clean or host, total))
    return out


def _read(db_path, query):
    tmp = tempfile.mkdtemp(prefix="omni-topsites-")
    try:
        copy = os.path.join(tmp, "h.sqlite")
        shutil.copyfile(db_path, copy)
        db = sqlite3.connect(__import__("pathlib").Path(copy).as_uri() + "?mode=ro", uri=True)
        try:
            return db.execute(query, (SCAN,)).fetchall()
        finally:
            db.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CHROMIUM_QUERY = "SELECT url, title, visit_count FROM urls WHERE hidden = 0 ORDER BY visit_count DESC LIMIT ?"
FIREFOX_QUERY = "SELECT url, title, visit_count FROM moz_places WHERE hidden = 0 ORDER BY visit_count DESC LIMIT ?"


def history_path(source):
    """The history database next to a bookmarks Source (same profile)."""
    if source.kind == "chromium":
        return os.path.join(os.path.dirname(source.path), "History")
    return source.path   # Firefox keeps history and bookmarks in places.sqlite


def read_history(source):
    path = history_path(source)
    if not os.path.isfile(path):
        return []
    return _read(path, CHROMIUM_QUERY if source.kind == "chromium" else FIREFOX_QUERY)


def top_sites(sources, top=TOP, log=lambda m: None):
    """The top sites over the chosen profiles (history rows from all of them are pooled)."""
    rows = []
    for s in sources:
        try:
            rows += read_history(s)
        except (OSError, sqlite3.Error) as e:
            s.error = type(e).__name__
    sites = aggregate(rows, top)
    log("Most visited: %d sites from %d profiles." % (len(sites), len(sources)))
    return sites


def as_bookmarks(sites):
    return [bookmarks.Bookmark(s.url, s.title, False, FOLDER) for s in sites]


def import_sites(console, sites, log=lambda m: None):
    """Add the chosen sites to Omni as the "Most visited" folder (bookmarks.import_to_console: merge, backup)."""
    return bookmarks.import_to_console(console, as_bookmarks(sites), log)
