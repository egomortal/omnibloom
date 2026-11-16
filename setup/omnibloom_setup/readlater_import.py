"""Import a "read later" queue (Pocket / Instapaper / any browser bookmarks HTML export) into Omni's bookmarks.

Formats read (picked by looking at the start of the file, never by its name alone):
    pocket_html     Pocket's ril_export.html: <h1>Unread</h1><ul><li><a href=... time_added=... tags=...>title</a>
                    ... <h1>Read Archive</h1><ul>...
    pocket_csv      Pocket's newer CSV: title,url,time_added,tags,status   (status "archive" = read)
    instapaper_csv  Instapaper's CSV: URL,Title,Selection,Folder,Timestamp (folder "Archive" = read)
    netscape        any Netscape bookmark HTML (<!DOCTYPE NETSCAPE-Bookmark-file-1>), the fallback for other services

Everything goes into one Omni bookmarks folder, READ_LATER_FOLDER, or READ_LATER_ARCHIVE_FOLDER for read / archived
items when the user opts in (left out otherwise). Addresses and titles go through bookmarks.clean_url / clean_title, so
Omni's limits hold; javascript: addresses are refused here (a read-later item is a page, never code to run). A page is
a duplicate when its exact cleaned address is already in the file or on the console.

Privacy: the Instapaper "Selection" (highlighted text) is never read into anything unless include_notes is set, and
then it only ends up in the bookmark title in the console's bookmarks.txt. This module never logs an address, title or
note; only counts leave it. Parsing is plain html.parser / csv, streamed in chunks, with caps on bytes and rows read.
"""
import csv
import html.parser
import io
from collections import namedtuple

from . import bookmarks, config

READ_LATER_FOLDER = "Read later"
READ_LATER_ARCHIVE_FOLDER = "Read later/Archive"

MAX_FILE_BYTES = 64 * 1024 * 1024     # a bigger export is read up to here (the rest is counted as not read)
MAX_ROWS = 50000                      # rows / links looked at, at most (Omni keeps OMNI_BOOKMARK_MAX anyway)
MAX_CSV_ERRORS = 1000                 # broken CSV rows tolerated before the rest of the file is given up on
SNIFF_BYTES = 64 * 1024
CHUNK = 64 * 1024

# url, title, archived (read / archived in the service), note (Instapaper selection; "" unless asked for)
Item = namedtuple("Item", "url title archived note", defaults=(False, ""))


class ReadLaterError(ValueError):
    """A file that isn't any of the supported exports."""


# -- format detection --------------------------------------------------------------------------------------------------
def _csv_header(text):
    first = text.lstrip("﻿").splitlines()[0] if text.strip() else ""
    try:
        row = next(csv.reader([first]))
    except (csv.Error, StopIteration):
        return []
    return [c.strip().lower() for c in row]


def detect_format(head):
    """Which export `head` (the first part of the file, as text) starts: "pocket_html", "pocket_csv",
    "instapaper_csv" or "netscape". Raises ReadLaterError for anything else."""
    low = head[:SNIFF_BYTES].lower()
    stripped = low.lstrip("﻿ \t\r\n")
    cols = set() if stripped.startswith("<") else set(_csv_header(head))
    if not ({"url", "title"} <= cols) and (stripped.startswith("<") or "<a " in low):
        if "netscape-bookmark-file" in low:
            return "netscape"
        if "time_added=" in low or "pocket export" in low:
            return "pocket_html"
        if "<a " in low and "href" in low:
            return "netscape"     # some other service's bookmarks-style HTML: links are links
        raise ReadLaterError("This HTML file has no links to import.")
    if {"url", "title"} <= cols and ({"selection", "folder"} & cols):
        return "instapaper_csv"
    if {"url", "title"} <= cols and ({"time_added", "status", "tags"} & cols):
        return "pocket_csv"
    if {"url", "title"} <= cols:
        return "pocket_csv"       # title,url and nothing else: read the same way
    raise ReadLaterError("This isn't a Pocket, Instapaper or bookmarks export Setup knows.")


# -- HTML (Pocket's ril_export.html and Netscape bookmarks) -----------------------------------------------------------
class _LinkParser(html.parser.HTMLParser):
    """Collects (href, text, section heading) for every <a href>; never runs or fetches anything."""

    def __init__(self, archive_sections, limit):
        super().__init__(convert_charrefs=True)
        self.archive_sections = archive_sections
        self.limit = limit
        self.items = []
        self.seen_rows = 0
        self.full = False
        self._heading = None      # text being collected for <h1>..<h3>
        self._section = ""
        self._link = None         # [href, [text parts]]

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "li", "dt", "ul", "dl", "p"):
            self._close_link()    # a missing </a> ends at the next list item, list or heading
        if tag in ("h1", "h2", "h3"):
            self._heading = []
        elif tag == "a":
            self._close_link()
            href = dict(attrs).get("href")
            self._link = [href, []] if href is not None else None

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3") and self._heading is not None:
            self._section = " ".join("".join(self._heading).split())[:200]
            self._heading = None
        elif tag in ("a", "li", "dt", "ul", "dl"):
            self._close_link()

    def handle_data(self, data):
        if self._link is not None and sum(map(len, self._link[1])) < 4096:
            self._link[1].append(data)
        if self._heading is not None and sum(map(len, self._heading)) < 400:
            self._heading.append(data)

    def _close_link(self):
        if self._link is None:
            return
        href, parts = self._link
        self._link = None
        self.seen_rows += 1
        if len(self.items) >= self.limit:
            self.full = True
            return
        archived = self.archive_sections(self._section)
        self.items.append(Item(href, "".join(parts), archived, ""))

    def close(self):
        super().close()
        self._close_link()


def _pocket_archive(section):
    s = section.strip().lower()
    return s in ("read archive", "archive", "archived", "read")


def parse_html(stream, pocket=True, limit=MAX_ROWS):
    """Items from an HTML export read from a text stream in chunks. Pocket: links under a "Read Archive" heading are
    archived. Netscape: folders don't matter, nothing is archived."""
    p = _LinkParser(_pocket_archive if pocket else (lambda s: False), limit)
    read = 0
    while read < MAX_FILE_BYTES and not p.full:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        read += len(chunk)
        p.feed(chunk)
    p.close()
    return p.items, max(0, p.seen_rows - len(p.items))


# -- CSV ---------------------------------------------------------------------------------------------------------------------
class _Capped(io.TextIOBase):
    """A text stream that ends after MAX_FILE_BYTES characters (so a huge file is read in part, never all at once)."""

    def __init__(self, stream, cap=None):
        self.stream, self.left = stream, MAX_FILE_BYTES if cap is None else cap

    def readable(self):
        return True

    def read(self, n=-1):
        if self.left <= 0:
            return ""
        n = self.left if n is None or n < 0 else min(n, self.left)
        data = self.stream.read(n)
        self.left -= len(data)
        return data

    def readline(self, n=-1):
        if self.left <= 0:
            return ""
        n = self.left if n is None or n < 0 else min(n, self.left)
        data = self.stream.readline(n)
        self.left -= len(data)
        return data

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line


def parse_csv(stream, kind, include_notes=False, limit=MAX_ROWS):
    """Items from a Pocket or Instapaper CSV read row by row. Returns (items, bad_rows). Short or broken rows count as
    bad. The Selection column is only read when include_notes is set."""
    reader = csv.reader(_Capped(stream))
    try:
        header = [c.strip().lower().lstrip("﻿") for c in next(reader)]
    except (StopIteration, csv.Error):
        return [], 0
    col = {name: i for i, name in reversed(list(enumerate(header)))}
    iu, it = col.get("url"), col.get("title")
    if iu is None:
        return [], 0
    if kind == "instapaper_csv":
        istate, isel = col.get("folder"), col.get("selection")
    else:
        istate, isel = col.get("status"), None
    items, bad, errors, rows = [], 0, 0, 0
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error:
            bad += 1
            errors += 1
            if errors >= MAX_CSV_ERRORS:
                break
            continue
        if not row or not any(c.strip() for c in row):
            continue
        rows += 1
        if rows > limit:
            bad += 1
            continue
        if iu >= len(row):
            bad += 1
            continue
        state = row[istate].strip().lower() if istate is not None and istate < len(row) else ""
        archived = state in ("archive", "archived", "read")
        note = ""
        if include_notes and isel is not None and isel < len(row):
            note = row[isel]
        items.append(Item(row[iu], row[it] if it is not None and it < len(row) else "", archived, note))
    return items, bad


# -- reading a file ---------------------------------------------------------------------------------------------------------
def _open(path):
    return open(path, encoding="utf-8-sig", errors="replace", newline="")


def read_file(path, include_notes=False):
    """(format, items, bad_rows) from an export file on this PC."""
    with _open(path) as f:
        head = f.read(SNIFF_BYTES)
    kind = detect_format(head)
    with _open(path) as f:
        if kind in ("pocket_html", "netscape"):
            items, bad = parse_html(f, pocket=(kind == "pocket_html"))
        else:
            items, bad = parse_csv(f, kind, include_notes=include_notes)
    return kind, items, bad


# -- turning items into Omni bookmarks ----------------------------------------------------------------------------------------
class Plan:
    """What an import would add. marks: Bookmark tuples for the console. Counts only in repr (never addresses)."""

    def __init__(self):
        self.marks = []
        self.duplicates = self.invalid = self.archived_left_out = 0

    def counts(self):
        return {"to_add": len(self.marks), "duplicates": self.duplicates, "invalid": self.invalid,
                "archived_left_out": self.archived_left_out}

    def __repr__(self):
        return "<ReadLaterPlan %r>" % self.counts()


def plan_import(items, include_archive=False, include_notes=False, bad_rows=0):
    """Clean `items` into Omni bookmarks: web pages only (javascript: and every other scheme are invalid), each exact
    address once, unread first then archived (when include_archive), titles cleaned, notes only when include_notes."""
    plan = Plan()
    plan.invalid = bad_rows
    seen = set()
    ordered = [i for i in items if not i.archived] + [i for i in items if i.archived]
    for it in ordered:
        if it.archived and not include_archive:
            plan.archived_left_out += 1
            continue
        raw = it.url if isinstance(it.url, str) else ""
        url = None if bookmarks.is_bookmarklet(raw.lstrip(bookmarks._C0_SPACE)) else bookmarks.clean_url(raw)
        if not url:
            plan.invalid += 1
            continue
        if url in seen:
            plan.duplicates += 1
            continue
        seen.add(url)
        title = it.title if isinstance(it.title, str) else ""
        note = it.note if include_notes and isinstance(it.note, str) else ""
        if note.strip():
            title = (title.strip() + " - " if title.strip() else "") + note
        folder = READ_LATER_ARCHIVE_FOLDER if it.archived else READ_LATER_FOLDER
        plan.marks.append(bookmarks.Bookmark(url, bookmarks.clean_title(title), False, bookmarks.clean_folder(folder)))
    return plan


def merge_exact(existing, marks):
    """bookmarks.txt bytes with `marks` added after what's there, skipping any exact address Omni already has, while
    there's room under OMNI_BOOKMARK_MAX. Returns (data, added, duplicates, no_room)."""
    existing = existing or b""
    entries = bookmarks.omni_lines(existing)
    have = {u for u, _, _ in entries}
    room = max(0, config.OMNI_BOOKMARK_MAX - len(entries))
    lines, dup, no_room = [], 0, 0
    for b in marks:
        key = b.url.encode("utf-8")
        if key in have:
            dup += 1
        elif len(lines) >= room:
            no_room += 1
        else:
            have.add(key)
            lines.append(bookmarks._line(b))
    if not lines:
        return existing, 0, dup, no_room
    data = existing
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data + b"".join(lines), len(lines), dup, no_room


def import_to_console(console, plan, log=lambda m: None):
    """Add the plan's bookmarks to Omni's bookmarks.txt (nothing already there is changed; the old file is parked as
    bookmarks.txt.before-setup-<time>). Returns {"added", "duplicates", "invalid", "no_room", "archived_left_out",
    "total"}."""
    from . import installer
    path = config.OMNI_BOOKMARKS
    existing = bookmarks.read_console_file(console)
    data, added, dup, no_room = merge_exact(existing, plan.marks)
    if added:
        installer._replace(console, path, data, ".before-setup-" + installer._stamp())
        if console.read(path) != data:
            raise IOError("Couldn't write Omni's bookmarks; the earlier file was kept beside it as a backup.")
    r = {"added": added, "duplicates": plan.duplicates + dup, "invalid": plan.invalid, "no_room": no_room,
         "archived_left_out": plan.archived_left_out, "total": len(bookmarks.omni_lines(data))}
    log(summary(r))
    return r


def summary(r):
    """"Imported N, skipped M duplicates, K invalid" (plus what the cap or the archive choice left out). Counts only."""
    text = "Imported %d, skipped %d duplicate%s, %d invalid" % (
        r["added"], r["duplicates"], "" if r["duplicates"] == 1 else "s", r["invalid"])
    if r.get("no_room"):
        text += ", %d left out (Omni keeps up to %d bookmarks)" % (r["no_room"], config.OMNI_BOOKMARK_MAX)
    if r.get("archived_left_out"):
        text += ", %d read/archived not included" % r["archived_left_out"]
    return text + "."
