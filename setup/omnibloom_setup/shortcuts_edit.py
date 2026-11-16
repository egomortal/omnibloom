"""Edit Omni's search shortcuts (/data/omni/search-shortcuts.txt) and Quick access row (/data/omni/quick-access.txt).

Both files are read and written exactly as Omni does (OMNI_SEARCH_TILES_V1 / OMNI_SITE_SEARCH_V1 and OMNI_QA_CUSTOM_V1):

search-shortcuts.txt  one "keyword<TAB>https://...%s[<TAB>Name]" per line ("keyword template" with a space is read too),
    '#' comments and blank lines skipped, a UTF-8 BOM skipped, the first valid line of a keyword wins, at most 30
    entries, the file read up to 64 KB. Keyword: 1-16 of a-z 0-9 ! - _ (lower-cased first). Template: https:// only, a
    plain host (letters, digits, '.', '-', optional :port, at least one dot), no credentials, a path / query after the
    host, at least one %s there, every other '%' a %XX escape, at most 1024 bytes of printable ASCII without space,
    quotes, <>, backslash, backtick, {}|^. Name: optional, at most 40 bytes (Omni shows the template's host when empty).
    A missing file means Omni's built-ins (yt, w, r, g, d, a, m); an empty file means no shortcuts.

quick-access.txt  one button key per line, in order, at most 6 (Omni reads lines with a 64-byte fgets buffer and
    trims trailing CR / LF / spaces; unknown keys and repeats are skipped). A missing file means the default row
    (uBlock, Dark mode, Apps, Add-ons); an empty file means an empty row.

Writes to the PS5 use the verified upload of every other Setup write (temp file, sha256 readback, then moved into
place); the old file is parked beside it as <name>.prev (.prev-2, ... when that name is taken), never deleted. A local
file is written the same way: the old copy is kept as <file>.prev.

Shortcuts can hold personal sites: this module logs counts only, never a keyword, address or name.
"""
import os
import posixpath
from collections import namedtuple

SEARCH_PATH = "/data/omni/search-shortcuts.txt"
QUICK_PATH = "/data/omni/quick-access.txt"
PREV_SUFFIX = ".prev"

# OmniSearchTiles.h
MAX_ENGINES = 30
MAX_PREFIX = 16
MAX_TEMPLATE = 1024
MAX_NAME = 40
MAX_FILE = 64 * 1024

# OmniMqQuickAccess.h (OMNI_QA_CUSTOM_V1)
QUICK_MAX = 6
QUICK_LINE_BUFFER = 64
QUICK_KEYS = ("ublock", "dark", "apps", "addons", "media", "copy", "paste", "quickbar", "bookmarks", "tabs", "history",
              "translate", "reader", "find", "newtab", "reload", "settings")
QUICK_NAMES = ("uBlock", "Dark mode", "Apps", "Add-ons", "Media downloads", "Copy", "Paste", "Quick bar", "Bookmarks",
               "Tabs", "History", "Translate", "Reader view", "Find in page", "New tab", "Reload", "Settings")
QUICK_NAME = dict(zip(QUICK_KEYS, QUICK_NAMES))
QUICK_DEFAULTS = ("ublock", "dark", "apps", "addons")

Engine = namedtuple("Engine", "prefix template name")

BUILTINS = (
    Engine("yt", "https://www.youtube.com/results?search_query=%s", "YouTube"),
    Engine("w", "https://en.wikipedia.org/w/index.php?search=%s", "Wikipedia"),
    Engine("r", "https://www.reddit.com/search/?q=%s", "Reddit"),
    Engine("g", "https://www.google.com/search?q=%s", "Google"),
    Engine("d", "https://duckduckgo.com/?q=%s", "DuckDuckGo"),
    Engine("a", "https://www.amazon.com/s?k=%s", "Amazon"),
    Engine("m", "https://www.google.com/maps/search/?api=1&query=%s", "Google Maps"),
)
HEADER = "# Omni search shortcuts: keyword<TAB>https://...%s<TAB>Name (type \"keyword words\" in the address bar)"

_TRIM = " \t\r\n"
_BAD_TEMPLATE_CHARS = "\"'<>\\`{}|^"
_HEX = "0123456789abcdefABCDEF"


class EditError(Exception):
    """A list Omni would not take as it is (the message says which row and why)."""


# -- search shortcuts: Omni's rules ---------------------------------------------------------------------------------
def _ascii_lower(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def valid_prefix(p):
    """OmniSearchTiles::validPrefix: 1-16 of a-z 0-9 ! - _ (the caller lower-cases first)."""
    if not isinstance(p, str) or not p or len(p) > MAX_PREFIX:
        return False
    return all("a" <= c <= "z" or "0" <= c <= "9" or c in "!-_" for c in p)


def valid_template(t):
    """OmniSearchTiles::validTemplate, rule for rule."""
    if not isinstance(t, str) or len(t) > MAX_TEMPLATE or _ascii_lower(t[:8]) != "https://":
        return False
    for c in t:
        if ord(c) <= 0x20 or ord(c) >= 0x7F or c in _BAD_TEMPLATE_CHARS:
            return False
    hs = 8
    he = min([i for i in (t.find("/", hs), t.find("?", hs), t.find("#", hs)) if i >= 0], default=-1)
    auth = t[hs:] if he < 0 else t[hs:he]
    host, port = auth, ""
    colon = auth.find(":")
    if colon >= 0:
        host, port = auth[:colon], auth[colon + 1:]
        if not port or len(port) > 5:
            return False
    if any(not ("0" <= c <= "9") for c in port):
        return False
    if not host or "." not in host or host[0] == "." or host[-1] == "." or host[0] == "-":
        return False
    for c in _ascii_lower(host):
        if not ("a" <= c <= "z" or "0" <= c <= "9" or c in ".-"):
            return False
    if he < 0:
        return False
    query = False
    i, n = he, len(t)
    while i < n:
        if t[i] == "%":
            if i + 1 < n and t[i + 1] == "s":
                query = True
                i += 1
            elif i + 2 < n and t[i + 1] in _HEX and t[i + 2] in _HEX:
                i += 2
            else:
                return False
        i += 1
    return query


def host_of(url):
    """OmniSearchTiles::hostOf: lower-case host of an http(s) address, no credentials / port / trailing dot / www."""
    low = _ascii_lower(url[:8])
    if low.startswith("https://"):
        s = 8
    elif low.startswith("http://"):
        s = 7
    else:
        return ""
    ends = [i for i in (url.find("/", s), url.find("?", s), url.find("#", s)) if i >= 0]
    a = _ascii_lower(url[s:min(ends)] if ends else url[s:])
    if "@" in a:
        a = a[a.rfind("@") + 1:]
    if a.startswith("["):
        b = a.find("]")
        a = "" if b < 0 else a[:b + 1]
    elif ":" in a:
        a = a[:a.find(":")]
    a = a.rstrip(".")
    if a.startswith("www.") and "." in a[4:]:
        a = a[4:]
    return a


def clean_name(name):
    """OmniSiteSearch::cleanName (what Omni writes): valid UTF-8 only, no C1 / line separators, runs of spaces and
    control characters become one space (none at the ends), at most 40 bytes, never a cut character."""
    out, space, size = [], False, 0
    for ch in name if isinstance(name, str) else "":
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF or cp in (0x2028, 0x2029) or 0x80 <= cp < 0xA0:
            continue
        if cp < 0x20 or cp == 0x7F or ch == " ":
            space = bool(out)
            continue
        n = len(ch.encode("utf-8"))
        if size + (1 if space else 0) + n > MAX_NAME:
            break
        if space:
            out.append(" ")
            size += 1
            space = False
        out.append(ch)
        size += n
    return "".join(out)


def display_name(e):
    """The name Omni shows: the entry's own, else a built-in's with the same host, else the host."""
    if e.name:
        return e.name
    h = host_of(e.template)
    for b in BUILTINS:
        if host_of(b.template) == h:
            return b.name
    return h


def _lines(text):
    if text.startswith("﻿"):
        text = text[1:]
    return text.split("\n") if text else []


def parse_search(data):
    """search-shortcuts.txt bytes (or text) -> (engines, rejected), as OmniSearchTiles::parseFile reads it. Names are
    kept as written (control characters made spaces, cut to 40 bytes); an empty name stays empty."""
    if isinstance(data, bytes):
        data = data[:MAX_FILE].decode("utf-8", "replace")
    out, bad = [], 0
    for raw in _lines(data):
        line = raw.strip(_TRIM)
        if not line or line[0] == "#":
            continue
        name = ""
        t1 = line.find("\t")
        if t1 >= 0:
            prefix = line[:t1]
            t2 = line.find("\t", t1 + 1)
            tmpl = (line[t1 + 1:] if t2 < 0 else line[t1 + 1:t2]).strip(_TRIM)
            if t2 >= 0:
                name = line[t2 + 1:].strip(_TRIM)
        else:
            sp = line.find(" ")
            if sp < 0:
                bad += 1
                continue
            prefix, tmpl = line[:sp], line[sp + 1:].strip(_TRIM)
        prefix = _ascii_lower(prefix.strip(_TRIM))
        if not valid_prefix(prefix) or not valid_template(tmpl) or len(out) >= MAX_ENGINES:
            bad += 1
            continue
        if any(x.prefix == prefix for x in out):
            bad += 1
            continue
        name = "".join(" " if ord(c) < 0x20 else c for c in name)
        b = name.encode("utf-8", "replace")
        if len(b) > MAX_NAME:
            name = b[:MAX_NAME].decode("utf-8", "ignore")
        out.append(Engine(prefix, tmpl, name))
    return out, bad


def normalize(e):
    """An entry as the editor saves it: keyword trimmed and lower-cased, template trimmed, name cleaned."""
    return Engine(_ascii_lower(str(e.prefix).strip(_TRIM)), str(e.template).strip(_TRIM), clean_name(e.name or ""))


def search_problems(engines):
    """[(row, message)] for every entry Omni would skip, plus the count cap; [] when Omni takes the whole list."""
    problems, seen = [], {}
    for i, e in enumerate(engines):
        e = normalize(e)
        if not valid_prefix(e.prefix):
            problems.append((i, "Keyword: use 1-16 letters, digits, - _ or !"))
        elif e.prefix in seen:
            problems.append((i, "Keyword “%s” is already used in row %d" % (e.prefix, seen[e.prefix] + 1)))
        else:
            seen[e.prefix] = i
        if len(e.template) > MAX_TEMPLATE:
            problems.append((i, "Address: longer than %d characters" % MAX_TEMPLATE))
        elif not e.template.lower().startswith("https://"):
            problems.append((i, "Address: must start with https:// (Omni takes no http:// shortcuts)"))
        elif "%s" not in e.template:
            problems.append((i, "Address: put %s where the search words go"))
        elif not valid_template(e.template):
            problems.append((i, "Address: a plain host with a dot, then a path or query holding %s; no spaces, "
                                "quotes, <>, {}|^ or a lone %"))
    if len(engines) > MAX_ENGINES:
        problems.append((MAX_ENGINES, "Omni keeps %d shortcuts; remove %d" % (MAX_ENGINES, len(engines) - MAX_ENGINES)))
    return problems


def serialize_search(engines, newline="\n"):
    """search-shortcuts.txt bytes for `engines` (the header comment, then one TAB line each, as Omni writes them).
    Raises EditError when Omni would not take every entry or the file would pass 64 KB."""
    problems = search_problems(engines)
    if problems:
        row, why = problems[0]
        raise EditError("Row %d: %s." % (row + 1, why))
    lines = [HEADER]
    for e in map(normalize, engines):
        lines.append(e.prefix + "\t" + e.template + ("\t" + e.name if e.name else ""))
    data = newline.join(lines).encode("utf-8") + newline.encode()
    if len(data) > MAX_FILE:
        raise EditError("The list is over %d KB; Omni reads only the first %d KB." % (MAX_FILE // 1024, MAX_FILE // 1024))
    return data


def newline_of(data):
    """The file's line ending (CRLF when its first line ends so), kept on save like Omni's own editor."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    n = data.find("\n")
    return "\r\n" if n > 0 and data[n - 1] == "\r" else "\n"


# -- quick access ---------------------------------------------------------------------------------------------------
def parse_quick(data):
    """quick-access.txt bytes -> (keys, skipped), as omniQaLoad reads it: fgets with a 64-byte buffer, trailing CR / LF
    / spaces trimmed, a line kept only when it is exactly a known key not seen yet, reading stops at 6 buttons."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    keys, skipped, pos = [], 0, 0
    while pos < len(data) and len(keys) < QUICK_MAX:
        chunk = data[pos:pos + QUICK_LINE_BUFFER - 1]
        nl = chunk.find(b"\n")
        if nl >= 0:
            chunk = chunk[:nl + 1]
        pos += len(chunk)
        s = chunk.split(b"\0", 1)[0].rstrip(b"\n\r ")
        try:
            key = s.decode("ascii")
        except UnicodeDecodeError:
            key = None
        if key in QUICK_KEYS and key not in keys:
            keys.append(key)
        elif s:
            skipped += 1
    return keys, skipped


def quick_problems(keys):
    problems, seen = [], set()
    for i, k in enumerate(keys):
        if k not in QUICK_KEYS:
            problems.append((i, "Unknown button %r" % (k,)))
        elif k in seen:
            problems.append((i, "%s is already in the row" % QUICK_NAME[k]))
        seen.add(k)
    if len(keys) > QUICK_MAX:
        problems.append((QUICK_MAX, "Omni shows up to %d buttons; remove %d" % (QUICK_MAX, len(keys) - QUICK_MAX)))
    return problems


def serialize_quick(keys):
    """quick-access.txt bytes as omniQaSave writes them ("key\\n" each). An empty list is an empty row."""
    problems = quick_problems(keys)
    if problems:
        row, why = problems[0]
        raise EditError("Button %d: %s." % (row + 1, why))
    return "".join(k + "\n" for k in keys).encode("ascii")


# -- loading and saving ---------------------------------------------------------------------------------------------
Loaded = namedtuple("Loaded", "items skipped exists newline")


def from_bytes(kind, data):
    """kind "search" / "quick"; data None = the file is missing (Omni's built-ins / default row)."""
    if kind == "search":
        if data is None:
            return Loaded(list(BUILTINS), 0, False, "\n")
        items, bad = parse_search(data)
        return Loaded(items, bad, True, newline_of(data))
    if kind == "quick":
        if data is None:
            return Loaded(list(QUICK_DEFAULTS), 0, False, "\n")
        items, bad = parse_quick(data)
        return Loaded(items, bad, True, "\n")
    raise ValueError(kind)


def to_bytes(kind, items, newline="\n"):
    return serialize_search(items, newline) if kind == "search" else serialize_quick(items)


def console_path(kind):
    return SEARCH_PATH if kind == "search" else QUICK_PATH


def load_console(console, kind):
    path = console_path(kind)
    return from_bytes(kind, console.read(path) if console.exists(path) else None)


def load_local(path, kind):
    with open(path, "rb") as f:
        return from_bytes(kind, f.read(MAX_FILE + 1))


def save_console(console, kind, data, log=lambda m: None):
    """Verified upload, the old file parked as <name>.prev (or .prev-N), then moved into place. Returns the parked
    path, or None when there was no old file / it already held these bytes."""
    from . import installer   # here, so this module loads without the installer's imports
    path = console_path(kind)
    old = console.read(path) if console.exists(path) else None
    if old == data:
        log("%s: already up to date." % posixpath.basename(path))
        return None
    console.makedirs(posixpath.dirname(path))
    temp = console.put_verified(path, data)
    parked = None
    if old is not None:
        parked = installer._free_name(console, path, PREV_SUFFIX)
        console.rename(path, parked)
    console.rename(temp, path)
    if console.read(path) != data:
        raise IOError("Couldn't write %s; the earlier file was kept beside it." % posixpath.basename(path))
    log("%s: %d entries written." % (posixpath.basename(path), len(from_bytes(kind, data).items)))
    return parked


def save_local(path, data):
    """Write a local copy; an existing file is kept as <file>.prev first. Returns the .prev path or None."""
    prev = None
    if os.path.exists(path):
        prev = path + PREV_SUFFIX
        with open(path, "rb") as src, open(prev, "wb") as dst:
            dst.write(src.read())
    tmp = path + ".omnibloom-new"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return prev


# -- Tk editor ------------------------------------------------------------------------------------------------------
def open_editor(root, connect=None, run_bg=None, title="Search shortcuts and Quick access"):
    """A window with two tabs. connect(): a context-managed ps5.Console (None = offline, local files only);
    run_bg(fn, done(result, err)): the app's background runner (None = run inline)."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    run = run_bg or (lambda fn, done: _inline(fn, done))
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("860x520")
    status = tk.StringVar(value="")
    book = ttk.Notebook(win)
    book.pack(fill="both", expand=True, padx=8, pady=8)
    ttk.Label(win, textvariable=status, wraplength=820).pack(fill="x", padx=10, pady=(0, 8))
    state = {"search": None, "quick": None}

    # search tab
    sf = ttk.Frame(book, padding=8)
    book.add(sf, text="Search shortcuts")
    tree = ttk.Treeview(sf, columns=("prefix", "template", "name"), show="headings", height=12, selectmode="browse")
    for col, head, width in (("prefix", "Keyword", 110), ("template", "Address (%s = search words)", 500),
                             ("name", "Name", 170)):
        tree.heading(col, text=head)
        tree.column(col, width=width, anchor="w")
    tree.pack(fill="both", expand=True)
    form = ttk.Frame(sf)
    form.pack(fill="x", pady=6)
    v_pre, v_tpl, v_name = tk.StringVar(), tk.StringVar(), tk.StringVar()
    for i, (lab, var, w) in enumerate((("Keyword", v_pre, 12), ("Address", v_tpl, 60), ("Name", v_name, 20))):
        ttk.Label(form, text=lab).grid(row=0, column=2 * i, padx=(0 if i == 0 else 8, 4))
        ttk.Entry(form, textvariable=var, width=w).grid(row=0, column=2 * i + 1)

    def s_items():
        out = []   # Tk turns "42" into 42 and may drop an empty last cell: back to three strings
        for r in tree.get_children():
            vals = [str(v) for v in tree.item(r, "values")] + ["", "", ""]
            out.append(Engine(*vals[:3]))
        return out

    def s_fill(items, select=None):
        tree.delete(*tree.get_children())
        for e in items:
            tree.insert("", "end", values=(e.prefix, e.template, e.name))
        rows = tree.get_children()
        if select is not None and rows:
            tree.selection_set(rows[max(0, min(select, len(rows) - 1))])
        s_count()

    def s_count():
        status.set("%d of %d search shortcuts." % (len(tree.get_children()), MAX_ENGINES))

    def s_sel():
        sel = tree.selection()
        return tree.index(sel[0]) if sel else None

    def on_select(_e=None):
        i = s_sel()
        if i is not None:
            e = s_items()[i]
            v_pre.set(e.prefix), v_tpl.set(e.template), v_name.set(e.name)
    tree.bind("<<TreeviewSelect>>", on_select)

    def s_form_entry(items, replace=None):
        e = normalize(Engine(v_pre.get(), v_tpl.get(), v_name.get()))
        trial = list(items)
        if replace is None:
            trial.append(e)
        else:
            trial[replace] = e
        row = len(trial) - 1 if replace is None else replace
        mine = [why for r, why in search_problems(trial) if r == row]
        if mine:
            messagebox.showerror(title, mine[0] + ".", parent=win)
            return None
        return trial, row

    def s_add():
        got = s_form_entry(s_items())
        if got:
            s_fill(*got)

    def s_update():
        i = s_sel()
        if i is None:
            return
        got = s_form_entry(s_items(), i)
        if got:
            s_fill(*got)

    def s_remove():
        i = s_sel()
        if i is not None:
            items = s_items()
            del items[i]
            s_fill(items, i)

    def s_move(d):
        i = s_sel()
        items = s_items()
        if i is None or not 0 <= i + d < len(items):
            return
        items[i], items[i + d] = items[i + d], items[i]
        s_fill(items, i + d)

    btns = ttk.Frame(sf)
    btns.pack(fill="x")
    for text, cmd in (("Add", s_add), ("Update selected", s_update), ("Remove", s_remove),
                      ("Move up", lambda: s_move(-1)), ("Move down", lambda: s_move(1)),
                      ("Omni's built-ins", lambda: s_fill(list(BUILTINS)))):
        ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 6))

    # quick access tab
    qf = ttk.Frame(book, padding=8)
    book.add(qf, text="Quick access row")
    ttk.Label(qf, text="The buttons in Omni's top bar, left to right (up to %d). An empty row is allowed." % QUICK_MAX
              ).pack(anchor="w")
    qrow = ttk.Frame(qf)
    qrow.pack(fill="both", expand=True, pady=6)
    chosen = tk.Listbox(qrow, height=8, exportselection=False)
    chosen.pack(side="left", fill="both", expand=True)
    q_keys = []
    side = ttk.Frame(qrow, padding=(8, 0))
    side.pack(side="left", fill="y")
    pick = ttk.Combobox(side, state="readonly", values=list(QUICK_NAMES), width=20)
    pick.pack(anchor="w", pady=(0, 6))

    def q_fill(keys, select=None):
        q_keys[:] = keys
        chosen.delete(0, "end")
        for k in keys:
            chosen.insert("end", QUICK_NAME.get(k, k))
        if select is not None and keys:
            chosen.selection_set(max(0, min(select, len(keys) - 1)))

    def q_sel():
        s = chosen.curselection()
        return s[0] if s else None

    def q_add():
        if pick.current() < 0:
            return
        trial = q_keys + [QUICK_KEYS[pick.current()]]
        bad = quick_problems(trial)
        if bad:
            messagebox.showerror(title, bad[0][1] + ".", parent=win)
            return
        q_fill(trial, len(trial) - 1)

    def q_remove():
        i = q_sel()
        if i is not None:
            keys = list(q_keys)
            del keys[i]
            q_fill(keys, i)

    def q_move(d):
        i = q_sel()
        if i is None or not 0 <= i + d < len(q_keys):
            return
        keys = list(q_keys)
        keys[i], keys[i + d] = keys[i + d], keys[i]
        q_fill(keys, i + d)

    for text, cmd in (("Add", q_add), ("Remove", q_remove), ("Move up", lambda: q_move(-1)),
                      ("Move down", lambda: q_move(1)), ("Omni's default", lambda: q_fill(list(QUICK_DEFAULTS)))):
        ttk.Button(side, text=text, command=cmd, width=16).pack(anchor="w", pady=2)

    # source / destination
    def current_kind():
        return "search" if book.index("current") == 0 else "quick"

    def show(kind, loaded, where):
        state[kind] = loaded
        (s_fill if kind == "search" else q_fill)(list(loaded.items))
        note = "%s from %s." % ("Search shortcuts" if kind == "search" else "Quick access row", where)
        if not loaded.exists:
            note += " The file isn't there yet, so Omni uses its %s." % ("built-ins" if kind == "search" else "default row")
        if loaded.skipped:
            note += " %d line(s) Omni skips were left out; saving drops them (the old file is kept as .prev)." % loaded.skipped
        status.set(note)

    def from_ps5():
        def work():
            with connect() as c:
                return load_console(c, "search"), load_console(c, "quick")

        def done(r, err):
            if err:
                status.set("Couldn't read the PS5: %s" % err)
                return
            show("quick", r[1], "the PS5")
            show("search", r[0], "the PS5")
        status.set("Reading both files from the PS5…")
        run(work, done)

    def from_file():
        kind = current_kind()
        path = filedialog.askopenfilename(parent=win, filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if path:
            try:
                show(kind, load_local(path, kind), "the file")
            except OSError as e:
                messagebox.showerror(title, "Couldn't read the file: %s" % e, parent=win)

    def data_for(kind):
        if kind == "search":
            nl = state["search"].newline if state["search"] else "\n"
            return serialize_search(s_items(), nl)
        return serialize_quick(list(q_keys))

    def to_file():
        kind = current_kind()
        try:
            data = data_for(kind)
        except EditError as e:
            messagebox.showerror(title, str(e), parent=win)
            return
        path = filedialog.asksaveasfilename(parent=win, defaultextension=".txt",
                                            initialfile=posixpath.basename(console_path(kind)))
        if path:
            prev = save_local(path, data)
            status.set("Saved." + (" The old copy is kept as .prev." if prev else ""))

    def to_ps5():
        kind = current_kind()
        try:
            data = data_for(kind)
        except EditError as e:
            messagebox.showerror(title, str(e), parent=win)
            return
        name = posixpath.basename(console_path(kind))
        if not messagebox.askokcancel(title, "Upload %s to the PS5?\n\nThe current file is kept beside it as %s%s. "
                                             "Omni picks up search shortcuts at once; restart Omni for the Quick "
                                             "access row." % (name, name, PREV_SUFFIX), parent=win):
            return

        def work():
            with connect() as c:
                return save_console(c, kind, data)

        def done(parked, err):
            if err:
                status.set("Couldn't upload: %s" % err)
            else:
                status.set("Uploaded %s and checked it." % name
                           + (" The old file is kept as %s." % posixpath.basename(parked) if parked else ""))
        status.set("Uploading…")
        run(work, done)

    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=8, pady=(0, 8))
    ps5_state = "normal" if connect else "disabled"
    ttk.Button(bar, text="Load from PS5", command=from_ps5, state=ps5_state).pack(side="left")
    ttk.Button(bar, text="Open file…", command=from_file).pack(side="left", padx=6)
    ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
    ttk.Button(bar, text="Upload this tab to PS5", command=to_ps5, state=ps5_state).pack(side="right", padx=6)
    ttk.Button(bar, text="Save this tab to file…", command=to_file).pack(side="right")

    show("search", from_bytes("search", None), "Omni's built-ins")
    show("quick", from_bytes("quick", None), "Omni's default")
    if connect:
        from_ps5()
    return win


def _inline(fn, done):
    try:
        r = fn()
    except Exception as e:  # shown to the user
        done(None, e)
    else:
        done(r, None)
