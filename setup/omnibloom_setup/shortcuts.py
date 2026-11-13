"""Omni's controller shortcuts: one list for Setup's window and its command line.

Each row: (PlayStation button, Xbox button or "-", what it does). The README's "Controller shortcuts" tables carry
the same rows; tests/test_shortcuts.py fails if the two drift apart.
"""

SECTIONS = (
    ("Browsing", (
        ("Left stick", "-", "Move the pointer (it snaps to the nearest link)"),
        ("Right stick", "-", "Scroll in any direction"),
        ("Cross", "A", "Click. Hold for half a second: the right-click menu"),
        ("Circle", "B", "Go back"),
        ("Square", "X", "New tab"),
        ("Triangle", "Y", "Address bar"),
        ("L1 / R1", "LB / RB", "Previous / next tab"),
        ("L1 + R1 together", "LB + RB", "Media downloads"),
        ("L2", "LT", "Saved links"),
        ("R2", "RT", "Send this page's media link to Media downloads"),
        ("L3", "press left stick", "Save this site to your shortcuts"),
        ("R3", "press right stick", "Close tab"),
        ("D-pad up / down", "-", "Scroll"),
        ("D-pad left / right", "-", "Back / forward (or switch tabs, in Settings)"),
        ("Touchpad", "-", "Translate the page"),
        ("Options", "Menu", "Quick menu: Browse, Quick toggles, Apps, Settings, More (Exit is in it)"),
        ("Create", "View", "Settings (on an Xbox controller View may not reach Omni: use LT + B, in the next version)"),
    )),
    ("Typing (on-screen keyboard)", (
        ("L1 / R1", "LB / RB", "Move the cursor"),
        ("L2 / R2", "LT / RT", "Move the cursor a whole word"),
        ("Square", "X", "Delete"),
        ("Triangle", "Y", "Space"),
        ("L3", "press left stick", "Shift"),
        ("R3", "press right stick", "Symbols"),
        ("Touchpad", "-", "Edit row: copy, cut, paste, undo, select all, Fill saved login, Fill form"),
        ("Options", "Menu", "Go"),
    )),
    ("Fullscreen video", (
        ("Square", "X", "Pause / play"),
        ("L1 / R1", "LB / RB", "Back / forward 10 seconds"),
        ("Triangle", "Y", "Captions"),
        ("L3", "press left stick", "Mute"),
        ("Circle", "B", "Leave fullscreen"),
    )),
)

COMING = ("Coming in the next version", (
    ("L2 + Square", "LT + X", "Copy: the selected text, else the link under the pointer, else the page address"),
    ("L2 + Triangle", "LT + Y", "Paste into the selected text box"),
    ("L2 + Cross", "LT + A", "Quick bar"),
    ("L2 + Circle", "LT + B", "Browser settings"),
))

# Shown on Setup's "All set" page: the ones people ask about first.
KEY = (
    ("L1 + R1 together", "LB + RB", "Media downloads"),
    ("Options", "Menu", "Quick menu (Exit is in it)"),
    ("Cross, held", "A, held", "Right-click menu"),
    ("Triangle", "Y", "Address bar"),
)


def label(ps, xbox):
    return ps if xbox == "-" else "%s (%s)" % (ps, xbox)


def text():
    """The whole list as plain text (command line, Setup's "All controller shortcuts" window)."""
    out = ["Omni controller shortcuts. PlayStation names first, Xbox names in brackets.", ""]
    for title, rows in SECTIONS + (COMING,):
        out.append(title)
        width = max(len(label(p, x)) for p, x, _ in rows)
        for p, x, what in rows:
            out.append("  %-*s  %s" % (width, label(p, x), what))
        out.append("")
    out.append("Also on the web: https://github.com/egomortal/omnibloom#controller-shortcuts")
    return "\n".join(out) + "\n"
