"""Look inside an Omni backup zip and put single items back on the PS5.

Nothing is extracted to disk: the zip is checked in full by backup.read_backup first (allow-listed paths only, so no
"../" or absolute names, no links or folders, per-file / per-folder / total size caps, every entry matching the
manifest's size and sha256), and entries are then read into memory with the same capped reader.

Each item shows its group, size, date and a short preview: a line count for text, and the first few lines only for
files where that is harmless (bookmark titles, notes, short settings). Never for history, learned keyboard words,
bookmarklet keys, downloads, add-on data, highlights or reading-list pages, and never anything the backup can't hold
(passwords, parental controls and the rest of backup.NEVER are refused by the allow-list before any preview).

A restore goes through backup.restore (the same checks, allow-list and verified upload) narrowed to the chosen paths;
the file each one replaces is kept beside it as <name>.prev (.prev-2, ... when taken), like shortcuts_edit does.
Logs carry counts only, never a file name or content.
"""
import datetime
import posixpath
import zipfile
import zlib

from . import backup

PREV_SUFFIX = ".prev"
PREVIEW_LINES = 3
PREVIEW_WIDTH = 60
PREVIEW_READ_MAX = 4 * 1024 * 1024      # line counts read at most this much of one entry

# Paths whose first lines may be shown, and how to pick the shown part of a line.
_O = backup.OMNI


def _title_column(line):                 # bookmarks.txt: url TAB title [TAB folder] -> the title only
    parts = line.split("\t")
    return parts[1].strip() if len(parts) > 1 else ""


def _first_column(line):                 # search shortcuts: keyword TAB template -> the keyword only
    return line.split("\t")[0].split(" ")[0].strip()


def _whole(line):
    return line.strip()


PREVIEW_TEXT = {
    _O + "bookmarks.txt": _title_column,
    _O + "notes.txt": _whole,
    _O + "search-shortcuts.txt": _first_column,
    _O + "quick-access.txt": _whole,
}
# Small one-line settings files (theme, accent, scale...) show their value.
SMALL_SETTING_MAX = 4 * 1024
# Never a first-lines preview, whatever else would allow it.
NO_PREVIEW_GROUPS = ("history", "kb-words", "downloads", "addon-data", "highlights", "reading-list", "pointers",
                     "tab-sessions")
NO_PREVIEW_PATHS = (_O + "bookmarklets.txt",)


class Item(dict):
    """{"path", "name", "group", "group_name", "size", "date", "lines", "first"} for one file in a backup."""


def _show_first(path, group, size):
    if path in NO_PREVIEW_PATHS or group in NO_PREVIEW_GROUPS:
        return None
    if path in PREVIEW_TEXT:
        return PREVIEW_TEXT[path]
    if group == "settings" and path.endswith(".txt") and size <= SMALL_SETTING_MAX:
        return _whole
    return None


def _preview(data, path, group, size):
    """(line count or None for binary, [first lines] or None)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, None
    if "\0" in text:
        return None, None
    lines = text.splitlines()
    pick = _show_first(path, group, size)
    if pick is None:
        return len(lines), None
    first = []
    for line in lines:
        if len(first) >= PREVIEW_LINES:
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        shown = "".join(ch if ch.isprintable() else " " for ch in pick(line))
        if shown:
            first.append(shown[:PREVIEW_WIDTH] + ("…" if len(shown) > PREVIEW_WIDTH else ""))
    return len(lines), first


def _date(info, created):
    try:
        return datetime.datetime(*info.date_time).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return created or ""


def inspect(zip_path):
    """Check the backup and list what it holds. Returns {"created", "omni_version", "setup_version", "items": [Item]}
    in backup.GROUPS order, then by path. Raises backup.BackupError for anything damaged or unsafe."""
    manifest = backup.read_backup(zip_path)       # full check first: nothing is read for previews before it passes
    names = {g["id"]: g["name"] for g in backup.GROUPS}
    order = {g: i for i, g in enumerate(backup.GROUP_IDS)}
    created = manifest.get("created") if isinstance(manifest.get("created"), str) else ""
    items = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            for f in manifest["files"]:
                path, group, size = f["path"], f["group"], f["size"]
                rule = backup.rule_for(path)
                if rule is None:                   # read_backup refused these already; checked again
                    raise backup.BackupError("The backup holds a file Setup doesn't restore.")
                info = z.getinfo(backup.entry_name(path))
                data = backup._entry_bytes(z, info, min(rule["max"], PREVIEW_READ_MAX))
                lines, first = _preview(data, path, group, size) if size <= PREVIEW_READ_MAX else (None, None)
                items.append(Item(path=path, name=posixpath.basename(path), group=group,
                                  group_name=names.get(group, group), size=size, date=_date(info, created),
                                  lines=lines, first=first))
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error):
        raise backup.BackupError("The backup changed or is damaged. Nothing was changed.")
    items.sort(key=lambda i: (order.get(i["group"], 99), i["path"]))
    return {"created": created, "omni_version": manifest.get("omni_version"),
            "setup_version": manifest.get("setup_version"), "items": items}


def restore_items(console, zip_path, paths, log=lambda m: None, progress=None):
    """Put only `paths` (console paths from inspect()) back on the PS5, through backup.restore: the zip is checked in
    full, every path must be allow-listed and in the backup or nothing is written, and each replaced file is kept as
    <name>.prev. Omni must be closed. Returns backup.restore's result."""
    paths = list(paths or ())
    if not paths:
        raise backup.BackupError("Choose at least one item to restore.")
    if any(backup.rule_for(p) is None for p in paths):
        raise backup.BackupError("That item isn't one Setup restores. Nothing was changed.")
    return backup.restore(console, zip_path, groups=None, log=log, progress=progress, paths=paths,
                          park_suffix=PREV_SUFFIX)


def size_text(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.1f MB" % (n / 1024.0 / 1024.0)


def preview_text(item):
    """One short line for the list: line count and, when allowed, the first lines joined."""
    if item["lines"] is None:
        return "binary"
    out = "%d line%s" % (item["lines"], "" if item["lines"] == 1 else "s")
    if item["first"]:
        out += ": " + " | ".join(item["first"])
    return out


# -- Tk window -------------------------------------------------------------------------------------------------------
def open_window(root, zip_path, connect=None, run_bg=None, title="Inspect Omni backup"):
    """A Toplevel listing the backup's items; "Restore selected" puts the ticked ones back. `connect()` returns a
    console (None when no PS5 is set), `run_bg(work, done)` runs work off the UI thread and calls done(result, err)."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    run_bg = run_bg or _inline
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("860x480")
    status = tk.StringVar(value="Checking the backup…")
    ttk.Label(win, textvariable=status, wraplength=820).pack(anchor="w", padx=12, pady=(10, 6))
    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=12)
    cols = ("group", "size", "date", "preview")
    tree = ttk.Treeview(frame, columns=cols, show="tree headings", selectmode="extended")
    tree.heading("#0", text="File")
    for c, w in zip(cols, (130, 80, 120, 330)):
        tree.heading(c, text=c.capitalize())
        tree.column(c, width=w, stretch=(c == "preview"))
    tree.column("#0", width=180)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=10)
    ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")
    restore_btn = ttk.Button(btns, text="Restore selected to the PS5", state="disabled")
    restore_btn.pack(side="right", padx=8)
    by_iid = {}

    def loaded(r, err):
        if err:
            status.set("Can't use this backup: %s" % err)
            return
        for it in r["items"]:
            iid = tree.insert("", "end", text=it["name"], values=(it["group_name"], size_text(it["size"]), it["date"],
                                                                 preview_text(it)))
            by_iid[iid] = it["path"]
        status.set("Backup from %s: %d item(s). Select the ones to put back; Omni must be closed. Each file they "
                   "replace is kept on the PS5 as <name>.prev." % (r["created"] or "an unknown date", len(r["items"])))
        if connect and r["items"]:
            restore_btn.configure(state="normal")

    def do_restore():
        paths = [by_iid[i] for i in tree.selection() if i in by_iid]
        if not paths:
            status.set("Select at least one item first.")
            return
        if not messagebox.askyesno(title, "Put %d item(s) back on the PS5? Close Omni first." % len(paths), parent=win):
            return
        restore_btn.configure(state="disabled")
        status.set("Putting %d item(s) on the PS5…" % len(paths))

        def work():
            c = connect()
            if c is None:
                raise backup.BackupError("No PS5 is set up.")
            if hasattr(c, "__enter__"):              # ps5.Console connects / closes as a context manager
                with c as live:
                    return restore_items(live, zip_path, paths)
            return restore_items(c, zip_path, paths)

        def done(r, err):
            restore_btn.configure(state="normal")
            if err:
                status.set("Couldn't restore: %s" % err)
            else:
                status.set("Done: %d written, %d already the same. Replaced files were kept as .prev."
                           % (r["written"], r["same"]))

        run_bg(work, done)

    restore_btn.configure(command=do_restore)
    run_bg(lambda: inspect(zip_path), loaded)
    return win


def _inline(fn, done):
    try:
        r = fn()
    except Exception as e:  # shown to the user
        done(None, e)
    else:
        done(r, None)
