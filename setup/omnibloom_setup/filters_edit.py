"""Edit Omni's "My filters" list (/data/omni/ublock-user-filters.txt): your own uBlock Origin rules and the element
zapper's "Hide this element" rules (S10).

The file is read exactly as Omni reads it (OMNI_ZAPPER_V1, OmniZapper.h):
    the first 256 KB (a longer file is cut at its last whole line), split on "\\n" with one trailing "\\r" dropped, at
    most 3000 lines, blank lines at the end dropped. No BOM handling (a BOM makes the first line unusable).
    A line is applied only when it is "host##selector" or "h1,h2##selector": every host lower-case letters, digits,
    '.' and '-' (no empty label, at most 253 characters; ASCII upper case is lower-cased; IDN as punycode), the
    selector plain CSS (at most 280 bytes; no { } ; < \\ or control characters, no /* */, no leading @ > + ~ , or
    space, balanced () [] and quotes, no uBlock procedural operator). It hides the matches on the host and every
    subdomain. Everything else (comments "!" / "[", network filters, generic "##x", "#@#" / "#?#" / "#$#", "~host",
    "host.*", "##+js(...)", "##^...", procedural selectors) is kept in the file untouched and not applied yet.
    The zapper refuses a 101st rule for one host and stops adding when the file holds 2998 lines; this editor does too.

Omni loads the file once when it starts and rewrites the whole file (from what it loaded) when you hide an element,
so changes need Omni closed while uploading, or restarted right after.

The editor keeps every line it does not touch byte for byte (line endings included): loading and saving an unchanged
file gives the same bytes. Uploads use the verified upload of every other Setup write; the old file is parked beside
it as <name>.prev (.prev-2, ... when taken), never deleted. A local file keeps its old copy as <file>.prev.

Rules name the sites you visit: this module logs counts only, never a host or selector.
"""
import posixpath
from collections import OrderedDict, namedtuple

from . import shortcuts_edit

FILTERS_PATH = "/data/omni/ublock-user-filters.txt"
PREV_SUFFIX = ".prev"

# OmniZapper.h
MAX_FILE = 256 * 1024
MAX_LINES = 3000
MAX_PER_HOST = 100
MAX_SELECTOR = 280
HOST_MAX = 253
HEADER = "! Omni: my filters (uBlock Origin syntax). The element zapper adds host##selector lines."

_PROCEDURAL = (":has-text(", ":style(", ":remove(", ":matches-css", ":upward(", ":xpath(", ":-abp-",
               ":min-text-length(", ":watch-attr(", ":others(", ":matches-path(", ":matches-attr(", ":matches-media(",
               ":remove-attr(", ":remove-class(", ":matches-prop(", ":if(", ":if-not(", ":nth-ancestor(", ":spath(",
               ":contains(")

OTHER = "Other lines"        # group of lines with no site (network filters, generic rules, ...)
COMMENTS = "Comments"
NOT_APPLIED = "not applied yet"


class EditError(Exception):
    """A change Omni would not take (the message says why)."""


# -- Omni's rules (OmniZapper.h, rule for rule) ------------------------------------------------------------------------
def _trim(s):
    return s.strip(" \t\r")


def _lower(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def _nbytes(s):
    return len(s.encode("utf-8", "surrogateescape"))


def valid_host(h):
    if not h or len(h) > HOST_MAX or h[0] == "." or h[-1] == "." or ".." in h:
        return False
    return all("a" <= c <= "z" or "0" <= c <= "9" or c in ".-" for c in h)


def procedural(s):
    return any(op in s for op in _PROCEDURAL)


def css_safe(s):
    if not s or _nbytes(s) > MAX_SELECTOR or "/*" in s or "*/" in s or s[0] in "@>+~, ":
        return False
    paren = bracket = 0
    quote = None
    for c in s:
        if ord(c) < 0x20 or ord(c) == 0x7F or c in "{};<\\":
            return False
        if quote:
            if c == quote:
                quote = None
            continue
        if c in "\"'":
            quote = c
        elif c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
            if paren < 0:
                return False
        elif c == "[":
            bracket += 1
        elif c == "]":
            bracket -= 1
            if bracket < 0:
                return False
    return not quote and not paren and not bracket and not procedural(s)


Parsed = namedtuple("Parsed", "kind hosts selector reason")   # kind: blank / comment / rule / ignored


def parse_line(raw):
    """OmniZapper::parseLine, plus why a line is not applied. hosts / selector are set only for kind "rule"."""
    s = _trim(raw)
    if not s:
        return Parsed("blank", (), "", "")
    if s[0] in "![":
        return Parsed("comment", (), "", "")
    sep = s.find("##")
    if sep < 0 or sep == 0 or "#@#" in s or "#?#" in s or "#$#" in s:
        if "#@#" in s:
            why = "an exception (#@#)"
        elif "#?#" in s or "#$#" in s:
            why = "an extended rule (#?# / #$#)"
        elif sep == 0:
            why = "a rule for every site"
        else:
            why = "a network filter"
        return Parsed("ignored", (), "", why)
    sel = s[sep + 2:]
    if not sel or sel[0] == "+":
        return Parsed("ignored", (), "", "a scriptlet" if sel else "no selector")
    if sel[0] == "^":
        return Parsed("ignored", (), "", "an HTML filter")
    if not css_safe(sel):
        if procedural(sel):
            why = "a procedural selector"
        elif _nbytes(sel) > MAX_SELECTOR:
            why = "a selector over %d characters" % MAX_SELECTOR
        else:
            why = "a selector Omni can't use safely"
        return Parsed("ignored", (), "", why)
    hosts = []
    for part in s[:sep].split(","):
        h = _lower(_trim(part))
        if not valid_host(h):
            return Parsed("ignored", (), "", "a site list Omni can't read (~, .*, regex or a typo)")
        hosts.append(h)
    return Parsed("rule", tuple(hosts), sel, "")


def site_hint(raw):
    """The plain hosts named before ## / #@# / #?# / #$# on a line Omni doesn't apply (to group it by site), or ()."""
    s = _trim(raw)
    cut = [i for i in (s.find("##"), s.find("#@#"), s.find("#?#"), s.find("#$#")) if i > 0]
    if not cut:
        return ()
    out = []
    for part in s[:min(cut)].split(","):
        h = _lower(_trim(part)).lstrip("~")
        if not valid_host(h):
            return ()
        if h not in out:
            out.append(h)
    return tuple(out)


def console_line_count(data):
    """How many of the file's lines Omni reads (OmniZapper::parse before dropping blank lines at the end)."""
    if len(data) > MAX_FILE:
        data = data[:MAX_FILE]
        nl = data.rfind(b"\n")
        data = data[:nl] if nl >= 0 else b""
    n, p = 0, 0
    while p < len(data) and n < MAX_LINES:
        e = data.find(b"\n", p)
        e = len(data) if e < 0 else e
        n += 1
        p = e + 1
    return n


# -- the file, line by line, every untouched line byte-exact ---------------------------------------------------------
class FilterFile:
    """lines: text without its ending; endings: what followed it ("\\n", "\\r\\n", "\\r" or "" on the last line)."""

    def __init__(self, data=b"", exists=True):
        if isinstance(data, str):
            data = data.encode("utf-8", "surrogateescape")
        self.exists = exists
        self.lines, self.endings = [], []
        text = data.decode("utf-8", "surrogateescape")
        parts = text.split("\n")
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if last and part == "":
                break
            end = "" if last else "\n"
            if part.endswith("\r"):
                part, end = part[:-1], "\r" + end
            self.lines.append(part)
            self.endings.append(end)
        self.newline = "\r\n" if self.endings and self.endings[0] == "\r\n" else "\n"
        self.seen = console_line_count(data)     # lines past this one Omni doesn't read

    def to_bytes(self):
        return "".join(l + e for l, e in zip(self.lines, self.endings)).encode("utf-8", "surrogateescape")

    # what Omni sees
    def rules(self):
        """[(host, selector)] Omni applies, in file order, without repeats (OmniZapper::rules)."""
        out, seen = [], set()
        for line in self.lines[:self.seen]:
            p = parse_line(line)
            for h in p.hosts:
                if (h, p.selector) not in seen:
                    seen.add((h, p.selector))
                    out.append((h, p.selector))
        return out

    def rows(self):
        """[Row] one per line (a rule line once per host), with what Omni does with it."""
        out = []
        for i, line in enumerate(self.lines):
            p = parse_line(line)
            if i >= self.seen and p.kind != "blank":
                site = (p.hosts or site_hint(line) or (OTHER,))[0]
                out.append(Row(i, site, "ignored", line, "",
                               "past Omni's limit of %d lines / %d KB" % (MAX_LINES, MAX_FILE // 1024)))
                continue
            if p.kind == "rule":
                out.extend(Row(i, h, "rule", line, p.selector, "") for h in p.hosts)
            elif p.kind == "comment":
                out.append(Row(i, COMMENTS, "comment", line, "", ""))
            elif p.kind == "ignored":
                hint = site_hint(line)
                out.extend(Row(i, h, "ignored", line, "", p.reason) for h in (hint or (OTHER,)))
        return out

    def groups(self):
        """OrderedDict site -> [Row]: sites in first-seen order, then OTHER, then COMMENTS."""
        g = OrderedDict()
        for r in self.rows():
            if r.site not in (OTHER, COMMENTS):
                g.setdefault(r.site, []).append(r)
        for tail in (OTHER, COMMENTS):
            rows = [r for r in self.rows() if r.site == tail]
            if rows:
                g[tail] = rows
        return g

    def counts(self):
        rows = self.rows()
        return {"rules": len(self.rules()), "sites": len({r.site for r in rows if r.kind == "rule"}),
                "not_applied": len({r.index for r in rows if r.kind == "ignored"}),
                "comments": sum(1 for r in rows if r.kind == "comment")}

    # changes
    def _append(self, text):
        if self.endings and self.endings[-1] == "":
            self.endings[-1] = self.newline
        self.lines.append(text)
        self.endings.append(self.newline)

    def _insert(self, index, text):
        if index >= len(self.lines):
            self._append(text)
        else:
            self.lines.insert(index, text)
            self.endings.insert(index, self.newline)

    def _host_count(self, host):
        return sum(1 for h, _ in self.rules() if h == host)

    def _sync(self):
        self.seen = console_line_count(self.to_bytes())

    def _check_rule(self, sites, selector):
        """The line "h1,h2##selector" when the zapper would add it (OmniZapper::add, for each host); raises EditError
        with the reason Omni would refuse it."""
        hosts = []
        for part in str(sites).split(","):
            h = _lower(_trim(part))
            if h.startswith("www.") and "." in h[4:]:
                h = h[4:]
            if h and h not in hosts:
                hosts.append(h)
        selector = _trim(str(selector))
        if not hosts:
            raise EditError("Type the site, like example.com.")
        for h in hosts:
            if not valid_host(h):
                raise EditError("“%s” isn't a plain site name (letters, digits, dots and dashes)." % h)
        if not css_safe(selector):
            raise EditError(selector_problem(selector))
        have = set(self.rules())
        if all((h, selector) in have for h in hosts):
            raise EditError("That rule is already in the list.")
        for h in hosts:
            if self._host_count(h) >= MAX_PER_HOST:
                raise EditError("%s already has %d rules, Omni's limit for one site." % (h, MAX_PER_HOST))
        if len(self.lines) + 2 > MAX_LINES:
            raise EditError("The list is full (%d lines)." % MAX_LINES)
        return ",".join(hosts) + "##" + selector

    def add_rule(self, sites, selector):
        """Append a checked rule line (the header comment first in an empty file). Returns the new line's index."""
        line = self._check_rule(sites, selector)
        if not self.lines:
            self._append(HEADER)
        self._append(line)
        self._sync()
        return len(self.lines) - 1

    def edit_rule(self, index, host, sites, selector):
        """Change the rule shown for `host` on line `index`: a one-host line is rewritten in place; on a shared line
        only this host moves to a new line just below. All or nothing. Returns the new line's index."""
        trial = FilterFile(self.to_bytes(), self.exists)
        alone = parse_line(self.lines[index]).hosts == (host,)
        ending = self.endings[index]
        trial.remove_host(index, host)
        line = trial._check_rule(sites, selector)
        at = index if alone else index + 1
        trial._insert(at, line)
        if alone and ending:
            trial.endings[at] = ending
        trial._sync()
        self.__dict__.update(trial.__dict__)
        return at

    def set_line(self, index, text):
        """Replace one line's text (its line ending stays)."""
        text = str(text)
        if "\n" in text or "\r" in text:
            raise EditError("One rule per line.")
        self.lines[index] = text
        self._sync()

    def delete_line(self, index):
        del self.lines[index]
        del self.endings[index]
        if self.lines == [HEADER]:
            self.lines, self.endings = [], []
        self._sync()

    def remove_host(self, index, host):
        """Take host off the rule line (OmniZapper::remove for one line): the line goes when no host is left."""
        p = parse_line(self.lines[index])
        if p.kind != "rule" or host not in p.hosts:
            raise EditError("That line is not a rule for %s." % host)
        rest = [h for h in p.hosts if h != host]
        if rest:
            self.set_line(index, ",".join(rest) + "##" + p.selector)
        else:
            self.delete_line(index)

    def delete_site(self, site):
        """Remove every rule for a site (shared lines keep their other hosts) and its not-applied lines. Returns count."""
        n = 0
        for i in sorted({r.index for r in self.groups().get(site, ())}, reverse=True):
            if parse_line(self.lines[i]).kind == "rule":
                self.remove_host(i, site)
            else:
                self.delete_line(i)
            n += 1
        return n

    def import_text(self, text):
        """Append the pasted lines (uBlock syntax; blank lines and lines already in the list are skipped). Stops at
        Omni's caps. Returns {"added", "applied", "not_applied", "same", "left_out"}."""
        r = {"added": 0, "applied": 0, "not_applied": 0, "same": 0, "left_out": 0}
        have = {_trim(l) for l in self.lines}
        for raw in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip()
            if not line:
                continue
            if line in have:
                r["same"] += 1
                continue
            before = (list(self.lines), list(self.endings))
            if not self.lines and parse_line(line).kind != "comment":
                self._append(HEADER)
            self._append(line)
            if len(self.lines) > MAX_LINES or len(self.to_bytes()) > MAX_FILE:
                self.lines, self.endings = before
                r["left_out"] += 1
                continue
            have.add(line)
            r["added"] += 1
            r["applied" if parse_line(line).kind == "rule" else "not_applied"] += 1
        self._sync()
        return r

    def problems(self):
        """Why Omni would not read the whole file: [] when it reads every line."""
        data = self.to_bytes()
        out = []
        if len(data) > MAX_FILE:
            out.append("The list is %d KB; Omni reads only the first %d KB." % (len(data) // 1024 + 1, MAX_FILE // 1024))
        if len(self.lines) > MAX_LINES:
            out.append("The list has %d lines; Omni reads only the first %d." % (len(self.lines), MAX_LINES))
        return out

    def serialize(self):
        """The bytes to save. Raises EditError when Omni would not read the whole file."""
        bad = self.problems()
        if bad:
            raise EditError(bad[0])
        return self.to_bytes()


Row = namedtuple("Row", "index site kind line selector reason")


def selector_problem(sel):
    """Plain words for why Omni won't use this selector ("" when it will)."""
    if not sel:
        return "Type the element to hide (a CSS selector, like .ad-banner or #promo)."
    if _nbytes(sel) > MAX_SELECTOR:
        return "The selector is over %d characters." % MAX_SELECTOR
    if procedural(sel):
        return "Omni doesn't apply uBlock's special operators (:has-text, :style, :upward, ...) yet."
    if sel[0] in "+^":
        return "Scriptlets (##+js) and HTML filters (##^) aren't applied by Omni yet."
    if not css_safe(sel):
        return ("Omni can't use that selector: no { } ; < \\ or comments, it can't start with @ > + ~ , or a space, "
                "and brackets and quotes must match.")
    return ""


# -- loading and saving ---------------------------------------------------------------------------------------------
def from_bytes(data):
    """data None = the file is missing (no filters yet)."""
    return FilterFile(b"", exists=False) if data is None else FilterFile(data)


def load_console(console):
    return from_bytes(console.read(FILTERS_PATH) if console.exists(FILTERS_PATH) else None)


def load_local(path):
    with open(path, "rb") as f:
        return from_bytes(f.read())


def save_console(console, data, log=lambda m: None):
    """Verified upload, the old file parked as <name>.prev (or .prev-N), then moved into place. Returns the parked
    path, or None when there was no old file / it already held these bytes."""
    from . import installer   # here, so this module loads without the installer's imports
    path = FILTERS_PATH
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
    log("%s: %d rules written." % (posixpath.basename(path), len(FilterFile(data).rules())))
    return parked


save_local = shortcuts_edit.save_local


# -- Tk editor ------------------------------------------------------------------------------------------------------
def open_editor(root, connect=None, run_bg=None, title="My filters"):
    """connect(): a context-managed ps5.Console (None = offline, local files only); run_bg(fn, done(result, err)): the
    app's background runner (None = run inline)."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    run = run_bg or (lambda fn, done: shortcuts_edit._inline(fn, done))
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("900x580")
    status = tk.StringVar(value="")
    st = {"file": from_bytes(None), "where": ""}

    ttk.Label(win, wraplength=860, text="Your own uBlock Origin rules, and the elements you hid with “Hide this "
              "element” in Omni. Omni applies site##selector lines (hide matching elements on that site and its "
              "subdomains); other lines are kept and marked “%s”." % NOT_APPLIED).pack(fill="x", padx=10, pady=(8, 0))
    tree = ttk.Treeview(win, columns=("what", "state"), show="tree headings", height=14, selectmode="browse")
    tree.heading("#0", text="Site")
    tree.heading("what", text="Rule")
    tree.heading("state", text="In Omni")
    tree.column("#0", width=220, anchor="w")
    tree.column("what", width=470, anchor="w")
    tree.column("state", width=170, anchor="w")
    tree.pack(fill="both", expand=True, padx=8, pady=8)
    rowmap = {}   # tree item -> Row (rule / line rows) or site name (group rows)

    form = ttk.Frame(win)
    form.pack(fill="x", padx=8)
    v_site, v_sel = tk.StringVar(), tk.StringVar()
    ttk.Label(form, text="Site").grid(row=0, column=0, padx=(0, 4))
    ttk.Entry(form, textvariable=v_site, width=28).grid(row=0, column=1)
    ttk.Label(form, text="Element (CSS selector)").grid(row=0, column=2, padx=(8, 4))
    ttk.Entry(form, textvariable=v_sel, width=52).grid(row=0, column=3)

    def fill(keep=None):
        f = st["file"]
        tree.delete(*tree.get_children())
        rowmap.clear()
        pick = None
        for site, rows in f.groups().items():
            n_rule = sum(1 for r in rows if r.kind == "rule")
            n_off = sum(1 for r in rows if r.kind == "ignored")
            label = site if site in (OTHER, COMMENTS) else "%s  (%d)" % (site, n_rule)
            g = tree.insert("", "end", text=label, open=True,
                            values=("", "%d %s" % (n_off, NOT_APPLIED) if n_off else ""))
            rowmap[g] = site
            for r in rows:
                state = {"rule": "hidden on this site", "comment": "comment"}.get(r.kind, NOT_APPLIED + ": " + r.reason)
                item = tree.insert(g, "end", text="", values=(r.selector or r.line, state))
                rowmap[item] = r
                if keep is not None and (r.index, r.site) == keep:
                    pick = item
        if pick:
            tree.selection_set(pick)
            tree.see(pick)
        c = f.counts()
        status.set("%s%d rules on %d sites applied; %d lines %s; %d comments." % (
            st["where"], c["rules"], c["sites"], c["not_applied"], NOT_APPLIED, c["comments"]))

    def selected():
        s = tree.selection()
        return rowmap.get(s[0]) if s else None

    def on_select(_e=None):
        r = selected()
        if isinstance(r, Row) and r.kind == "rule":
            v_site.set(r.site), v_sel.set(r.selector)
        elif isinstance(r, str) and r not in (OTHER, COMMENTS):
            v_site.set(r), v_sel.set("")
    tree.bind("<<TreeviewSelect>>", on_select)

    def guarded(fn):
        try:
            return fn()
        except EditError as e:
            messagebox.showerror(title, str(e), parent=win)
            return None

    def add():
        i = guarded(lambda: st["file"].add_rule(v_site.get(), v_sel.get()))
        if i is not None:
            p = parse_line(st["file"].lines[i])
            fill((i, p.hosts[0]))

    def update():
        r = selected()
        if not isinstance(r, Row):
            return
        f = st["file"]
        if r.kind == "rule":
            at = guarded(lambda: f.edit_rule(r.index, r.site, v_site.get(), v_sel.get()))
            if at is not None:
                fill((at, parse_line(f.lines[at]).hosts[0]))
            return
        text = simpledialog.askstring(title, "Edit the line (uBlock Origin syntax):", initialvalue=r.line, parent=win)
        if text is not None and guarded(lambda: f.set_line(r.index, text) or True):
            fill((r.index, r.site))

    def delete():
        r = selected()
        f = st["file"]
        if isinstance(r, Row):
            if r.kind == "rule":
                f.remove_host(r.index, r.site)
            else:
                f.delete_line(r.index)
            fill()
        elif isinstance(r, str):
            if messagebox.askokcancel(title, "Remove everything listed under %s?" % r, parent=win):
                if r in (OTHER, COMMENTS):
                    for i in sorted({x.index for x in f.groups().get(r, ())}, reverse=True):
                        f.delete_line(i)
                else:
                    f.delete_site(r)
                fill()

    def import_pasted():
        dlg = tk.Toplevel(win)
        dlg.title("Import rules")
        dlg.transient(win)
        ttk.Label(dlg, text="Paste uBlock Origin rules, one per line. Lines already in the list are skipped.").pack(
            anchor="w", padx=8, pady=(8, 4))
        box = tk.Text(dlg, width=90, height=16)
        box.pack(fill="both", expand=True, padx=8)

        def go():
            r = st["file"].import_text(box.get("1.0", "end"))
            dlg.destroy()
            fill()
            msg = "Added %d lines: %d applied by Omni, %d %s." % (r["added"], r["applied"], r["not_applied"], NOT_APPLIED)
            if r["same"]:
                msg += " %d were already there." % r["same"]
            if r["left_out"]:
                msg += " %d didn't fit (Omni reads %d lines / %d KB)." % (r["left_out"], MAX_LINES, MAX_FILE // 1024)
            status.set(msg)
        b = ttk.Frame(dlg)
        b.pack(fill="x", padx=8, pady=8)
        ttk.Button(b, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(b, text="Import", command=go).pack(side="right", padx=6)

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=8, pady=6)
    for text, cmd in (("Add rule", add), ("Update selected", update), ("Delete selected", delete),
                      ("Import pasted rules…", import_pasted)):
        ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 6))

    def show(f, where):
        st["file"], st["where"] = f, "From %s: " % where
        if not f.exists:
            st["where"] += "no filters file yet. "
        fill()

    def from_ps5():
        def work():
            with connect() as c:
                return load_console(c)

        def done(f, err):
            if err:
                status.set("Couldn't read the PS5: %s" % err)
            else:
                show(f, "the PS5")
        status.set("Reading your filters from the PS5…")
        run(work, done)

    def from_file():
        path = filedialog.askopenfilename(parent=win, filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if path:
            try:
                show(load_local(path), "the file")
            except OSError as e:
                messagebox.showerror(title, "Couldn't read the file: %s" % e, parent=win)

    def to_file():
        data = guarded(st["file"].serialize)
        if data is None:
            return
        path = filedialog.asksaveasfilename(parent=win, defaultextension=".txt",
                                            initialfile=posixpath.basename(FILTERS_PATH))
        if path:
            prev = save_local(path, data)
            status.set("Saved." + (" The old copy is kept as .prev." if prev else ""))

    def to_ps5():
        data = guarded(st["file"].serialize)
        if data is None:
            return
        name = posixpath.basename(FILTERS_PATH)
        if not messagebox.askokcancel(title, "Upload %s to the PS5?\n\nClose Omni first, or restart it right after: "
                                             "Omni reads this file when it starts, and hiding an element while it runs "
                                             "rewrites the file from what it loaded. The current file is kept beside "
                                             "it as %s%s." % (name, name, PREV_SUFFIX), parent=win):
            return

        def work():
            with connect() as c:
                return save_console(c, data)

        def done(parked, err):
            if err:
                status.set("Couldn't upload: %s" % err)
            else:
                status.set("Uploaded %s and checked it. Restart Omni to use it." % name
                           + (" The old file is kept as %s." % posixpath.basename(parked) if parked else ""))
        status.set("Uploading…")
        run(work, done)

    ttk.Label(win, textvariable=status, wraplength=860).pack(fill="x", padx=10)
    bar = ttk.Frame(win)
    bar.pack(fill="x", padx=8, pady=8)
    ps5_state = "normal" if connect else "disabled"
    ttk.Button(bar, text="Load from PS5", command=from_ps5, state=ps5_state).pack(side="left")
    ttk.Button(bar, text="Open file…", command=from_file).pack(side="left", padx=6)
    ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
    ttk.Button(bar, text="Upload to PS5", command=to_ps5, state=ps5_state).pack(side="right", padx=6)
    ttk.Button(bar, text="Save to file…", command=to_file).pack(side="right")

    show(from_bytes(None), "nowhere yet")
    if connect:
        from_ps5()
    return win
