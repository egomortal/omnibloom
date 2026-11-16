#!/usr/bin/env python3
"""OMNI_BOOKMARKS_MANAGER_V1: the Setup side of the bookmarks.txt round trip (setup/omnibloom_setup/bookmarks.py).

  test_bookmarks_manager_ref.py <setup dir> gen <out>
      A Chromium "Bookmarks" file with nested folders, read by the Setup's own reader (read_chromium), cleaned by
      collect() and written by merge() onto an empty console file: the bytes the Setup would put on the console.
  test_bookmarks_manager_ref.py <setup dir> append <omni file> <out>
      Reads a bookmarks.txt written by the new Omni (with folder columns) the way the Setup reads it (omni_entries),
      prints what it saw, and appends a second PC import onto it with merge() (one address already there, two new).
Synthetic data only (example.* addresses).
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, sys.argv[1])
from omnibloom_setup import bookmarks as B  # noqa: E402


def chromium(nodes_bar, nodes_other):
    return {"roots": {"bookmark_bar": {"type": "folder", "children": nodes_bar},
                      "other": {"type": "folder", "children": nodes_other}}}


def url(name, address):
    return {"type": "url", "name": name, "url": address}


def folder(name, children):
    return {"type": "folder", "name": name, "children": children}


def read(doc):
    d = tempfile.mkdtemp(prefix="bmref-")
    p = os.path.join(d, "Bookmarks")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    try:
        src = B.Source("Chrome", "Default", p, "chromium")
        return B.collect([src])
    finally:
        os.remove(p)
        os.rmdir(d)


def main():
    mode = sys.argv[2]
    if mode == "gen":
        doc = chromium(
            [url("Example News", "https://news.example.com/"),
             folder("Work", [url("Docs\tTabbed  title", "https://docs.example.com/a?b=1#c"),
                             folder("Deep", [url("Café – résumé", "HTTPS://example.org/caf%C3%A9")])]),
             url("", "http://untitled.example.net"),
             url("Not web", "ftp://files.example.com/"),
             url("Dupe", "https://news.example.com/")],
            [url("Other one", "https://other.example.com:8443/path"),
             url("Long " + "x" * 400, "https://long.example.com/")])
        items = read(doc)
        data, added, already, no_room = B.merge(b"", items)
        with open(sys.argv[3], "wb") as f:
            f.write(data)
        print("gen: %d added, %d already, %d no room, %d entries" % (added, already, no_room, len(B.omni_entries(data))))
    elif mode == "append":
        with open(sys.argv[3], "rb") as f:
            existing = f.read()
        entries = B.omni_entries(existing)
        print("setup reads %d entries" % len(entries))
        for u, t in entries:
            print("  %s | %s" % (u.decode("utf-8"), t.decode("utf-8").replace("\t", "<TAB>")))
        more = read(chromium([url("Example News again", "https://news.example.com/"),
                              url("New A", "https://new-a.example.com/"),
                              folder("PC folder", [url("New B", "https://new-b.example.com/")])], []))
        data, added, already, no_room = B.merge(existing, more)
        assert data.startswith(existing), "Setup must keep the existing bytes"
        with open(sys.argv[4], "wb") as f:
            f.write(data)
        print("append: %d added, %d already, %d no room" % (added, already, no_room))
    else:
        sys.exit("mode: gen | append")


main()
