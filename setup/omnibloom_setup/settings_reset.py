"""S08: reset Omni's settings to their defaults, keeping personal data, with a full backup first.

What is reset is exactly backup.py's "settings" group (backup.FILES rows with group "settings"); nothing else on the
console is touched: bookmarks, history, notes, highlights, reading list, saved sessions, passwords, cookies (the browser
profile), the parental-controls file and everything in backup.NEVER stay where they are.

Order: (1) a backup of every group goes to a zip on this PC and is checked with backup.read_backup; if that fails,
nothing on the PS5 is changed. (2) plan() lists the settings files that are on the console. (3) the GUI asks.
(4) each file is renamed to <name>.reset-<time> over FTP (never deleted); Omni starts with its defaults next time.
undo_last() renames the newest reset's files back (a default file Omni wrote meanwhile is parked as
<name>.after-reset-<time>). Logs carry counts only, never file names.
"""
import posixpath
import re

from . import backup

SETTINGS_FILES = tuple(f["path"] for f in backup.FILES if f["group"] == "settings")
# Never renamed, never read by a reset: every other backup row, and everything a backup leaves out on purpose.
PROTECTED = tuple(f["path"] for f in backup.FILES if f["group"] != "settings") + tuple(
    f["dir"] for f in backup.FOLDERS) + backup.NEVER
assert not set(SETTINGS_FILES) & set(PROTECTED)
assert backup.OMNI + "parental.txt" in PROTECTED

RESET_TAG = ".reset-"
AFTER_TAG = ".after-reset-"
_STAMP = re.compile(r"\d{8}T\d{6}Z(?:-\d+)?\Z")


class ResetError(Exception):
    """The reset or undo stopped; the message is for the user."""


def _stamp():
    from . import installer
    return installer._stamp()


def _listings(console, paths):
    out = {}
    for p in paths:
        parent = posixpath.dirname(p)
        if parent not in out:
            out[parent] = console.listing(parent) or {}
    return out


def _is_file(listings, path):
    parent, name = posixpath.split(path)
    entry = listings[parent].get(name)
    return entry is not None and not entry.get("dir")


def plan(console):
    """The settings files on the console that a reset would rename, in backup.FILES order."""
    listings = _listings(console, SETTINGS_FILES)
    return [p for p in SETTINGS_FILES if _is_file(listings, p)]


def _unique_stamp(console, paths, stamp):
    """`stamp`, or stamp-2, -3... when some <path>.reset-<stamp> already exists (two resets in one second)."""
    listings = _listings(console, paths)
    taken = lambda s: any(posixpath.basename(p) + RESET_TAG + s in listings[posixpath.dirname(p)] for p in paths)
    out, n = stamp, 2
    while taken(out):
        out, n = "%s-%d" % (stamp, n), n + 1
    return out


def make_backup(console, dest, log=lambda m: None, backup_fn=None, check_fn=None):
    """Full backup (every group) to `dest`, then read it back. Raises ResetError when either fails."""
    backup_fn = backup_fn or backup.backup
    check_fn = check_fn or backup.read_backup
    try:
        r = backup_fn(console, list(backup.GROUP_IDS), dest, log=log)
        check_fn(r["path"] if isinstance(r, dict) and r.get("path") else dest)
    except Exception as e:  # any failure stops the reset before the PS5 is touched
        raise ResetError("The backup didn't work (%s). Nothing on the PS5 was changed." % e)
    return r


def reset(console, dest, paths=None, log=lambda m: None, backup_fn=None, check_fn=None, stamp=None):
    """Back up everything to `dest`, then rename the settings files to <name>.reset-<time>.
    `paths` is what the user confirmed (from plan()); only settings files are accepted.
    Returns {"backup", "renamed": [path], "suffix"}."""
    if paths is not None and not set(paths) <= set(SETTINGS_FILES):
        raise ResetError("That isn't an Omni settings file. Nothing was changed.")
    r = make_backup(console, dest, log=log, backup_fn=backup_fn, check_fn=check_fn)
    current = plan(console)
    todo = current if paths is None else [p for p in current if p in set(paths)]
    suffix = RESET_TAG + _unique_stamp(console, todo, stamp or _stamp())
    done = []
    try:
        for p in todo:
            console.rename(p, p + suffix)
            done.append(p)
    except Exception as e:
        undone = 0
        for p in reversed(done):                   # put back what was moved, so Omni isn't left half reset
            try:
                console.rename(p + suffix, p)
                undone += 1
            except Exception:
                pass
        raise ResetError("Renaming stopped (%s). %d file(s) were put back%s. Your backup is at %s." % (
            e, undone, "" if undone == len(done) else "; use Undo last reset for the rest", r.get("path", dest)))
    log("Omni settings reset: %d file(s) renamed." % len(done))
    return {"backup": r, "renamed": done, "suffix": suffix}


def last_reset(console):
    """(suffix, [settings path]) of the newest reset still on the console, or (None, [])."""
    listings = _listings(console, SETTINGS_FILES)
    found = {}
    for p in SETTINGS_FILES:
        parent, name = posixpath.split(p)
        for entry_name, entry in listings[parent].items():
            if entry.get("dir") or not entry_name.startswith(name + RESET_TAG):
                continue
            s = entry_name[len(name + RESET_TAG):]
            if _STAMP.match(s):
                found.setdefault(s, []).append(p)
    if not found:
        return None, []
    newest = max(found, key=lambda s: (s[:16], int(s[17:] or 1)))
    return RESET_TAG + newest, [p for p in SETTINGS_FILES if p in found[newest]]


def undo_last(console, log=lambda m: None, stamp=None):
    """Rename the newest reset's files back. A file Omni wrote since then is parked as <name>.after-reset-<time>.
    Returns {"restored": [path], "parked": [path], "suffix"}; raises ResetError when there is nothing to undo."""
    suffix, paths = last_reset(console)
    if not suffix:
        raise ResetError("There is no Omni settings reset to undo on the PS5.")
    listings = _listings(console, paths)
    after = AFTER_TAG + (stamp or _stamp())
    restored, parked = [], []
    for p in paths:
        if _is_file(listings, p):
            console.rename(p, p + after)
            parked.append(p)
        console.rename(p + suffix, p)
        restored.append(p)
    log("Omni settings reset undone: %d file(s) back, %d newer default(s) kept aside." % (len(restored), len(parked)))
    return {"restored": restored, "parked": parked, "suffix": suffix}


# -- Tk window -------------------------------------------------------------------------------------------------------
def _with(c, fn):
    if hasattr(c, "__enter__"):                    # ps5.Console connects / closes as a context manager
        with c as live:
            return fn(live)
    return fn(c)


def open_window(root, connect, dest_fn, run_bg=None, title="Reset Omni settings"):
    """A Toplevel: lists the settings files on the PS5, asks, backs up to dest_fn() then resets; "Undo last reset"
    renames them back. `connect()` returns a console (None when no PS5 is set)."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    run_bg = run_bg or _inline
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("640x460")
    status = tk.StringVar(value="Reading which Omni settings files are on the PS5…")
    ttk.Label(win, textvariable=status, wraplength=600, justify="left").pack(anchor="w", padx=12, pady=(10, 6))
    box = tk.Listbox(win, height=12)
    box.pack(fill="both", expand=True, padx=12)
    ttk.Label(win, wraplength=600, justify="left", text=(
        "Only settings are reset. Bookmarks, history, notes, highlights, the reading list, saved passwords, cookies "
        "and parental controls are never touched. A full backup is saved on this PC first, and each file is renamed "
        "(<name>.reset-<time>), not deleted.")).pack(anchor="w", padx=12, pady=6)
    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(0, 10))
    ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")
    reset_btn = ttk.Button(btns, text="Back up and reset", state="disabled")
    reset_btn.pack(side="right", padx=8)
    undo_btn = ttk.Button(btns, text="Undo last reset", state="disabled" if connect is None else "normal")
    undo_btn.pack(side="left")
    found = []

    def need():
        c = connect() if connect else None
        if c is None:
            raise ResetError("No PS5 is set up.")
        return c

    def listed(paths, err):
        if err:
            status.set("Couldn't read the PS5: %s" % err)
            return
        found[:] = paths
        box.delete(0, "end")
        for p in paths:
            box.insert("end", p)
        if not paths:
            status.set("Omni has no settings files on the PS5: it is already on its defaults.")
            return
        status.set("%d settings file(s) will be renamed so Omni starts with its defaults. Close Omni first." % len(paths))
        reset_btn.configure(state="normal")

    def do_reset():
        if not found or not messagebox.askyesno(title, "Back up Omni to this PC, then reset %d settings file(s)?\n\n"
                                                "Close Omni on the PS5 first." % len(found), icon="warning", parent=win):
            return
        reset_btn.configure(state="disabled")
        undo_btn.configure(state="disabled")
        status.set("Backing up Omni to this PC…")
        dest, paths = dest_fn(), list(found)

        def done(r, err):
            undo_btn.configure(state="normal")
            if err:
                status.set("Reset stopped: %s" % err)
                reset_btn.configure(state="normal")
                return
            status.set("Done: %d file(s) renamed. Backup saved to %s.\nRestart Omni on the PS5 to use its default "
                       "settings." % (len(r["renamed"]), r["backup"].get("path", dest)))

        run_bg(lambda: _with(need(), lambda c: reset(c, dest, paths)), done)

    def do_undo():
        if not messagebox.askyesno(title, "Put the settings from the last reset back? Close Omni first.", parent=win):
            return
        undo_btn.configure(state="disabled")

        def done(r, err):
            undo_btn.configure(state="normal")
            if err:
                status.set("Couldn't undo: %s" % err)
                return
            status.set("Undone: %d settings file(s) are back. Restart Omni on the PS5 to use them." % len(r["restored"]))
            run_bg(lambda: _with(need(), plan), listed)

        run_bg(lambda: _with(need(), undo_last), done)

    reset_btn.configure(command=do_reset)
    undo_btn.configure(command=do_undo)
    if connect is None:
        status.set("Set up a PS5 first.")
    else:
        run_bg(lambda: _with(need(), plan), listed)
    return win


def _inline(fn, done):
    try:
        r = fn()
    except Exception as e:  # shown to the user
        done(None, e)
    else:
        done(r, None)
