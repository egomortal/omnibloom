# SPDX-License-Identifier: GPL-3.0-or-later
"""Where finished downloads go (OMNI_DL_SAVE_V1, Downloads 0.5.4).

The GUI picks a place by id ("internal", "usb0".."usb7") and may add a folder name and a file name. It never sends a
path: the paths are built here, from fixed roots, and every name is checked. A USB drive counts only while it is
mounted (os.path.ismount): when a drive is pulled, /mnt/usbN stays behind as an empty folder on the console's own
storage, and writing there would silently fill the system drive.

Layout: console storage -> <downloads folder>/Saved/[folder]/<file>; USB drive N -> /mnt/usbN/Omni Downloads/[folder]/<file>.
A download for a USB drive is also written there while it runs (a hidden ".omni-work" folder next to it), so a
big file never has to fit on the console first, and the final move is a rename on the same drive.
"""
import os
import re
import shutil
from pathlib import Path

USB_ROOTS = tuple('/mnt/usb%d' % i for i in range(8))
USB_FOLDER = 'Omni Downloads'
INTERNAL_FOLDER = 'Saved'
WORK_FOLDER = '.omni-work'
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._()\-]{0,79}\Z')
_PLACE = re.compile(r'internal|usb[0-7]\Z')
# Room kept free on top of the file itself, so a download never takes a drive to zero.
MARGIN = 64 * 1024 * 1024


def clean_name(value, what):
    """None/'' -> None; otherwise a plain name: letters, digits, space . _ - ( ), up to 80, not hidden."""
    if value is None or value == '':
        return None
    if not isinstance(value, str) or not _NAME.fullmatch(value) or '..' in value or value.endswith(('.', ' ')):
        raise ValueError(what + ' may use letters, digits, spaces and . _ - ( ) (up to 80 characters); '
                         'it cannot start with a dot or end with a dot or a space.')
    return value


def check_place(place):
    if place is None:
        return 'internal'
    if not isinstance(place, str) or not _PLACE.fullmatch(place):
        raise ValueError('Unknown save place.')
    return place


def mounted(root):
    try:
        return os.path.ismount(root)
    except OSError:
        return False


def usage(path):
    try:
        u = shutil.disk_usage(path)
        return u.free, u.total
    except OSError:
        return None, None


def places(internal, usb_roots=USB_ROOTS):
    """The places the GUI may offer, with free and total bytes."""
    out = []
    free, total = usage(internal)
    out.append(dict(id='internal', label='Console storage', free_bytes=free, total_bytes=total))
    for index, root in enumerate(usb_roots):
        if mounted(root):
            free, total = usage(root)
            if free is not None:
                out.append(dict(id='usb%d' % index, label='USB drive %d' % (index + 1), free_bytes=free, total_bytes=total))
    return out


def base_for(place, internal, usb_roots=USB_ROOTS):
    """The folder a place saves into; for a USB drive, refused when it is not mounted."""
    place = check_place(place)
    if place == 'internal':
        return Path(internal) / INTERNAL_FOLDER
    root = usb_roots[int(place[3])]
    if not mounted(root):
        raise ValueError('USB drive %d is not connected.' % (int(place[3]) + 1))
    return Path(root) / USB_FOLDER


def still_there(place, usb_roots=USB_ROOTS):
    """False once a chosen USB drive has been pulled (checked while the download runs)."""
    place = check_place(place)
    return place == 'internal' or mounted(usb_roots[int(place[3])])


def work_folder(place, internal, key, usb_roots=USB_ROOTS):
    """Where a job writes while it runs: the job folder on console storage, or a hidden folder on the USB drive."""
    if check_place(place) == 'internal':
        return Path(internal) / key
    return base_for(place, internal, usb_roots) / WORK_FOLDER / key


def _no_links(path, base):
    """Refuse a destination reached through a symbolic link, from `path` up to and including `base`."""
    part = path
    while True:
        if part.is_symlink():
            raise ValueError('The save folder must not be a symbolic link.')
        if part == base or part == part.parent:
            return
        part = part.parent


def final_name(src):
    """'Title [id].f137.mp4' / 'Title [id].merged.mkv' -> ('Title [id]', '.mkv')."""
    name = Path(src).name
    stem, ext = os.path.splitext(name)
    for tail in ('.merged',):
        if stem.endswith(tail):
            stem = stem[:-len(tail)]
    stem = re.sub(r'\.f[0-9A-Za-z_-]{1,24}$', '', stem)
    return stem or 'download', ext.lower()


def publish(src, place, internal, folder=None, filename=None, usb_roots=USB_ROOTS):
    """Move a finished file to its place under a free name ('Name (2).mp4' when 'Name.mp4' exists). Never overwrites.
    Same drive: a rename. Another drive (a JDownloader file for a USB place): copy to a hidden part file, then rename."""
    src = Path(src)
    if not src.is_file() or src.is_symlink():
        raise ValueError('The finished file is missing.')
    base = base_for(place, internal, usb_roots)
    folder = clean_name(folder, 'The folder name')
    filename = clean_name(filename, 'The file name')
    target_dir = base / folder if folder else base
    target_dir.mkdir(parents=True, exist_ok=True)
    _no_links(target_dir, base)
    stem, ext = final_name(src)
    if filename:
        stem = filename[:-len(ext)] if ext and filename.lower().endswith(ext) else filename
    for n in range(1, 1000):
        candidate = target_dir / ((stem if n == 1 else '%s (%d)' % (stem, n)) + ext)
        if not candidate.exists():
            break
    else:
        raise ValueError('Too many files with this name in the save folder.')
    if not still_there(place, usb_roots):
        raise ValueError('The USB drive was disconnected before the file could be saved.')
    try:
        same_drive = os.stat(src).st_dev == os.stat(target_dir).st_dev
    except OSError:
        same_drive = False
    if same_drive:
        os.rename(src, candidate)
    else:
        part = target_dir / ('.' + candidate.name + '.omni-part')
        try:
            shutil.copyfile(src, part)
            if candidate.exists():
                raise ValueError('A file with this name appeared while saving.')
            os.rename(part, candidate)
        finally:
            if part.exists():
                part.unlink()
        src.unlink()
    return candidate
