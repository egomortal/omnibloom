"""Remove personal details from log text before it leaves the PC in a diagnostics bundle.

Pure: no files, no network, no console. One Redactor per bundle: its host names are replaced by a short hash that
is the same everywhere in that bundle (so "the same site failed twice" still shows) but is salted per bundle, so a
hash can't be looked up by hashing well-known site names.

Rules (RULES below is the text written into the bundle's manifest):
  passwords/tokens in key=value form  -> key=<secret>
  web addresses                       -> scheme://<host-xxxxxx>/…   (user:password@, port, path, query and fragment
                                         are dropped; only "is there more after the host" survives as "/…").
                                         Local Omnibloom pages (localhost, 127.x) keep host, port and path, lose
                                         the query.
  e-mail addresses                    -> <email>
  home folders (C:\\Users\\<name>, /home/<name>, /Users/<name>, the PS5's /user/home/<id>) -> <home>
  the user's names (PC account name, any name Setup was given) -> <user>
  MAC addresses                       -> <mac>
  IPv4 and IPv6 addresses             -> <ip>   (127.x and ::1 stay)
  long hex / base64 runs (24+ chars)  -> <secret>
  video and playlist ids (v=, list=)  -> v=<removed>
  bare site names (news.example.org)  -> <host-xxxxxx>
"""
import hashlib
import math
import os
import re

RULES = (
    "Passwords, tokens, keys, cookies and session values written as name=value become name=<secret>.",
    "Web addresses become scheme://<host-xxxxxx>/… : the site name is replaced by a short hash (salted for this "
    "bundle only), and any user name, password, port, path, query and fragment are removed. Local Omnibloom pages "
    "(localhost, 127.x) keep their port and path but lose the query.",
    "E-mail addresses become <email>.",
    "Home folders (C:\\Users\\<name>, /home/<name>, /Users/<name>, /user/home/<id>) become <home>.",
    "The PC's account name and any user name Setup knows become <user>.",
    "MAC (hardware) addresses become <mac>.",
    "IPv4 and IPv6 addresses become <ip> (127.x and ::1 stay).",
    "Long runs of hex or base64 (24 characters or more) become <secret>.",
    "Video and playlist ids (v=, vid=, list=...) become <removed>.",
    "Site names outside web addresses become <host-xxxxxx>, the same hash as above.",
)

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")

_SECRET_KV = re.compile(
    r"(?i)\b(access[_-]?token|refresh[_-]?token|id[_-]?token|api[_-]?key|apikey|client[_-]?secret|token|key|secret|"
    r"password|passwd|pwd|pass|cookie|set-cookie|authorization|auth|session|sessionid|sid|signature|sig|bearer)"
    r"(\s*[=:]\s*|\"\s*:\s*\")(?=\S)(?!<)([^\s\",;&<>]+)")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]*)?")
_BEARER = re.compile(r"(?i)\b(Bearer|Basic)(\s+)(?!<)([A-Za-z0-9._~+/=-]{8,})")
_URL = re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]{1,15})://([^\s\"'<>()\]\[{}|\\^`]*(?:\[[0-9a-fA-F:.]+\][^\s\"'<>()\]{}|\\^`]*)?)")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
_HOME_WIN = re.compile(r"(?i)\b[A-Z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\\/\r\n\t\"'|?*:]+")
_HOME_UNIX = re.compile(r"(?<![\w.-])/(?:home|Users)/[^/\s\"'<>]+")
_HOME_PS5 = re.compile(r"(?<![\w.-])/user/home/[0-9a-fA-F]+")
_MAC = re.compile(r"(?<![0-9A-Fa-f:-])(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}(?![0-9A-Fa-f:-])")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.]*\d)")
# An IPv6 address (also shortened with "::") has a hex letter or at least 3 colons; log times ("12:34:56") stay.
_IPV6 = re.compile(r"(?<![\w:])(?:(?=[0-9a-fA-F:]*[a-fA-F])|(?=(?:[0-9a-fA-F]{0,4}:){3}))"
                   r"[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}(?:%\w+)?(?![\w:])")
_RUN = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/=_-]{24,}(?![A-Za-z0-9+/=_-])")
_HEX = re.compile(r"[0-9a-fA-F]{24,}")
_MEDIA_ID = re.compile(r"\b(vid|videoId|video_id|v|list|playlist)=([A-Za-z0-9_-]{6,})")
_HOST = re.compile(r"(?<![\w@<-])(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+([a-zA-Z]{2,24})\b(?![\w-])")

# Endings that are file names, not sites (boot.log, hub.elf, app.js).
_FILE_EXT = {"log", "txt", "json", "elf", "prx", "bin", "js", "css", "html", "htm", "png", "jpg", "webp", "svg", "ttf",
             "otf", "woff", "woff2", "flag", "cpp", "h", "inc", "py", "zip", "mp4", "webm", "conf", "pem", "so", "sprx",
             "self", "tmp", "dat", "db", "ini", "md", "xml", "plist", "cfg", "new", "off", "bak", "lock", "map", "sh",
             "class", "jar", "pid", "tsv", "part", "sqlite"}
# Real web endings: every two-letter country code, plus the common generic ones.
_TLDS = {"com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "io", "app", "dev", "tv", "gg", "me", "co", "ai",
         "xyz", "online", "site", "store", "shop", "blog", "news", "live", "video", "page", "cloud", "tech", "top", "club",
         "art", "design", "media", "social", "games", "game", "chat", "link", "world", "today", "space", "studio", "wiki",
         "fun", "pro", "mobi", "name", "asia", "travel", "jobs", "tel", "eu", "lol", "porn", "sex", "xxx", "adult", "cam",
         "local", "lan", "home", "internal", "onion"}


_COMMON_NAMES = {"omni", "omnibloom", "bloom", "admin", "administrator", "user", "users", "root", "data", "test", "home",
                 "guest", "default", "public", "system", "owner", "player", "ps5", "hub", "core", "setup", "native"}


def pc_user_names():
    """The PC account names worth hiding (the current user, from the environment)."""
    names = set()
    for var in ("USERNAME", "USER", "LOGNAME"):
        v = os.environ.get(var)
        if v:
            names.add(v)
    home = os.path.basename(os.path.expanduser("~").rstrip("\\/"))
    if home:
        names.add(home)
    return sorted(names)


def _looks_secret(run):
    """A 24+ character run of hex/base64 characters that is random-looking (a key or token, not a word or a path)."""
    if _HEX.fullmatch(run):
        return True
    if "/" in run:       # a path: judge each part on its own
        return False
    if len(run) < 24:
        return False
    kinds = [("u" if c.isupper() else "l" if c.islower() else "d" if c.isdigit() else "o") for c in run]
    if not ("d" in kinds and ("u" in kinds or "l" in kinds)) and not ("u" in kinds and "l" in kinds):
        return False
    changes = sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
    counts = {}
    for c in run:
        counts[c] = counts.get(c, 0) + 1
    entropy = -sum(n / len(run) * math.log2(n / len(run)) for n in counts.values())
    return changes >= 0.3 * len(run) and entropy >= 3.5


class Redactor:
    def __init__(self, salt=None, user_names=()):
        self.salt = salt if salt is not None else os.urandom(8)
        if isinstance(self.salt, str):
            self.salt = self.salt.encode()
        # Names that are also everyday log words would wipe the log, so they're not replaced.
        self.users = sorted({u for u in user_names if u and len(u) >= 3 and u.lower() not in _COMMON_NAMES},
                            key=len, reverse=True)
        self._users = (re.compile(r"(?i)(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(re.escape(u) for u in self.users))
                       if self.users else None)
        self.counts = {}

    # -- helpers -----------------------------------------------------------------------------------------------
    def host_tag(self, host):
        h = hashlib.sha256(self.salt + host.lower().strip(".").encode("utf-8", "replace")).hexdigest()[:6]
        return "<host-%s>" % h

    def _count(self, what, n=1):
        if n:
            self.counts[what] = self.counts.get(what, 0) + n

    def _sub(self, pattern, repl, text, what):
        out, n = pattern.subn(repl, text)
        self._count(what, n)
        return out

    def _url(self, m):
        scheme, rest = m.group(1), m.group(2)
        if not rest:
            return m.group(0)
        cut = re.search(r"[/?#]", rest)
        authority, tail = (rest[:cut.start()], rest[cut.start():]) if cut else (rest, "")
        if "@" in authority:                      # user:password@host
            authority = authority.rsplit("@", 1)[1]
            self._count("user names and passwords in web addresses")
        if authority.startswith("["):
            host = authority[1:authority.find("]")] if "]" in authority else authority[1:]
        else:
            host = authority.rsplit(":", 1)[0] if authority.count(":") == 1 else authority
        hl = host.lower()
        if hl in LOCAL_HOSTS or hl.startswith("127."):
            return scheme + "://" + authority + re.split(r"[?#]", tail, maxsplit=1)[0]
        self._count("web addresses")
        if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", host) or ":" in host:
            shown = "<ip>"
        else:
            shown = self.host_tag(host) if host else "<host>"
        more = tail.strip("/") != "" or tail.startswith(("?", "#"))
        return scheme + "://" + shown + ("/…" if more else "")

    def _ip4(self, m):
        text = m.group(0)
        parts = text.split(".")
        if parts[0] == "127" or any(int(p) > 255 for p in parts):
            return text      # loopback, or a version number
        self._count("IP addresses")
        return "<ip>"

    def _ip6(self, m):
        text = m.group(0)
        if text == "::1" or text.count(":") < 2:
            return text
        self._count("IP addresses")
        return "<ip>"

    def _run(self, m):
        run = m.group(0)
        if "/" in run:
            parts = run.split("/")
            if not any(_looks_secret(p) for p in parts):
                return run
            n = sum(1 for p in parts if _looks_secret(p))
            self._count("tokens and keys", n)
            return "/".join("<secret>" if _looks_secret(p) else p for p in parts)
        if _looks_secret(run):
            self._count("tokens and keys")
            return "<secret>"
        return run

    def _host(self, m):
        tld = m.group(1).lower()
        name = m.group(0)
        if tld in _FILE_EXT or name.lower() in LOCAL_HOSTS:
            return name
        if not (tld in _TLDS or len(tld) == 2):
            return name
        self._count("site names")
        return self.host_tag(name)

    # -- the whole pass ----------------------------------------------------------------------------------------
    def redact(self, text):
        """Return the text with personal details replaced (counts accumulate in self.counts)."""
        text = _URL.sub(self._url, text)
        text = self._sub(_JWT, "<secret>", text, "tokens and keys")
        text = self._sub(_BEARER, lambda m: m.group(1) + m.group(2) + "<secret>", text, "passwords, tokens and keys")
        text = self._sub(_SECRET_KV, lambda m: m.group(1) + m.group(2) + "<secret>", text, "passwords, tokens and keys")
        text = self._sub(_EMAIL, "<email>", text, "e-mail addresses")
        if self._users:
            text = self._sub(self._users, "<user>", text, "user names")
        text = self._sub(_HOME_WIN, "<home>", text, "home folders")
        text = self._sub(_HOME_UNIX, "<home>", text, "home folders")
        text = self._sub(_HOME_PS5, "<home>", text, "home folders")
        text = self._sub(_MAC, "<mac>", text, "hardware addresses")
        text = _IPV6.sub(self._ip6, text)
        text = _IPV4.sub(self._ip4, text)
        text = _RUN.sub(self._run, text)
        text = self._sub(_MEDIA_ID, lambda m: m.group(1) + "=<removed>", text, "video and playlist IDs")
        text = _HOST.sub(self._host, text)
        return text


def redact(text, salt=b"", user_names=()):
    """One-off redaction: (clean text, counts)."""
    r = Redactor(salt=salt, user_names=user_names)
    return r.redact(text), r.counts
