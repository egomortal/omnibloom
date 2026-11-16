"""S15: the PC settings editor: every Omni setting from settings_catalog.py, grouped, searchable, with its description.

Values are read from the PS5 (one read per catalog file that exists), changed with a toggle / choice / number control,
validated with the catalog's rules, and uploaded per file: serialize() gives Omni's own bytes, the upload is the
verified one every Setup write uses (temp file, sha256 readback, moved into place) and the old file is parked beside
it as <name>.prev (.prev-2, ... when taken), never deleted. Only settings_catalog.EDITABLE files are ever written;
parental controls, passwords and personal data are refused by settings_catalog.path_for().
Logs carry file names and counts only (settings files hold no personal data; free-text lines are never logged).
"""
import posixpath

from . import settings_catalog as sc

PREV_SUFFIX = ".prev"
READ_CAP = 2 * 1024 * 1024


def load_console(console):
    """{path: bytes or None} for every editable catalog file (None: not on the PS5, Omni uses its defaults)."""
    out = {}
    for path in sc.EDITABLE:
        out[path] = console.read(path) if console.exists(path) else None
    return out


def values_from(raw):
    """{path: {key: token}} as Omni reads each file."""
    return {p: sc.parse(sc.BY_PATH[p], raw.get(p)) for p in sc.EDITABLE}


def changed_files(loaded, edited):
    """Paths whose edited values differ from what was read."""
    return [p for p in sc.EDITABLE if edited.get(p, loaded.get(p)) != loaded.get(p)]


def plan(raw, loaded, edited):
    """[(path, bytes)] to upload for every changed file (SettingError on the first value Omni would not take)."""
    out = []
    for p in changed_files(loaded, edited):
        out.append((p, sc.serialize(sc.BY_PATH[p], edited[p], raw.get(p))))
    return out


def save_console(console, path, data, log=lambda m: None):
    """Verified upload of one settings file; the old file is parked as <name>.prev(-N). Returns the parked path or
    None (no old file, or it already held these bytes)."""
    from . import installer   # here, so this module loads without the installer's imports
    sc.path_for(path)
    old = console.read(path) if console.exists(path) else None
    if old == data:
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
    log("Settings editor: %s written." % posixpath.basename(path))
    return parked


def upload(console, changes, log=lambda m: None):
    """Write every (path, bytes) of plan(); every path is checked before anything is written.
    Returns [(path, parked or None)]."""
    for path, _ in changes:
        sc.path_for(path)
    done = [(path, save_console(console, path, data, log)) for path, data in changes]
    log("Settings editor: %d file(s) uploaded." % len(done))
    return done


# -- Tk window -------------------------------------------------------------------------------------------------------
def open_window(root, connect=None, run_bg=None, title="Omni settings (all)"):
    """connect(): a context-managed ps5.Console (None = no PS5 set up); run_bg(fn, done(result, err))."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    run = run_bg or _inline
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("980x620")
    state = {"raw": {}, "loaded": values_from({}), "edited": values_from({}), "ready": False}

    top = ttk.Frame(win, padding=(10, 8, 10, 0))
    top.pack(fill="x")
    ttk.Label(top, text="Search").pack(side="left")
    query = tk.StringVar()
    ttk.Entry(top, textvariable=query, width=40).pack(side="left", padx=6)
    ttk.Label(top, text="● changed   ◆ not Omni's default   live: applies while Omni runs").pack(side="right")

    mid = ttk.Panedwindow(win, orient="horizontal")
    mid.pack(fill="both", expand=True, padx=10, pady=8)
    tree = ttk.Treeview(mid, columns=("value", "mark"), show="tree headings", selectmode="browse")
    tree.heading("#0", text="Setting")
    tree.heading("value", text="Value")
    tree.heading("mark", text="")
    tree.column("#0", width=330)
    tree.column("value", width=200)
    tree.column("mark", width=70, anchor="center")
    mid.add(tree, weight=3)
    side = ttk.Frame(mid, padding=(10, 0))
    mid.add(side, weight=2)
    info = tk.StringVar(value="Pick a setting.")
    ttk.Label(side, textvariable=info, wraplength=330, justify="left").pack(anchor="w")
    ctl_box = ttk.Frame(side)
    ctl_box.pack(anchor="w", fill="x", pady=8)

    status = tk.StringVar(value=sc.RESTART_NOTE)
    ttk.Label(win, textvariable=status, wraplength=940, justify="left").pack(fill="x", padx=10)
    bar = ttk.Frame(win, padding=10)
    bar.pack(fill="x")
    rows = {}   # tree id -> (path, key) or (path, None) for a read-only file

    def mark(path, key):
        f = next(f for f in sc.BY_PATH[path]["fields"] if f["key"] == key)
        v = state["edited"][path][key]
        out = "●" if v != state["loaded"][path][key] else ""
        return out + ("◆" if v != f["default"] else "")

    def fill():
        tree.delete(*tree.get_children())
        rows.clear()
        q = query.get().strip().lower()
        for g in sc.GROUPS:
            gid = None
            for e in [e for e in sc.CATALOG if e["group"] == g]:
                shown = sc.fields(e) if e["path"] in sc.EDITABLE else [None]
                for f in shown:
                    label = f["label"] if f else e["name"]
                    hay = " ".join((label, f["desc"] if f else "", e["desc"], e["name"])).lower()
                    if q and q not in hay:
                        continue
                    if gid is None:
                        gid = tree.insert("", "end", text=g, open=True)
                    if f is None:
                        iid = tree.insert(gid, "end", text=label + "  (read only)", values=(e["desc"], ""))
                        rows[iid] = (e["path"], None)
                        continue
                    tok = state["edited"][e["path"]][f["key"]]
                    text = label + ("  (live)" if e["live"] else "")
                    iid = tree.insert(gid, "end", text=text, values=(sc.describe_value(f, tok), mark(e["path"], f["key"])))
                    rows[iid] = (e["path"], f["key"])

    def on_select(_e=None):
        for w in ctl_box.winfo_children():
            w.destroy()
        sel = tree.selection()
        if not sel or sel[0] not in rows:
            return
        path, key = rows[sel[0]]
        e = sc.BY_PATH[path]
        if key is None:
            info.set("%s\n\n%s\n\nFile: %s\nNot edited here%s." % (e["name"], e["desc"], path,
                                                                  ": " + e["where"] if e["where"] else ""))
            return
        f = next(f for f in e["fields"] if f["key"] == key)
        allowed = ("%s to %s" % (f["lo"], f["hi"]) if f["kind"] == sc.NUMBER
                   else ", ".join(lbl for _, lbl in f["choices"]))
        info.set("%s\n\n%s\n\nFile: %s%s\nAllowed: %s\nDefault: %s\n%s" % (
            f["label"], f["desc"] or e["desc"], path, " (key %s)" % key if key else "", allowed,
            sc.describe_value(f, f["default"]), "Applies while Omni runs." if e["live"] else
            "Omni reads it at start: restart Omni after uploading."))
        cur = state["edited"][path][key]
        if f["kind"] == sc.NUMBER:
            var = tk.StringVar(value=cur)
            ttk.Spinbox(ctl_box, from_=f["lo"], to=f["hi"], increment=f["step"], textvariable=var, width=12
                        ).pack(side="left")
            getter = var.get
        else:
            labels = [lbl for _, lbl in f["choices"]]
            tokens = [t for t, _ in f["choices"]]
            if cur not in tokens:          # e.g. a language code set by hand: kept as a choice
                labels.append(cur)
                tokens.append(cur)
            box = ttk.Combobox(ctl_box, state="readonly", values=labels, width=30)
            box.current(tokens.index(cur))
            box.pack(side="left")
            getter = lambda: tokens[box.current()]

        def set_value(v=None):
            v = getter() if v is None else v
            if f["kind"] == sc.NUMBER:
                try:
                    v = f["fmt"] % (float(v) if "." in f["fmt"] else int(float(v)))
                except ValueError:
                    pass
            trial = dict(state["edited"][path], **{key: v})
            bad = [m for k, m in sc.problems(e, trial) if k == key]
            if bad:
                messagebox.showerror(title, bad[0] + ".", parent=win)
                return
            state["edited"][path] = trial
            fill()
            for iid, rk in rows.items():
                if rk == (path, key):
                    tree.selection_set(iid)
                    tree.see(iid)
        ttk.Button(ctl_box, text="Set", command=set_value).pack(side="left", padx=6)
        ttk.Button(ctl_box, text="Omni's default", command=lambda: set_value(f["default"])).pack(side="left")

    tree.bind("<<TreeviewSelect>>", on_select)
    query.trace_add("write", lambda *_: fill())

    def need():
        if connect is None:
            raise sc.SettingError("No PS5 is set up.")
        return connect()

    def from_ps5():
        def work():
            with need() as c:
                return load_console(c)

        def done(raw, err):
            if err:
                status.set("Couldn't read the PS5: %s" % err)
                return
            state["raw"] = raw
            state["loaded"] = values_from(raw)
            state["edited"] = {p: dict(v) for p, v in state["loaded"].items()}
            state["ready"] = True
            fill()
            status.set("Read %d settings file(s) from the PS5 (%d not there yet: Omni's defaults). %s" % (
                sum(1 for v in raw.values() if v is not None), sum(1 for v in raw.values() if v is None),
                sc.RESTART_NOTE))
        status.set("Reading Omni's settings from the PS5…")
        run(work, done)

    def to_ps5():
        if not state["ready"]:
            messagebox.showinfo(title, "Load the settings from the PS5 first.", parent=win)
            return
        try:
            changes = plan(state["raw"], state["loaded"], state["edited"])
        except sc.SettingError as e:
            messagebox.showerror(title, str(e), parent=win)
            return
        if not changes:
            status.set("Nothing changed.")
            return
        names = "\n".join(posixpath.basename(p) for p, _ in changes)
        live = all(sc.BY_PATH[p]["live"] for p, _ in changes)
        if not messagebox.askokcancel(title, "Close Omni on the PS5 first (it rewrites these files when it saves).\n\n"
                                      "Upload %d file(s)? Each old file is kept beside it as <name>%s.\n\n%s\n\n%s" % (
                                          len(changes), PREV_SUFFIX, names,
                                          "These apply while Omni runs." if live else
                                          "Start Omni again to use them."), parent=win):
            return

        def work():
            with need() as c:
                return upload(c, changes)

        def done(r, err):
            if err:
                status.set("Upload stopped: %s. Load from the PS5 again to see what is there." % err)
                return
            status.set("Uploaded and checked %d file(s); old copies kept as .prev. %s" % (
                len(r), "" if live else "Start Omni again to use them."))
            from_ps5()
        status.set("Uploading…")
        run(work, done)

    def revert():
        state["edited"] = {p: dict(v) for p, v in state["loaded"].items()}
        fill()

    ps5 = "normal" if connect else "disabled"
    ttk.Button(bar, text="Load from PS5", command=from_ps5, state=ps5).pack(side="left")
    ttk.Button(bar, text="Undo my changes", command=revert).pack(side="left", padx=6)
    ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
    ttk.Button(bar, text="Upload changes to PS5", command=to_ps5, state=ps5).pack(side="right", padx=6)
    fill()
    if connect:
        from_ps5()
    else:
        status.set("Set up a PS5 first. " + sc.RESTART_NOTE)
    return win


def _inline(fn, done):
    try:
        r = fn()
    except Exception as e:  # shown to the user
        done(None, e)
    else:
        done(r, None)
