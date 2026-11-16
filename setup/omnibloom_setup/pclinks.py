"""Send a web link from this PC to Omni on the PS5 ("Send a link to Omni" page; OMNI_PC_LINKS_V1 on the console).

Two ways, both ending in Omni asking on the TV "Link from your PC: <site>" with Open / Dismiss (it never opens on its own):

1. The inbox (default; needs only the console's FTP server, which Setup already uses). Setup uploads one small file
       /data/omni/inbox/links-<YYYYmmdd-HHMMSS>-<6 hex>.txt
   holding the line "omni-pc-links\\t1" and then one link per line (at most 20). It goes through the usual verified
   upload (`<name>.omnibloom-new`, read back, renamed into place), so Omni never sees half a file; the name is new every
   time, so nothing on the console is overwritten, appended to or deleted by Setup. Omni looks at the folder every
   5 seconds while it is on screen (one stat of the folder; it reads only when the folder changed), takes the files
   (deleting each one it has read) and asks about each link in turn. In guest mode Omni leaves the files alone until
   the owner is back; parental controls block a link before it is ever offered.
   At most 20 waiting files: Setup refuses to add more until Omni has taken some ("Is Omni open on the PS5?").
2. Send links from your phone (OMNI_SEND_LINK_V1, off by default in Omni's Browser settings): with the 6-digit code
   shown there, Setup posts the link straight to http://<console>:8770/send and Omni opens it in a new tab at once.

Every link is checked here exactly as Omni checks it (OmniPcLinks.h / OmniSendLink.h validUrl): http or https only,
at most 2048 bytes, no user name or password, no spaces, control characters or backslashes, a plain host name or IP
literal and a port from 1 to 65535. "example.com/page" gets "https://" in front (like the phone page).
Logs and errors name counts only, never a link.
"""
import datetime
import json
import os
import posixpath
import re
import urllib.error
import urllib.request

INBOX = "/data/omni/inbox"
HEADER = "omni-pc-links\t1"
MAX_LINKS = 20          # per file, and Omni's waiting list
MAX_FILES = 20          # waiting files in the inbox before Setup says "Omni hasn't taken them"
MAX_URL = 2048          # bytes (UTF-8)
SEND_LINK_PORT = 8770
NAME_RE = re.compile(r"links-[0-9]{8}-[0-9]{6}-[0-9a-f]{6}\.txt\Z")   # Omni takes only these names


class SendError(Exception):
    """A send that didn't happen; the message is for the user."""


# -- the link check (mirrors OmniSendLink::validUrl + OmniPcLinks::validUrl) ----------------------------------------------
_HOST_OK = re.compile(r"[A-Za-z0-9._-]+\Z")


def _bad_char(ch):
    cp = ord(ch)
    return (cp <= 0x20 or 0x7F <= cp <= 0x9F or ch == "\\" or cp in (0x2028, 0x2029, 0xFEFF)
            or 0xD800 <= cp <= 0xDFFF)


def valid_url(text):
    """The link as Omni will take it (scheme in lower case, white space trimmed), or None."""
    if not isinstance(text, str):
        return None
    u = text.strip(" \t\r\n")
    if not u:
        return None
    try:
        size = len(u.encode("utf-8"))
    except UnicodeEncodeError:   # a lone surrogate
        return None
    if size > MAX_URL or any(_bad_char(c) for c in u):
        return None
    low = u[:8].lower()
    if low.startswith("http://"):
        scheme, rest = "http://", u[7:]
    elif low.startswith("https://"):
        scheme, rest = "https://", u[8:]
    else:
        return None
    end = len(rest)
    for sep in "/?#":
        i = rest.find(sep)
        if i >= 0:
            end = min(end, i)
    auth = rest[:end]
    if not auth or "@" in auth:
        return None
    port = None
    if auth.startswith("["):
        close = auth.find("]")
        if close < 3 or any(c not in "0123456789abcdefABCDEF:." for c in auth[1:close]):
            return None
        tail = auth[close + 1:]
        if tail:
            if not tail.startswith(":") or len(tail) == 1:
                return None
            port = tail[1:]
    else:
        if auth.count(":") > 1:
            return None
        host, _, p = auth.partition(":")
        if not host:
            return None
        if ":" in auth:
            if not p:
                return None
            port = p
        if not all(ord(c) >= 0x80 or _HOST_OK.match(c) for c in host):
            return None
    if port is not None:
        if len(port) > 5 or not port.isdigit() or not port.isascii() or not 1 <= int(port) <= 65535:
            return None
    return scheme + rest


def _with_scheme(word):
    """"example.com/x" -> "https://example.com/x"; anything with a scheme (or that isn't a host) unchanged."""
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]*://", word) or re.match(r"(?i)(javascript|data|file|about|mailto):", word):
        return word
    if re.match(r"(localhost|\[[0-9A-Fa-f:.]+\]|[^\s/?#:@]+\.[^\s/?#:@]+)(:[0-9]+)?([/?#]|\Z)", word):
        return "https://" + word
    return word


def _from_shortcut(text):
    """The URL= line of a Windows Internet shortcut (.url file) dropped on the window, else None."""
    if "[InternetShortcut]" not in text:
        return None
    for line in text.splitlines():
        if line.strip().lower().startswith("url="):
            return line.strip()[4:].strip()
    return None


def parse_input(text):
    """What was pasted or dropped -> (links, rejected count). One link per line or separated by spaces; repeats are
    kept once; more than MAX_LINKS are refused as a whole (SendError) rather than cut silently."""
    text = (text or "").replace("\x00", "")
    shortcut = _from_shortcut(text)
    words = [shortcut] if shortcut is not None else text.split()
    links, bad, seen = [], 0, set()
    for w in words:
        w = w.strip().strip("<>\"'")
        if not w:
            continue
        u = valid_url(_with_scheme(w))
        if u is None:
            bad += 1
        elif u not in seen:
            seen.add(u)
            links.append(u)
    if len(links) > MAX_LINKS:
        raise SendError("That is %d links: Omni takes up to %d at a time." % (len(links), MAX_LINKS))
    return links, bad


def site(url):
    """The host shown on the TV ("www.example.com"), for this page's preview."""
    u = valid_url(url)
    if not u:
        return ""
    rest = u.split("://", 1)[1]
    for sep in "/?#":
        rest = rest.split(sep, 1)[0]
    if rest.startswith("["):
        return rest[: rest.find("]") + 1]
    return rest.split(":", 1)[0].lower()


# -- the inbox file -------------------------------------------------------------------------------------------------------
def file_text(links):
    """The file Omni reads (OmniPcLinks::parse): the header line and one link per line, LF endings."""
    if not links:
        raise SendError("There is no link to send.")
    if len(links) > MAX_LINKS:
        raise SendError("Omni takes up to %d links at a time." % MAX_LINKS)
    for u in links:
        if valid_url(u) != u:
            raise SendError("One of the links can't be sent (only http:// and https:// links, without a user name or "
                            "password, up to %d characters)." % MAX_URL)
    return HEADER + "\n" + "".join(u + "\n" for u in links)


def file_name(now=None, rand=None):
    now = now or datetime.datetime.now()
    token = rand if rand is not None else os.urandom(3).hex()
    name = "links-%s-%s.txt" % (now.strftime("%Y%m%d-%H%M%S"), token)
    if not NAME_RE.match(name):
        raise ValueError("bad inbox name")
    return name


def waiting(console):
    """Link files Omni hasn't taken yet (names only)."""
    return sorted(n for n, e in console.listing(INBOX).items() if not e["dir"] and NAME_RE.match(n))


def send_inbox(console, links, now=None, rand=None, log=lambda m: None):
    """Put `links` in Omni's inbox over FTP. Returns {"path", "links", "waiting"}; raises SendError."""
    data = file_text(links).encode("utf-8")
    entries = console.listing(INBOX)
    if entries:
        pending = [n for n, e in entries.items() if not e["dir"] and NAME_RE.match(n)]
        if len(pending) >= MAX_FILES:
            raise SendError("%d earlier sends are still waiting on the PS5. Open Omni there (it takes them while it is on "
                            "screen), then try again." % len(pending))
    else:
        console.makedirs(INBOX)
        entries = {}
    name = file_name(now, rand)
    while name in entries:   # same second and same random bytes: pick again
        name = file_name(now, None)
    path = posixpath.join(INBOX, name)
    temp = console.put_verified(path, data)
    console.rename(temp, path)
    log("Sent %d link%s to Omni's inbox." % (len(links), "" if len(links) == 1 else "s"))
    return {"path": path, "links": len(links), "waiting": len(waiting(console))}


# -- Send links from your phone (OMNI_SEND_LINK_V1), when the user gives the code ----------------------------------------
def clean_code(code):
    digits = re.sub(r"[\s-]", "", code or "")
    return digits if re.fullmatch(r"[0-9]{6}", digits) else None


def send_direct(host, links, code, port=SEND_LINK_PORT, timeout=5.0, opener=None, log=lambda m: None):
    """POST each link to Omni's send-link server (it opens each in a new tab). Returns the number sent; raises SendError
    with Omni's own message (wrong code, locked for a minute, busy) or a plain "didn't answer"."""
    c = clean_code(code)
    if not c:
        raise SendError("The code is the 6 digits shown in Omni: Browser settings, Send links from your phone.")
    if not links:
        raise SendError("There is no link to send.")
    for u in links:
        if valid_url(u) != u:
            raise SendError("One of the links can't be sent.")
    open_ = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    url = "http://%s:%d/send" % (host, port)
    sent = 0
    for u in links:
        req = urllib.request.Request(url, data=json.dumps({"url": u, "code": c}).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with open_(req, timeout=timeout) as r:
                r.read(4096)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read(4096).decode("utf-8", "replace")).get("message")
            except (ValueError, AttributeError, OSError):
                msg = None
            raise SendError((msg or "Omni refused the link (HTTP %d)." % e.code)
                            + ("" if not sent else " %d of %d were sent." % (sent, len(links))))
        except (urllib.error.URLError, OSError) as e:
            raise SendError("Omni didn't answer on port %d. Is \"Send links from your phone\" on in Omni's Browser "
                            "settings, and is Omni open? (%s)" % (port, getattr(e, "reason", e)))
        sent += 1
    log("Sent %d link%s to Omni directly." % (sent, "" if sent == 1 else "s"))
    return sent
