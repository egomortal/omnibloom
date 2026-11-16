"""S06: an automatic Omni backup when Setup finds the PS5, keeping the last N.

Off until the user turns it on. When Setup connects to the PS5 anyway (the check page, the one-button install), and the
newest automatic backup is at least 24 hours old, it saves one backup with backup.backup() into its own folder,
<backup.default_folder()>/Automatic, named omni-auto-<date>-<time>.zip. Nothing extra polls or scans the network.

What it holds is chosen like a manual backup: Omni's settings always, bookmarks by default, and the other personal
groups (notes, history, My filters, ...) only when the user ticks them. backup.py's allow-list decides the rest, so
passwords, cookies, the open-tabs session, flags and the parental-controls file are never in it.

Only after the new zip passes backup.read_backup are older automatic backups beyond "keep last N" deleted, and only
files in the Automatic folder named like an automatic backup. Manual backups (omni-backup-*.zip, any folder) are never
touched. A backup that fails or doesn't verify is removed and every older backup stays.

The settings live on this PC (release.cache_dir()/auto-backup.json). Logs carry counts only, never file names.
"""
import datetime
import json
import os
import re
import time

from . import backup

SETTINGS_NAME = "auto-backup.json"
DEFAULT_GROUPS = ("settings", "bookmarks")
DEFAULT_KEEP = 5
KEEP_MIN, KEEP_MAX = 1, 20
INTERVAL = 24 * 60 * 60
FOLDER_NAME = "Automatic"
NAME_RE = re.compile(r"omni-auto-\d{4}-\d{2}-\d{2}-\d{6}(?:-\d+)?\.zip\Z")


def defaults():
    return {"enabled": False, "groups": list(DEFAULT_GROUPS), "keep": DEFAULT_KEEP, "last": None, "last_error": None}


def settings_path():
    from . import release
    return os.path.join(release.cache_dir(), SETTINGS_NAME)


def clean(s):
    """Settings with every value checked (unknown groups dropped, settings always in, keep clamped to 1-20)."""
    out = defaults()
    if not isinstance(s, dict):
        return out
    out["enabled"] = s.get("enabled") is True
    groups = s.get("groups")
    if isinstance(groups, (list, tuple)):
        out["groups"] = [g for g in backup.GROUP_IDS if g in groups or g == "settings"]
    try:
        out["keep"] = max(KEEP_MIN, min(KEEP_MAX, int(s.get("keep", DEFAULT_KEEP))))
    except (TypeError, ValueError):
        pass
    last = s.get("last")
    out["last"] = float(last) if isinstance(last, (int, float)) and not isinstance(last, bool) else None
    err = s.get("last_error")
    out["last_error"] = err if isinstance(err, str) else None
    return out


def load(path=None):
    try:
        with open(path or settings_path(), encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return defaults()


def save(s, path=None):
    path = path or settings_path()
    s = clean(s)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    return s


def folder(home=None):
    return os.path.join(backup.default_folder(home), FOLDER_NAME)


def new_path(dest_dir, when):
    stamp = when.strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(dest_dir, "omni-auto-%s.zip" % stamp)
    n = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, "omni-auto-%s-%d.zip" % (stamp, n))
        n += 1
    return path


def automatic_backups(dest_dir):
    """The automatic backups in `dest_dir`, oldest first (only names this module writes)."""
    try:
        names = os.listdir(dest_dir)
    except OSError:
        return []
    out = [n for n in names if NAME_RE.match(n) and os.path.isfile(os.path.join(dest_dir, n))]
    return [os.path.join(dest_dir, n) for n in sorted(out)]


def prune(dest_dir, keep, protect=None):
    """Delete the oldest automatic backups beyond `keep`; never `protect` (the one just made). Returns the count."""
    paths = automatic_backups(dest_dir)
    extra = [p for p in paths[:max(0, len(paths) - keep)] if p != protect]
    removed = 0
    for p in extra:
        try:
            os.remove(p)
            removed += 1
        except OSError:
            pass
    return removed


def due(s, now):
    return s["enabled"] and (s["last"] is None or now - s["last"] >= INTERVAL or s["last"] > now)


def maybe_run(console, settings_file=None, dest_dir=None, clock=time.time, log=lambda m: None, run=None, verify=None):
    """Called whenever Setup has connected to the PS5. Returns None when off or not due, else
    {"ok": True, "path", "files", "pruned"} or {"ok": False, "error"}. Never raises."""
    try:
        s = load(settings_file)
    except Exception:
        return None
    now = clock()
    if not due(s, now):
        return None
    run = run or backup.backup
    verify = verify or backup.read_backup
    dest_dir = dest_dir or folder()
    path = None
    try:
        os.makedirs(dest_dir, exist_ok=True)
        path = new_path(dest_dir, datetime.datetime.fromtimestamp(now))
        r = run(console, s["groups"], path)
        verify(path)
    except Exception as e:
        if path and os.path.exists(path):
            try:
                os.remove(path)    # ours, and not a usable backup
            except OSError:
                pass
        s["last_error"] = str(e) or type(e).__name__
        _save_quiet(s, settings_file)
        log("Automatic backup failed; older backups were kept.")
        return {"ok": False, "error": s["last_error"]}
    pruned = prune(dest_dir, s["keep"], protect=path)
    s["last"], s["last_error"] = now, None
    _save_quiet(s, settings_file)
    files = r.get("files", 0) if isinstance(r, dict) else 0
    log("Automatic backup: %d file(s) saved%s." % (files, ("; %d older one(s) removed" % pruned) if pruned else ""))
    return {"ok": True, "path": path, "files": files, "pruned": pruned}


def _save_quiet(s, path):
    try:
        save(s, path)
    except OSError:
        pass


def ago(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "just now"
    for unit, size in (("day", 86400), ("h", 3600), ("min", 60)):
        if seconds >= size:
            n = seconds // size
            return "%d %s%s ago" % (n, unit, "s" if unit == "day" and n != 1 else "")
    return "just now"


def status_line(s=None, now=None):
    """One line for the window: "Backed up 2 min ago", or why there's nothing yet."""
    s = clean(s) if s is not None else load()
    now = time.time() if now is None else now
    if not s["enabled"]:
        return "Automatic backup is off."
    if s["last_error"]:
        return "Last automatic backup failed: %s" % s["last_error"]
    if s["last"] is None:
        return "Automatic backup is on; it runs the next time Setup finds your PS5."
    return "Backed up %s." % ago(now - s["last"])


def open_window(root, on_change=None, settings_file=None, title="Automatic backup"):
    """A Toplevel with the on/off tick, the groups to include and "keep last N"; saved when Save is pressed."""
    import tkinter as tk
    from tkinter import ttk

    s = load(settings_file)
    win = tk.Toplevel(root)
    win.title(title)
    enabled = tk.BooleanVar(value=s["enabled"])
    ttk.Checkbutton(win, text="Back up automatically when the PS5 is found", variable=enabled).pack(
        anchor="w", padx=12, pady=(10, 4))
    ttk.Label(win, wraplength=560, justify="left", text=(
        "At most once a day, into %s. Include:" % folder())).pack(anchor="w", padx=12)
    picks = {}
    for g in backup.GROUPS:
        var = tk.BooleanVar(value=bool(g.get("always")) or g["id"] in s["groups"])
        picks[g["id"]] = var
        ttk.Checkbutton(win, text="%s  (%s)" % (g["name"], g["detail"]), variable=var,
                        state="disabled" if g.get("always") else "normal").pack(anchor="w", padx=24)
    row = ttk.Frame(win)
    row.pack(anchor="w", padx=12, pady=8)
    ttk.Label(row, text="Keep the last").pack(side="left")
    keep = tk.IntVar(value=s["keep"])
    ttk.Spinbox(row, from_=KEEP_MIN, to=KEEP_MAX, textvariable=keep, width=4).pack(side="left", padx=6)
    ttk.Label(row, text="automatic backups (your own backups are never deleted).").pack(side="left")
    ttk.Label(win, wraplength=560, justify="left", text=(
        "Saved passwords, cookies, sign-ins, open tabs and parental controls are never included. The zips hold what "
        "you tick in plain form.")).pack(anchor="w", padx=12)

    def do_save():
        cur = load(settings_file)
        cur["enabled"] = enabled.get()
        cur["groups"] = [g for g, v in picks.items() if v.get()]
        try:
            cur["keep"] = keep.get()
        except (tk.TclError, ValueError):
            pass
        save(cur, settings_file)
        if on_change:
            on_change()
        win.destroy()

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(4, 10))
    ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(btns, text="Save", command=do_save).pack(side="right", padx=8)
    return win
