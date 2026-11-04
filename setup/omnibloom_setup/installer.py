"""Install, update, repair and uninstall, one app at a time (Omnibloom plug-in standard, hub_api 1).

For each app Setup writes:
- its files (upload as `<file>.omnibloom-new`, read back and check the hash, then move into place;
  anything already there is parked as a backup; nothing is ever deleted);
- its ID card, `/data/hub/apps/<id>.json`, with the port Setup picked;
- its receipt, `/data/hub/receipts/<id>.json`: files, backups, card hash, port, autoload change.
Bloom Core (`hub`) goes in first. Other apps don't need it to start, so they still install without it.
The user's own data (profiles, downloads, pairings, shared settings) is never touched.
"""
import datetime
import hashlib
import json
import os
import posixpath

from . import config
from .ports import PortPicker
from .release import cache_dir, version_key

RECEIPT_SCHEMA = "hub-receipt/v1"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode("utf-8")


def _decoded_on_readback(dest):
    return posixpath.basename(dest) in config.DECODED_ON_READBACK


def _free_name(console, path, suffix):
    parent, name = posixpath.split(path)
    names = console.listing(parent)
    candidate = name + suffix
    n = 2
    while candidate in names:
        candidate = "%s%s-%d" % (name, suffix, n)
        n += 1
    return posixpath.join(parent, candidate)


def _jd_tree(path):
    """Files of the JDownloader 2 engine: the console checks those folders for an exact file set, so nothing
    may be parked beside them; old copies go to setup-backup/ instead."""
    return path.startswith(config.JD_CONSOLE_ROOT) and not path.startswith(config.JD_BACKUP_DIR)


def _park(console, path, suffix, stamp=None):
    """Move `path` aside (never delete) and return where it went."""
    if _jd_tree(path):
        target = config.JD_BACKUP_DIR + (stamp or _stamp()) + "/" + path[len(config.JD_CONSOLE_ROOT):]
        console.makedirs(posixpath.dirname(target))
        if console.exists(target):
            target = _free_name(console, target, suffix)
    else:
        target = _free_name(console, path, suffix)
    console.rename(path, target)
    return target


def _replace(console, path, data, park_suffix):
    """Write a Setup-owned file (card, receipt, payload json) safely: verified temp, park old, move in."""
    console.makedirs(posixpath.dirname(path))
    temp = console.put_verified(path, data)
    if console.exists(path):
        console.rename(path, _free_name(console, path, park_suffix))
    console.rename(temp, path)


# -- receipts -------------------------------------------------------------
def receipt_path(app_id):
    return config.RECEIPTS_DIR + app_id + ".json"


def card_path(app_id):
    return config.CARDS_DIR + app_id + ".json"


def details_path(app_id):
    return config.DETAILS_DIR + app_id + ".json"


def read_receipt(console, app_id):
    """The receipt plus its details (file list, backups, full card) as one dict."""
    text = console.read_text(receipt_path(app_id), default=None)
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    if value.get("schema") != RECEIPT_SCHEMA or value.get("id") != app_id:
        return None
    try:
        details = json.loads(console.read_text(details_path(app_id), default="{}") or "{}")
    except ValueError:
        details = {}
    value["files"] = details.get("files", [])
    value["card"] = details.get("card")
    return value


def installed_apps(console):
    """{app_id: receipt} for every app Setup installed on this PS5."""
    found = {}
    for name, entry in console.listing(config.RECEIPTS_DIR).items():
        if not entry["dir"] and name.endswith(".json"):
            rec = read_receipt(console, name[:-5])
            if rec:
                found[rec["id"]] = rec
    return found


def _save_receipt(console, receipt, log):
    """Two files: the small receipt Bloom Core checks (<= 8 KiB) and the details Setup needs."""
    details = {"schema": RECEIPT_SCHEMA + "-details", "id": receipt["id"], "files": receipt["files"], "card": receipt["card"]}
    small = {k: v for k, v in receipt.items() if k not in ("files", "card") and v is not None}
    small["details"] = details_path(receipt["id"])
    small["history"] = small.get("history", [])[-5:]
    data = _json_bytes(small)
    if len(data) > config.RECEIPT_MAX:
        raise IOError("Receipt too large for Bloom Core (%d bytes)." % len(data))
    console.makedirs(config.DETAILS_DIR)
    _replace(console, details_path(receipt["id"]), _json_bytes(details), ".prev-" + _stamp())
    _replace(console, receipt_path(receipt["id"]), data, ".prev-" + _stamp())
    try:
        local = os.path.join(cache_dir(), "receipts", console.host.replace(":", "_"))
        os.makedirs(local, exist_ok=True)
        with open(os.path.join(local, receipt["id"] + ".json"), "wb") as f:
            f.write(_json_bytes(dict(small, files=receipt["files"], card=receipt["card"])))
    except OSError:
        pass


# -- autoload -------------------------------------------------------------
def _split_lines(text):
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n").split("\n"), nl


def set_autoload(console, elf_name, enable, log, replace=()):
    """Add or remove one payload in autoload.txt (bare file names only). Returns the receipt record."""
    original = console.read_text(config.AUTOLOAD_PATH, default="")
    lines, nl = _split_lines(original)
    lines = [ln for ln in lines if ln.strip()]
    removed = []
    if enable:
        keep = []
        for ln in lines:
            low = ln.strip().lower()
            if replace and low != elf_name and any(n in low for n in replace):
                removed.append(ln.strip())
                continue
            keep.append(ln)
        if elf_name not in [k.strip() for k in keep]:
            keep.append(elf_name)
        new_lines = keep
    else:
        new_lines = [ln for ln in lines if ln.strip() != elf_name]
    if new_lines == lines:
        return {"elf": elf_name, "changed": False, "removed": [], "backup": None}
    new_text = nl.join(new_lines) + nl
    backup = None
    if original:
        backup = _free_name(console, config.AUTOLOAD_PATH, ".before-omnibloom-" + _stamp())
        console.store(backup, original.encode("utf-8"))
        if console.read(backup) != original.encode("utf-8"):
            raise IOError("Couldn't back up autoload.txt; nothing was changed.")
    # Payload Manager reads this file at boot: rewrite it in place, then check it.
    console.store(config.AUTOLOAD_PATH, new_text.encode("utf-8"))
    if console.read(config.AUTOLOAD_PATH) != new_text.encode("utf-8"):
        if original:
            console.store(config.AUTOLOAD_PATH, original.encode("utf-8"))
        raise IOError("autoload.txt didn't save correctly; the old list was put back.")
    log("%s %s the start list (backup: %s)." % (elf_name, "added to" if enable else "removed from", backup or "none"))
    return {"elf": elf_name, "changed": True, "removed": removed, "backup": backup}


def _restore_autoload_entries(console, names, log):
    text = console.read_text(config.AUTOLOAD_PATH, default="")
    lines, nl = _split_lines(text)
    lines = [ln for ln in lines if ln.strip()]
    added = [n for n in names if n not in [l.strip() for l in lines]]
    if added:
        console.store(config.AUTOLOAD_PATH, (nl.join(lines + added) + nl).encode("utf-8"))
        log("Put back in the start list: %s" % ", ".join(added))


# -- shared folders --------------------------------------------------------
def ensure_shared(console, app_id, log):
    for d in (config.CARDS_DIR, config.DETAILS_DIR, config.LOGS_DIR + app_id + "/", config.CRASH_DIR + app_id + "/"):
        console.makedirs(d)
    if not console.exists(config.SETTINGS_PATH):  # created once; after that it's the user's settings
        console.store(config.SETTINGS_PATH, _json_bytes(config.DEFAULT_SETTINGS))
        log("Created the shared settings file.")


# -- cards -------------------------------------------------------------
def make_card(app_id, app, port, icon_path):
    card = {"hub_api": config.HUB_API, "id": app_id, "version": app["version"], "port": port}
    for k, v in app["card"].items():
        if k not in card:
            card[k] = v
    if icon_path:
        card["icon"] = icon_path
    return {k: v for k, v in card.items() if v is not None}   # Bloom Core treats a null field as invalid


def writes_card(app_id, card=None):
    """Bloom Core doesn't take a card for itself (its port 8760 is reserved): it gets a receipt only.
    Neither does a payload/service without a fixed port (the JDownloader 2 engine, started by downloads with a
    per-session loopback port): Bloom Core v1.1 requires a port on every non-title card. See REPORT
    "Standard feedback" (port-less `launch.started_by` services)."""
    if app_id == config.HUB_ID:
        return False
    if card is not None and card.get("kind") != "title" and card.get("port") is None:
        return False
    return True


# -- one app -------------------------------------------------------------
def install_app(console, catalog, app_id, picker, autoload_opt=False, start=False, log=print, progress=None):
    app = catalog.apps[app_id]
    rows = catalog.files_for(app_id)
    log("%s %s: checking %d file%s…" % (app["name"], app["version"], len(rows), "" if len(rows) == 1 else "s"))
    blobs = {r["dest"]: catalog.data(app_id, r) for r in rows}
    ensure_shared(console, app_id, log)

    previous = read_receipt(console, app_id)
    prev_files = {f["dest"]: f for f in (previous or {}).get("files", [])}
    version = app["version"]
    stamp = _stamp()
    entries = []
    for i, row in enumerate(rows, 1):
        dest, data = row["dest"], blobs[row["dest"]]
        decoded = _decoded_on_readback(dest)
        console.makedirs(posixpath.dirname(dest))
        old = prev_files.get(dest)
        backup = old.get("backup") if old else None
        if console.exists(dest):
            if old and old.get("sha256") == row["sha256"]:
                same = decoded or _sha(console.read(dest)) == row["sha256"]
            else:
                same = (not decoded) and _sha(console.read(dest)) == row["sha256"]
            if same:
                entries.append({"dest": dest, "sha256": row["sha256"], "bytes": row["bytes"], "backup": backup})
                if progress:
                    progress(i, len(rows))
                continue
        temp = console.put_verified(dest, data, readback=not decoded)
        if console.exists(dest):
            if old:  # our own older version: keep it for rollback; the original backup stays the restore point
                parked = _park(console, dest, ".omnibloom-old-" + str(previous.get("version", "prev")), stamp)
            else:
                parked = _park(console, dest, ".before-omnibloom-" + version, stamp)
                backup = parked
            log("Kept the previous file as %s" % parked)
        console.rename(temp, dest)
        entries.append({"dest": dest, "sha256": row["sha256"], "bytes": row["bytes"], "backup": backup})
        if progress:
            progress(i, len(rows))
    for dest, old in prev_files.items():   # files an older version had: keep them covered by uninstall
        if dest not in blobs:
            if _jd_tree(dest) and console.exists(dest):   # the engine's folders must hold exactly the new file set
                log("Moved the old engine file %s to %s" % (dest, _park(console, dest, ".omnibloom-old", stamp)))
                continue
            entries.append(old)

    # Payload Manager entry for payloads that live in its folder.
    elf = (app["card"].get("launch") or {}).get("elf")
    if elf and elf.startswith(config.PLDMGR_DIR + "payloads/") and elf in blobs:
        meta = _json_bytes({"name": app["name"], "filename": posixpath.basename(elf), "install_source": "web_upload",
                            "checksum": _sha(blobs[elf]), "version": version})
        _replace(console, elf + ".json", meta, ".prev-" + _stamp())
        entries.append({"dest": elf + ".json", "sha256": _sha(meta), "bytes": len(meta), "backup": None})

    # Port and ID card.
    old_card = (previous or {}).get("card") or {}
    port, note = picker.pick(app_id, app["port"], current=old_card.get("port"))
    if note:
        log(note)
    icon = next((r["dest"] for r in rows if r["dest"].startswith(config.ICONS_DIR)), None)
    card = make_card(app_id, app, port, icon)
    card_bytes = _json_bytes(card)
    if len(card_bytes) > config.CARD_MAX:
        raise IOError("%s's ID card is larger than Bloom Core allows." % app["name"])
    has_card = writes_card(app_id, card)
    if has_card:
        _replace(console, card_path(app_id), card_bytes, ".prev-" + _stamp())

    # Autoload: "required" always, "optional" only when the user ticked it, "never" never.
    al = (previous or {}).get("autoload")
    if elf and (app["autoload"] == "required" or (app["autoload"] == "optional" and autoload_opt)):
        replace = config.REPLACED_CONTROLLER_PAYLOADS if app_id == "master-control" else ()
        change = set_autoload(console, posixpath.basename(elf), True, log, replace=replace)
        if change["changed"] or not al:
            al = change
    if start and elf and elf in blobs:
        console.send_payload(blobs[elf])
        log("Started %s." % app["name"])

    receipt = {
        "schema": RECEIPT_SCHEMA, "id": app_id, "name": app["name"], "version": version,
        "setup_version": config.SETUP_VERSION, "installed_at": _now(), "package": catalog.source[app_id].name,
        "files": entries, "card": card, "card_sha256": _sha(card_bytes) if has_card else None,
        "port": port, "autoload": al,
        "history": ((previous or {}).get("history", []) + [{"version": previous["version"], "installed_at": previous["installed_at"]}]) if previous else [],
    }
    _save_receipt(console, receipt, log)
    log("%s %s is installed%s." % (app["name"], version, (" (port %d)" % port) if port else ""))
    return receipt


def install(console, catalog, app_ids, autoload=(), start=(), log=print, progress=None):
    """Install or update several apps. Bloom Core goes first when the catalog has it.
    autoload/start: app ids the user ticked for "start automatically" / "start now"."""
    wanted = [a for a in app_ids if catalog.has(a) and a != config.HUB_ID]
    missing = [a for a in app_ids if not catalog.has(a)]
    for a in missing:
        log("%s isn't available in this release; skipped." % a)
    order = []
    if catalog.has(config.HUB_ID):
        order.append(config.HUB_ID)
    else:
        log("%s isn't in this release yet. Apps are installed without it (they don't need it to start)." % config.HUB_NAME)
    order += wanted
    picker = PortPicker(console)
    receipts = {}
    for app_id in order:
        hub_start = app_id == config.HUB_ID  # Bloom Core is started right away
        receipts[app_id] = install_app(console, catalog, app_id, picker, autoload_opt=app_id in autoload,
                                       start=hub_start or app_id in start, log=log, progress=progress)
    return receipts


# -- repair ---------------------------------------------------------------
def repair_app(console, catalog, app_id, log=print, progress=None):
    """Re-check an app's files and card, and put back anything missing or changed."""
    receipt = read_receipt(console, app_id)
    if not receipt:
        raise IOError("%s isn't installed on this PS5." % app_id)
    want = {r["dest"]: r for r in catalog.files_for(app_id)} if catalog.has(app_id) else {}
    fixed = []
    files = [f for f in receipt["files"] if f["dest"] in want]
    for i, f in enumerate(files, 1):
        row = want[f["dest"]]
        decoded = _decoded_on_readback(f["dest"])
        ok = console.exists(f["dest"]) and (decoded or _sha(console.read(f["dest"])) == row["sha256"])
        if not ok:
            temp = console.put_verified(f["dest"], catalog.data(app_id, row), readback=not decoded)
            if console.exists(f["dest"]):
                _park(console, f["dest"], ".damaged-" + _stamp())
            console.rename(temp, f["dest"])
            fixed.append(f["dest"])
            log("Repaired %s" % f["dest"])
        if progress:
            progress(i, len(files))
    card_bytes = _json_bytes(receipt["card"]) if receipt.get("card") else None
    current = console.read(card_path(app_id)) if console.exists(card_path(app_id)) else None
    if writes_card(app_id, receipt.get("card")) and card_bytes and (current is None or _sha(current) != receipt.get("card_sha256")):
        _replace(console, card_path(app_id), card_bytes, ".damaged-" + _stamp())
        fixed.append(card_path(app_id))
        log("Repaired %s's ID card" % receipt["name"])
    al = receipt.get("autoload") or {}
    if al.get("changed"):
        set_autoload(console, al["elf"], True, log)
    log("%s: checked %d files, repaired %d." % (receipt["name"], len(files), len(fixed)))
    return fixed


# -- uninstall ------------------------------------------------------------
def uninstall_app(console, app_id, log=print):
    """Remove one app. Its files are renamed aside (never deleted) and earlier files are put back.
    Other apps, their cards and receipts, and the user's own data are left alone."""
    apps = installed_apps(console)
    receipt = apps.get(app_id)
    if not receipt:
        raise IOError("%s isn't installed on this PS5." % app_id)
    if app_id == config.HUB_ID and len(apps) > 1:
        raise IOError("%s is used by your other apps. Uninstall them first." % config.HUB_NAME)
    stamp = _stamp()
    if app_id == config.JD_APP_ID:   # switch JDownloader 2 off before its engine files move
        approval = config.JD_CONSOLE_ROOT + "native-install.json"
        if console.exists(approval):
            console.makedirs(config.JD_BACKUP_DIR + stamp)
            console.rename(approval, config.JD_BACKUP_DIR + stamp + "/native-install.json")
            log("JDownloader 2 is switched off on the PS5.")
    for f in receipt["files"]:
        dest = f["dest"]
        if console.exists(dest):
            _park(console, dest, ".omnibloom-removed-" + stamp, stamp)
        if f.get("backup") and console.exists(f["backup"]):
            console.rename(f["backup"], dest)
            log("Restored your previous %s" % dest)
    al = receipt.get("autoload") or {}
    if al.get("changed"):
        set_autoload(console, al["elf"], False, log)
        if al.get("removed"):
            _restore_autoload_entries(console, al["removed"], log)
    if console.exists(card_path(app_id)):
        console.rename(card_path(app_id), _free_name(console, card_path(app_id), ".removed-" + stamp))
    if console.exists(details_path(app_id)):
        console.rename(details_path(app_id), _free_name(console, details_path(app_id), ".uninstalled-" + stamp))
    console.rename(receipt_path(app_id), _free_name(console, receipt_path(app_id), ".uninstalled-" + stamp))
    log("%s was removed. Your own data was left as it was." % receipt["name"])


# -- updates -------------------------------------------------------------
def update_available(installed_version, latest_version):
    if not installed_version or not latest_version:
        return False
    return version_key(latest_version) > version_key(installed_version)


def updates(console, catalog):
    """{app_id: (installed, latest)} for installed apps with a newer version in the catalog."""
    out = {}
    for app_id, rec in installed_apps(console).items():
        if catalog.has(app_id) and update_available(rec["version"], catalog.apps[app_id]["version"]):
            out[app_id] = (rec["version"], catalog.apps[app_id]["version"])
    return out


# -- Bloom Core's view ------------------------------------------------------
def read_status(console, since=None, want=(), timeout=0.0, sleep=None, clock=None):
    """Bloom Core's /data/hub/status.json (it rewrites it about every 10 s; Setup can't reach its loopback API).
    With `since`/`want`, waits up to `timeout` seconds for a status written after `since` that lists `want`.
    Returns the parsed status, or None if Bloom Core hasn't written one."""
    import time as _t
    sleep = sleep or _t.sleep
    clock = clock or _t.time
    end = clock() + timeout
    last = None
    while True:
        text = console.read_text(config.HUB_DIR + "status.json", default=None)
        try:
            last = json.loads(text) if text else last
        except ValueError:
            pass
        if last and (since is None or last.get("written_at", 0) >= since) and \
                set(want) <= {a.get("id") for a in last.get("apps", [])}:
            return last
        if clock() >= end:
            return last
        sleep(1.0)


def explain_status(status, app_ids=None):
    """Plain-language lines for apps that aren't verified (and cards Bloom Core refused)."""
    if not status:
        return ["%s hasn't reported yet (it writes its status about every 10 seconds)." % config.HUB_NAME]
    lines = []
    for a in status.get("apps", []):
        if app_ids is not None and a.get("id") not in app_ids:
            continue
        if not a.get("verified"):
            lines.append("%s: not verified (%s)." % (a.get("id"), a.get("why") or a.get("status") or "unknown"))
    for bad in status.get("invalid", []):
        lines.append("%s was refused: %s." % (bad.get("file"), bad.get("reason")))
    return lines
