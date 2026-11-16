"""Export Omni's reading list from the PS5 to a folder on this PC (and, optionally, an EPUB 3 for e-readers).

Read-only on the console: only `listing` and `read` are used on /data/omni/reading-list/ (index.tsv and the saved
*.html pages); nothing there is ever written, renamed or removed.

The index (OMNI_READING_LIST_V1, header "omni-reading-list\\t1"):
    page lines      id \\t savedAt \\t bytes \\t h|t \\t url \\t title       (6 fields; url/title TSV-escaped)
    progress lines  p \\t id \\t permille 0..1000 \\t updated \\t finished-or-0   (5 fields, OMNI_READING_PROGRESS_V1)
parsed exactly the way Omni does (bad lines and repeated ids skipped; a later progress line for an id wins).

On the PC:  <folder>/Omni reading list <date>/index.html  (title, site, date saved, % read, link to each local copy)
            .../pages/<id>                                   (the saved pages, byte for byte)
            .../reading-list.epub                            (optional: the ticked articles)
The export is built in "<name>.part" and renamed when complete, so a stopped export leaves no half folder.

Sanitising. Every index field is untrusted: file names must pass Omni's own id rule ([a-z0-9.-], ends .html, no "..")
and Windows' reserved names are prefixed; every path is checked to stay inside the export folder. In index.html all
text is HTML-escaped, links to live pages are http(s) only, and the page has a CSP with no scripts at all. Saved
pages are copied as they are and never opened or run by Setup. For the EPUB each page is rebuilt from an allow-list
of text elements: scripts, styles, frames, objects, forms and their controls, event handlers, style/class attributes
and every external resource are dropped; images survive only when they were inlined as data: URIs (PNG/JPEG/GIF/WebP,
magic bytes checked), and are stored as files inside the EPUB.

Logs name counts only, never a title, site or file name (the pages are named after the sites).
"""
import base64
import binascii
import datetime
import html
import html.parser
import os
import posixpath
import re
import shutil
import urllib.parse
import uuid
import zipfile
from collections import namedtuple

DIR = "/data/omni/reading-list"
INDEX = DIR + "/index.tsv"
HEADER = "omni-reading-list\t1"
KiB, MiB = 1024, 1024 * 1024
INDEX_MAX = 4 * MiB             # backup.py's cap for index.tsv
PAGE_MAX = 32 * MiB             # Omni's cap for one saved file
MAX_COUNT = 200                 # Omni keeps at most 200 pages
WARN_BYTES = 500 * MiB          # ask before copying more than this
MAX_TOTAL = 640 * MiB           # never copy more than this
EPUB_IMAGE_MAX = 8 * MiB        # one decoded image in the EPUB
EPUB_MAX = 256 * MiB            # all EPUB content together (text + images)
FINISHED = 950                  # permille: Omni's "Finished"

Page = namedtuple("Page", "id saved_at bytes text_only url title permille finished_at size")


class ExportError(Exception):
    """An export that can't be done; the message is for the user."""


# -- the index (mirrors OmniReadingList.h / OmniReadingProgress.h) ---------------------------------------------------------
_ID_RE = re.compile(r"[a-z0-9][a-z0-9.-]*\Z")


def valid_id(page_id):
    """Omni's validId: [a-z0-9.-], starts with a letter or digit, ends ".html", 6..140 characters, no ".."."""
    return (isinstance(page_id, str) and 6 <= len(page_id) <= 140 and page_id.endswith(".html")
            and ".." not in page_id and bool(_ID_RE.match(page_id)))


def unescape_field(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c != "\\" or i + 1 >= len(s):
            out.append(c)
            i += 1
            continue
        n = s[i + 1]
        out.append({"t": "\t", "n": "\n", "r": "\r"}.get(n, n))
        i += 2
    return "".join(out)


def _number(s):
    if not s or len(s) > 18 or not all("0" <= c <= "9" for c in s):
        return None
    return int(s)


def parse_index(text):
    """[Page] in index order (size None) from index.tsv's text. A wrong header gives []."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != HEADER:
        return []
    pages, seen, progress = [], set(), {}
    for line in lines[1:]:
        if line.endswith("\r"):
            line = line[:-1]
        if not line:
            continue
        f = line.split("\t")
        if len(f) == 5 and f[0] == "p":
            if not valid_id(f[1]):
                continue
            pm, up, fin = _number(f[2]), _number(f[3]), _number(f[4])
            if pm is None or up is None or fin is None or pm > 1000 or up <= 0:
                continue
            if pm >= FINISHED and not fin:
                fin = up
            progress[f[1]] = (pm, fin)
            continue
        if len(f) != 6 or not valid_id(f[0]) or f[3] not in ("h", "t"):
            continue
        saved, size = _number(f[1]), _number(f[2])
        if saved is None or size is None or saved <= 0 or f[0] in seen:
            continue
        seen.add(f[0])
        pages.append([f[0], saved, size, f[3] == "t", unescape_field(f[4]), unescape_field(f[5])])
    out = []
    for p in pages:
        pm, fin = progress.get(p[0], (-1, 0))
        out.append(Page(p[0], p[1], p[2], p[3], p[4], p[5], pm, fin, None))
    return out


def read_label(page):
    """Omni's label: "Finished", "40% read", or "" (unknown / under 1 %)."""
    if page.finished_at:
        return "Finished"
    if page.permille < 10:
        return ""
    return "%d%% read" % (page.permille // 10)


def site(url):
    """The host of an http(s) address ("" otherwise), without "www."."""
    try:
        p = urllib.parse.urlsplit(url or "")
        host = (p.hostname or "") if p.scheme in ("http", "https") else ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _live_url(url):
    """The address when it's a plain http(s) link (safe to put in an href), else None."""
    if not isinstance(url, str) or len(url) > 8192:
        return None
    u = url.strip()
    if not re.match(r"https?://[^\s]", u, re.I) or any(ord(c) < 0x21 or ord(c) == 0x7f for c in u):
        return None
    return u


# -- file names on the PC -----------------------------------------------------------------------------------------------
_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {"com%d" % i for i in range(10)} | \
            {"lpt%d" % i for i in range(10)}


def local_name(page_id):
    """The file name a page gets on the PC, or None when the id isn't one Omni could have made."""
    if not valid_id(page_id):
        return None
    if page_id.split(".", 1)[0] in _RESERVED:
        return "_" + page_id
    return page_id


def _inside(root, path):
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    return os.path.commonpath([root, path]) == root and path != root


def default_folder(home=None):
    return os.path.join(home or os.path.expanduser("~"), "Documents", "Omnibloom Reading List")


def export_dir(folder, today=None):
    """<folder>/Omni reading list <date>, with " 2", " 3"... when taken."""
    day = (today or datetime.date.today()).strftime("%Y-%m-%d")
    base = os.path.join(folder, "Omni reading list %s" % day)
    path, n = base, 2
    while os.path.exists(path) or os.path.exists(path + ".part"):
        path = "%s %d" % (base, n)
        n += 1
    return path


# -- reading the console (read-only) ----------------------------------------------------------------------------------------
def _read(console, path, limit):
    try:
        return console.read(path, limit=limit + 1)
    except TypeError:
        return console.read(path)


def plan(console):
    """What an export would copy: {"pages": [Page with size], "missing", "too_big", "total", "warn", "no_index"}.
    One listing and one read of index.tsv; pages keep the index's order. Pages over 32 MB, past 200 or past
    MAX_TOTAL together are left out (too_big); index lines without a file are counted as missing."""
    listing = console.listing(DIR) or {}
    entry = listing.get("index.tsv")
    if entry is None or entry.get("dir"):
        return {"pages": [], "missing": 0, "too_big": 0, "total": 0, "warn": False, "no_index": True}
    if entry.get("size", 0) > INDEX_MAX:
        raise ExportError("The reading list's index on the PS5 is bigger than Omni writes. Nothing was copied.")
    data = _read(console, INDEX, INDEX_MAX)
    if len(data) > INDEX_MAX:
        raise ExportError("The reading list's index on the PS5 is bigger than Omni writes. Nothing was copied.")
    pages, missing, too_big, total = [], 0, 0, 0
    for p in parse_index(data):
        e = listing.get(p.id)
        if e is None or e.get("dir"):
            missing += 1
            continue
        size = e.get("size", -1)
        if size > PAGE_MAX or len(pages) >= MAX_COUNT or total + max(size, 0) > MAX_TOTAL:
            too_big += 1
            continue
        total += max(size, 0)
        pages.append(p._replace(size=size))
    return {"pages": pages, "missing": missing, "too_big": too_big, "total": total, "warn": total > WARN_BYTES,
            "no_index": False}


# -- index.html ---------------------------------------------------------------------------------------------------------------
def _date(ts, tz=None):
    try:
        return datetime.datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


def _esc(s):
    return html.escape(_clean_text(s), quote=True)


def _clean_text(s):
    """Text without control characters (XML 1.0 and HTML both refuse most of them)."""
    if not isinstance(s, str):
        return ""
    return "".join(c if (c in "\t\n" or 0x20 <= ord(c) < 0xd800 or 0xe000 <= ord(c) <= 0xfffd
                         or 0x10000 <= ord(c) <= 0x10ffff) and not 0x7f <= ord(c) < 0xa0 else " " for c in s)


INDEX_CSS = ("body{font:15px/1.45 system-ui,Segoe UI,sans-serif;margin:24px auto;max-width:960px;padding:0 16px;"
             "color:#1a1a1a;background:#fafafa}h1{font-size:22px}table{border-collapse:collapse;width:100%}"
             "th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top}"
             "th{font-size:13px;color:#555}.muted{color:#666;font-size:13px}a{color:#0a58ca}"
             "@media (prefers-color-scheme:dark){body{background:#151515;color:#e6e6e6}th{color:#aaa}"
             "td,th{border-color:#333}a{color:#7ab0ff}.muted{color:#999}}")


def index_html(rows, epub_name=None, tz=None, now=None):
    """The listing page. rows: [(Page, local file name)]. No scripts; everything from the index is escaped."""
    when = (now or datetime.datetime.now(tz)).strftime("%Y-%m-%d %H:%M")
    out = ["<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; "
           "img-src data:; frame-src 'none'; form-action 'none'\">\n",
           "<meta name=\"referrer\" content=\"no-referrer\">\n<meta name=\"viewport\" content=\"width=device-width\">\n",
           "<title>Omni reading list</title>\n<style>%s</style>\n</head>\n<body>\n" % INDEX_CSS,
           "<h1>Omni reading list</h1>\n<p class=\"muted\">%d page%s copied from the PS5 on %s. The copies are the pages "
           "as Omni saved them: images or styles from other sites need the internet.</p>\n"
           % (len(rows), "" if len(rows) == 1 else "s", html.escape(when))]
    if epub_name:
        out.append("<p><a href=\"%s\">E-book of the selected articles (EPUB)</a></p>\n"
                   % html.escape(urllib.parse.quote(epub_name), quote=True))
    out.append("<table>\n<thead><tr><th>Title</th><th>Site</th><th>Saved</th><th>Read</th><th></th></tr></thead>\n"
               "<tbody>\n")
    for page, name in rows:
        title = page.title.strip() or site(page.url) or page.id
        href = "pages/" + urllib.parse.quote(name)
        live = _live_url(page.url)
        live_link = ("<a href=\"%s\" rel=\"noopener noreferrer\">live page</a>" % html.escape(live, quote=True)
                     if live else "")
        out.append("<tr><td><a href=\"%s\">%s</a>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>\n" % (
            html.escape(href, quote=True), _esc(title), " <span class=\"muted\">(text only)</span>" if page.text_only else "",
            _esc(site(page.url)), html.escape(_date(page.saved_at, tz)), html.escape(read_label(page)), live_link))
    out.append("</tbody>\n</table>\n</body>\n</html>\n")
    return "".join(out)


# -- EPUB: sanitising a saved page into XHTML ---------------------------------------------------------------------------------
KEEP = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "a", "em", "strong", "b", "i", "u", "s", "sub", "sup", "small", "mark",
        "q", "cite", "abbr", "code", "kbd", "samp", "var", "pre", "blockquote", "ul", "ol", "li", "dl", "dt", "dd",
        "br", "hr", "img", "figure", "figcaption", "table", "caption", "thead", "tbody", "tfoot", "tr", "td", "th",
        "div", "span", "section", "article", "header", "footer", "aside", "main", "time", "del", "ins"}
VOID = {"br", "hr", "img"}
# Dropped with everything inside them.
DROP = {"script", "style", "iframe", "frame", "frameset", "object", "embed", "applet", "noembed", "noframes",
        "template", "svg", "math", "canvas", "video", "audio", "source", "track", "picture", "map", "head", "title",
        "select", "textarea", "button", "option", "optgroup", "datalist", "output", "dialog", "nav", "portal"}
# Dropped, children kept (unknown tags are treated the same way; void ones vanish).
_VOID_HTML = {"area", "base", "col", "embed", "input", "keygen", "link", "meta", "param", "source", "track", "wbr",
              "img", "br", "hr"}
_CELL = ({"td", "th"}, {"tr", "table"})
_IMPLIED = {"td": _CELL, "th": _CELL, "tr": ({"tr"}, {"table", "thead", "tbody", "tfoot"}),
            "li": ({"li"}, {"ul", "ol"}), "dt": ({"dt", "dd"}, {"dl"}), "dd": ({"dt", "dd"}, {"dl"}),
            "p": ({"p"}, {"div", "td", "th", "li", "blockquote", "section", "article", "figure", "table"})}
DATA_IMAGE = re.compile(r"data:image/(png|jpeg|jpg|gif|webp);base64,([A-Za-z0-9+/=\s]+)\Z", re.I)
_MAGIC = {"png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff", "gif": b"GIF8", "webp": b"RIFF"}
_EXT = {"png": "png", "jpeg": "jpg", "gif": "gif", "webp": "webp"}
_MEDIA = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def decode_data_image(src):
    """(kind, bytes) for an inlined data: image whose bytes really are that kind, else None."""
    if not isinstance(src, str) or len(src) > EPUB_IMAGE_MAX * 4 // 3 + 64:
        return None
    m = DATA_IMAGE.match(src.strip())
    if not m:
        return None
    kind = "jpeg" if m.group(1).lower() in ("jpg", "jpeg") else m.group(1).lower()
    try:
        data = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data or len(data) > EPUB_IMAGE_MAX or not data.startswith(_MAGIC[kind]):
        return None
    if kind == "webp" and data[8:12] != b"WEBP":
        return None
    return kind, data


def _safe_href(href):
    if not isinstance(href, str):
        return None
    h = href.strip()
    if re.match(r"(https?://|mailto:)[^\s]", h, re.I) and not any(ord(c) < 0x21 or ord(c) == 0x7f for c in h):
        return h
    return None


class _Sanitiser(html.parser.HTMLParser):
    """Rebuilds untrusted HTML as well-formed XHTML from the KEEP allow-list. Images: data: URIs only, via add_image."""

    def __init__(self, add_image):
        super().__init__(convert_charrefs=True)
        self.add_image = add_image
        self.out = []
        self.stack = []          # open KEEP elements
        self.drop = []           # open DROP elements (nothing is written while non-empty)
        self.in_body = False
        self.saw_body = False
        self.banner = 0          # depth inside Omni's "Saved copy" banner (dropped)
        self.text_chars = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "body":
            self.saw_body = self.in_body = True
            return
        if self.drop:
            if tag in DROP:
                self.drop.append(tag)
            return
        if tag in DROP:
            self.drop.append(tag)
            return
        a = {k.lower(): (v or "") for k, v in attrs if k}
        if self.banner:
            if tag not in _VOID_HTML:
                self.banner += 1
            return
        if a.get("id") == "omni-saved-banner":
            self.banner = 1
            return
        if tag not in KEEP:
            return
        keep = []
        if tag == "a":
            h = _safe_href(a.get("href"))
            if h:
                keep.append(("href", h))
        elif tag == "img":
            img = decode_data_image(a.get("src"))
            if not img:
                return
            name = self.add_image(*img)
            if not name:
                return
            keep.append(("src", name))
            keep.append(("alt", a.get("alt", "")))
        elif tag in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if a.get(k, "").isdigit() and 0 < int(a[k]) < 1000:
                    keep.append((k, str(int(a[k]))))
        if a.get("title") and tag != "img":
            keep.append(("title", a["title"]))
        attr = "".join(' %s="%s"' % (k, html.escape(_clean_text(v), quote=True)) for k, v in keep)
        self._implied_close(tag)
        if tag in VOID:
            self.out.append("<%s%s/>" % (tag, attr))
        else:
            self.out.append("<%s%s>" % (tag, attr))
            self.stack.append(tag)

    def _implied_close(self, tag):
        """HTML's optional end tags: a new <td> ends the open cell, <tr> the row, <li> the item, <p> the paragraph."""
        rule = _IMPLIED.get(tag)
        if not rule:
            return
        closes, bounds = rule
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] in bounds:
                return
            if self.stack[i] in closes:
                while len(self.stack) > i:
                    self.out.append("</%s>" % self.stack.pop())
                return

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        tag = tag.lower()
        if tag not in VOID and tag not in _VOID_HTML:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "body":
            self.in_body = False
            return
        if self.drop:
            if tag in DROP:
                # close up to the matching DROP element
                if tag in self.drop:
                    while self.drop and self.drop.pop() != tag:
                        pass
            return
        if self.banner:
            if tag not in _VOID_HTML:
                self.banner -= 1
            return
        if tag in VOID or tag not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            self.out.append("</%s>" % t)
            if t == tag:
                break

    def handle_data(self, data):
        if self.drop or self.banner or (self.saw_body and not self.in_body):
            return
        t = _clean_text(data)
        self.text_chars += len(t.strip())
        self.out.append(html.escape(t, quote=False))

    def result(self):
        self.close()
        while self.stack:
            self.out.append("</%s>" % self.stack.pop())
        return "".join(self.out)


XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
EPUB_CSS = ("body{font-family:serif;line-height:1.5;margin:0 4%}h1.title{font-size:1.4em;margin:0.6em 0 0.2em}"
            "p.source{font-size:0.85em;color:#555;margin:0 0 1.2em}img{max-width:100%;height:auto}"
            "pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{border:1px solid #999;padding:0.2em}")


def sanitise_page(raw, add_image):
    """(xhtml body fragment, visible text characters) of a saved page's bytes."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    s = _Sanitiser(add_image)
    s.feed(text)
    body = s.result()
    return body, s.text_chars


def _xhtml(title, body, lang="en", extra_ns=""):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="%s"%s xml:lang="%s" lang="%s">\n<head>\n<meta charset="utf-8"/>\n<title>%s</title>\n'
            '<link rel="stylesheet" type="text/css" href="style.css"/>\n</head>\n<body>\n%s\n</body>\n</html>\n'
            % (XHTML_NS, extra_ns, lang, lang, html.escape(_clean_text(title), quote=False), body))


def build_epub(dest, articles, title="Omni reading list", now=None, tz=None):
    """Write an EPUB 3 to `dest` (via dest.part). articles: [(Page, raw bytes)].
    Returns {"path", "chapters", "images", "skipped_images", "bytes"}."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    modified = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    book_id = "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, "omni-reading-list:" + modified + ":" +
                                         ",".join(p.id for p, _ in articles))
    images, chapters = [], []
    budget = [0]
    skipped = [0]

    def add_image(kind, data):
        if budget[0] + len(data) > EPUB_MAX:
            skipped[0] += 1
            return None
        budget[0] += len(data)
        name = "images/img-%04d.%s" % (len(images) + 1, _EXT[kind])
        images.append((name, _MEDIA[kind], data))
        return name

    for i, (page, raw) in enumerate(articles):
        body, _chars = sanitise_page(raw, add_image)
        head_title = page.title.strip() or site(page.url) or "Untitled page"
        src = " · ".join(x for x in (site(page.url), _date(page.saved_at, tz)) if x)
        live = _live_url(page.url)
        src_html = html.escape(src, quote=False)
        if live:
            src_html = '<a href="%s">%s</a>' % (html.escape(live, quote=True), src_html or "Live page")
        doc = _xhtml(head_title, '<h1 class="title">%s</h1>\n<p class="source">%s</p>\n<div class="content">%s</div>'
                     % (html.escape(_clean_text(head_title), quote=False), src_html, body))
        budget[0] += len(doc.encode("utf-8"))
        if budget[0] > EPUB_MAX:
            raise ExportError("The selected articles are too big for one e-book. Select fewer.")
        chapters.append(("text/ch-%03d.xhtml" % (i + 1), head_title, doc))

    nav_items = "\n".join('<li><a href="%s">%s</a></li>' % (posixpath.basename(href), html.escape(_clean_text(t), quote=False))
                          for href, t, _ in chapters)
    nav = _xhtml(title, '<nav epub:type="toc" id="toc"><h1>%s</h1>\n<ol>\n%s\n</ol></nav>'
                 % (html.escape(title, quote=False), nav_items), extra_ns=' xmlns:epub="%s"' % EPUB_NS)
    manifest = ['<item id="nav" href="text/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="css" href="text/style.css" media-type="text/css"/>']
    spine = []
    for i, (href, _t, _d) in enumerate(chapters):
        manifest.append('<item id="ch%03d" href="%s" media-type="application/xhtml+xml"/>' % (i + 1, href))
        spine.append('<itemref idref="ch%03d"/>' % (i + 1))
    for i, (name, media, _d) in enumerate(images):
        manifest.append('<item id="img%04d" href="text/%s" media-type="%s"/>' % (i + 1, name, media))
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en">\n'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           '<dc:identifier id="bookid">%s</dc:identifier>\n<dc:title>%s</dc:title>\n<dc:language>en</dc:language>\n'
           '<dc:creator>Omni reading list</dc:creator>\n<meta property="dcterms:modified">%s</meta>\n</metadata>\n'
           '<manifest>\n%s\n</manifest>\n<spine>\n%s\n</spine>\n</package>\n'
           % (book_id, html.escape(title, quote=False), modified, "\n".join(manifest), "\n".join(spine)))
    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                 '<rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles>\n</container>\n')
    part = dest + ".part"
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            mt = zipfile.ZipInfo("mimetype", date_time=(1980, 1, 1, 0, 0, 0))
            mt.compress_type = zipfile.ZIP_STORED
            z.writestr(mt, b"application/epub+zip")
            z.writestr("META-INF/container.xml", container)
            z.writestr("OEBPS/package.opf", opf)
            z.writestr("OEBPS/text/nav.xhtml", nav)
            z.writestr("OEBPS/text/style.css", EPUB_CSS)
            for href, _t, doc in chapters:
                z.writestr("OEBPS/" + href, doc)
            for name, _m, data in images:
                z.writestr("OEBPS/text/" + name, data, compress_type=zipfile.ZIP_STORED)
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return {"path": dest, "chapters": len(chapters), "images": len(images), "skipped_images": skipped[0],
            "bytes": os.path.getsize(dest)}


# -- the export -------------------------------------------------------------------------------------------------------------
def export(console, folder, epub_ids=None, plan_result=None, log=lambda m: None, progress=None, today=None, tz=None,
           now=None):
    """Copy the reading list into a new folder under `folder`. epub_ids: ids to put in an EPUB too (None/empty: no
    EPUB). Returns {"path", "pages", "bytes", "missing", "too_big", "epub": {...} or None}."""
    p = plan_result or plan(console)
    if p.get("no_index"):
        raise ExportError("Omni's reading list is empty on this PS5 (no saved pages yet).")
    pages = p["pages"]
    if not pages:
        raise ExportError("None of the reading list's pages could be found on the PS5.")
    os.makedirs(folder, exist_ok=True)
    dest = export_dir(folder, today)
    part = dest + ".part"
    os.makedirs(os.path.join(part, "pages"))
    wanted = set(epub_ids or ())
    rows, articles, total, missing, too_big = [], [], 0, p["missing"], p["too_big"]
    try:
        for i, page in enumerate(pages):
            name = local_name(page.id)
            target = os.path.join(part, "pages", name) if name else None
            if not name or not _inside(os.path.join(part, "pages"), target):
                missing += 1
                continue
            data = _read(console, DIR + "/" + page.id, PAGE_MAX)
            if len(data) > PAGE_MAX or total + len(data) > MAX_TOTAL:
                too_big += 1
                continue
            total += len(data)
            with open(target, "wb") as f:
                f.write(data)
            rows.append((page, name))
            if page.id in wanted:
                articles.append((page, data))
            if progress:
                progress(i + 1, len(pages))
        epub = None
        epub_name = None
        if articles:
            epub_name = "reading-list.epub"
            epub = build_epub(os.path.join(part, epub_name), articles, now=now, tz=tz)
        with open(os.path.join(part, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(index_html(rows, epub_name, tz=tz, now=now))
        os.rename(part, dest)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    log("Reading list export: %d page(s), %d KB%s%s." % (len(rows), (total + 1023) // 1024,
        "; e-book with %d article(s)" % epub["chapters"] if epub else "",
        "; %d missing, %d too big" % (missing, too_big) if missing or too_big else ""))
    return {"path": dest, "pages": len(rows), "bytes": total, "missing": missing, "too_big": too_big,
            "epub": dict(epub, path=os.path.join(dest, epub_name)) if epub else None}
