#!/usr/bin/env python3
"""Generate omni/pages/bundle-clean4/whatsnew/whatsnew.json (Omni's "What's new" page, OMNI_WHATSNEW_V1) from
CHANGELOG.md's "Unreleased" section, with each feature's button taken from the Controls guide.

Inputs
  --changelog   CHANGELOG.md (default: the repo's). The "## Unreleased ..." section, its "### Omni" bullets only (Setup
                and Downloads are PC / companion-app notes). A bullet runs on over indented lines.
  --controls    the Controls guide table: OmniControlsHelp.h from an engine tree, or the apply_controls_help.py that
                writes it (stage1 tools). Its rows give the button wording ("Hold Cross", "L2 + R3") in PlayStation and
                Xbox names. Required: the buttons must come from the guide, never be typed here.
  --out         the JSON file (default: the bundle's whatsnew/whatsnew.json); --check compares instead of writing
                (exit 1 when out of date).

Feature -> group / guide row / "Try it" action: FEATURES below (first matching pattern wins; a bullet nothing matches
goes to "Browsing" with no button). A FEATURES row naming a guide row the guide no longer has is an error, so a
renamed shortcut can't silently drop its button.

Output (deterministic: same inputs, same bytes; UTF-8, LF, sorted nothing, insertion order kept):
  {"schema": 1, "id": "<16 hex: sha256 of the rest>", "release": "...", "intro": "...",
   "groups": [{"key": "tabs", "title": "Tabs", "items": [
       {"title": "...", "text": "...", "button": {"ps": "...", "xbox": "...", "note": "..."} | null,
        "where": "..." | null, "try": "<action>" | null}]}]}
The engine (apply_whatsnew.py) reads "id" to notice new content; "try" names one of OmniWhatsNew.h's fixed actions.
No network, no clock, no environment: only the two input files.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'omni' / 'pages' / 'bundle-clean4' / 'whatsnew' / 'whatsnew.json'

GROUPS = (('tabs', 'Tabs'), ('video', 'Video'), ('reading', 'Reading'), ('privacy', 'Privacy'),
          ('accessibility', 'Accessibility'), ('controller', 'Controller'), ('keyboard', 'Keyboard'),
          ('browsing', 'Browsing'))
# Must match OmniWhatsNew.h's actionName() list.
ACTIONS = ('controls', 'options', 'settings', 'site-settings', 'tabs', 'history', 'downloads', 'reading-list',
           'bookmarks', 'screenshots')
SECTIONS = {'kBrowsing': 'Browsing', 'kKeyboard': 'Keyboard', 'kTabs': 'Tabs', 'kVideo': 'Video',
            'kQuick': 'Quick actions', 'kReading': 'Reading list', 'kDownloads': 'Downloads', 'kHistory': 'History',
            'kImage': 'Image viewer'}

# (pattern on the bullet's plain text, group, (guide section, guide action) or None, where or None, try or None
#  [, title replacing the bullet's own])
FEATURES = (
    (r'^Pinned tabs', 'tabs', ('Tabs', 'Pin / unpin the tab'), 'Options > Browse > Tabs', 'tabs'),
    (r'^Tab audio', 'tabs', ('Tabs', 'Mute / unmute the tab'), 'Options > Browse > Tabs', 'tabs'),
    (r'^Saved tab sessions', 'tabs', ('Tabs', 'Save these tabs as a session'), 'Options > Browse > Tabs', 'tabs'),
    (r'^Open in background tab', 'tabs', ('Quick actions', 'Open the link in a background tab'), None, None),
    (r'^Zoom per site', 'accessibility', ('Quick actions', 'Zoom this site in / out'), 'Options > Quick toggles', 'options'),
    (r'^Save page for later', 'reading', ('Reading list', 'Save page for later'), 'Options > Browse', 'reading-list'),
    (r'^Page screenshots', 'browsing', ('Quick actions', 'Screenshot'), 'Downloads > Saved > Screenshots', 'screenshots'),
    (r'^Clear data for this site', 'privacy', None, 'Options > Settings > Site settings', 'site-settings'),
    (r'^Autoplay', 'video', None, 'Browser settings', 'settings'),
    (r'^Continue watching', 'video', None, 'Start page', None),
    (r'^YouTube TV mode', 'video', ('Video', "YouTube TV mode: the remote's arrows"), 'Browser settings', 'settings'),
    (r'^HTTPS-only mode', 'privacy', None, 'Browser settings', 'settings'),
    (r'user-agent token', 'privacy', None, 'Browser settings', 'settings', 'Tell sites this is Omni (off)'),
    (r'^Ad block in embedded frames', 'privacy', None, 'Browser settings', 'settings'),
    (r'^"?Now playing', 'video', ('Video', 'Now playing'), 'Options, while a tab plays', 'options'),
    (r'^Sleep timer', 'video', ('Video', 'Sleep timer'), 'Options', 'options'),
    (r'^Keyboard word suggestions', 'keyboard', ('Keyboard', 'Word suggestions'), 'Browser settings', 'settings'),
    (r'^Search shortcuts', 'browsing', None, 'Address bar, start page', None),
    (r'^History', 'browsing', ('History', 'Search'), 'Options > Browse > History', 'history'),
    (r'^Send a link from your phone', 'browsing', None, 'Browser settings', 'settings'),
    (r'^Controller battery', 'controller', None, 'Top bar', None),
    (r'^File downloads', 'browsing', None, 'Options > More > Downloads', 'downloads'),
    (r"^What's new", 'browsing', ('Browsing', 'Options menu'), "Options > Settings > What's new", 'options'),
)
FALLBACK_GROUP = 'browsing'


class GenError(Exception):
    pass


# --- CHANGELOG ---------------------------------------------------------------------------------------------------
def plain(md):
    """Markdown inline -> plain text: **bold**, `code`, [text](link) -> text; whitespace collapsed."""
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', md)
    s = s.replace('**', '').replace('`', '')
    return re.sub(r'\s+', ' ', s).strip()


def unreleased(text):
    """(heading, intro, {subsection: [bullet markdown]}) of the first "## Unreleased" section."""
    lines = text.replace('\r\n', '\n').split('\n')
    start = next((i for i, l in enumerate(lines) if l.startswith('## ') and 'unreleased' in l.lower()), None)
    if start is None:
        raise GenError('CHANGELOG: no "## Unreleased" section')
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('## ')), len(lines))
    heading = lines[start][3:].strip()
    intro, subs, cur, bullet = [], {}, None, None
    for l in lines[start + 1:end]:
        if l.startswith('### '):
            cur, bullet = l[4:].strip(), None
            subs.setdefault(cur, [])
        elif cur is None:
            if l.strip():
                intro.append(l.strip())
        elif l.startswith('- '):
            subs[cur].append(l[2:])
            bullet = True
        elif bullet and l.startswith('  ') and l.strip():
            subs[cur][-1] += ' ' + l.strip()
        elif not l.strip():
            bullet = None
    return heading, ' '.join(intro), subs


def md_plain(md):
    """The bullet's whole plain text (FEATURES patterns match this, before the title is cut off the front)."""
    return plain(md)


def split_title(md):
    """A bullet's title (its first **bold** run, else the text up to the first ':' or '.') and its plain text."""
    text = plain(md)
    m = re.search(r'\*\*(.+?)\*\*', md)
    if m:
        title = plain(m.group(1))
    else:
        title = re.split(r'[:.]', text, maxsplit=1)[0].strip()
        if len(title) > 60:
            title = title[:57].rstrip() + '...'
    title = title.rstrip(':').strip().strip('"').strip()
    if text.startswith(title + ':'):          # "Pinned tabs: D-pad ..." -> "D-pad ..."
        text = text[len(title) + 1:].strip()
        if not text[1:2].isupper():           # keep "uBlock", "iOS"
            text = text[:1].upper() + text[1:]
    return title, text


# --- Controls guide -------------------------------------------------------------------------------------------------
_ROW = re.compile(r'\{\s*(k[A-Za-z]+)\s*,\s*\{([^}]*)\}\s*,\s*(0|\'[+/]\')\s*,\s*(true|false)\s*,\s*'
                  r'"((?:\\.|[^"\\])*)"\s*,\s*"((?:\\.|[^"\\])*)"\s*,\s*"((?:\\.|[^"\\])*)"\s*\}')
_GLYPH = re.compile(r'case\s+(g[A-Za-z0-9]+)\s*:\s*return\s+(?:ps\s*\?\s*"([^"]*)"\s*:\s*"([^"]*)"|"([^"]*)")\s*;')


def guide(text):
    """(rows, glyph names) from OmniControlsHelp.h / apply_controls_help.py."""
    a = text.find('table()')
    b = text.find('return t;', a)
    if a < 0 or b < 0:
        raise GenError('Controls guide: table() not found')
    rows = []
    for m in _ROW.finditer(text, a, b):
        sec, keys, join, hold, action, note = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        if sec not in SECTIONS:
            raise GenError('Controls guide: unknown section ' + sec)
        rows.append({'section': SECTIONS[sec], 'keys': [k.strip() for k in keys.split(',') if k.strip()],
                     'join': join.strip("'") if join != '0' else '', 'hold': hold == 'true',
                     'action': action.replace('\\"', '"'), 'note': note.replace('\\"', '"')})
    g = text.find('glyphName(')
    names = {}
    if g >= 0:
        for m in _GLYPH.finditer(text, g, text.find('\n}', g)):
            names[m.group(1)] = (m.group(2), m.group(3)) if m.group(4) is None else (m.group(4), m.group(4))
    if not rows or 'gCross' not in names:
        raise GenError('Controls guide: no rows or glyph names found')
    return rows, names


def tokens(s, ps, names):
    """{Cross} -> Cross / A (the guide's text tokens)."""
    def one(m):
        g = 'g' + m.group(1)
        return names[g][0 if ps else 1] if g in names else m.group(0)
    return re.sub(r'\{([A-Za-z0-9]+)\}', one, s)


def button(row, names):
    out = {}
    for kind, ps in (('ps', True), ('xbox', False)):
        parts = []
        for k in row['keys']:
            if k not in names:
                raise GenError('Controls guide: no name for glyph ' + k)
            parts.append(names[k][0 if ps else 1])
        sep = ' + ' if row['join'] == '+' else ' / ' if row['join'] == '/' else ' '
        out[kind] = ('Hold ' if row['hold'] else '') + sep.join(parts)
    out['note'] = tokens(row['note'], True, names)
    out['noteXbox'] = tokens(row['note'], False, names)
    return out


# --- build ----------------------------------------------------------------------------------------------------------
def build(changelog_text, controls_text):
    heading, intro, subs = unreleased(changelog_text)
    bullets = subs.get('Omni')
    if not bullets:
        raise GenError('CHANGELOG: no "### Omni" bullets under ' + heading)
    rows, names = guide(controls_text)
    for pat, grp, ref, _where, act, *_title in FEATURES:
        if grp not in dict(GROUPS):
            raise GenError('FEATURES: unknown group ' + grp)
        if act is not None and act not in ACTIONS:
            raise GenError('FEATURES: unknown action ' + act)
        if ref and not any(r['section'] == ref[0] and r['action'] == ref[1] for r in rows):
            raise GenError('Controls guide has no row %s > %s (FEATURES %r)' % (ref[0], ref[1], pat))
    groups = {k: [] for k, _ in GROUPS}
    for md in bullets:
        title, text = split_title(md)
        item = {'title': title, 'text': text, 'button': None, 'where': None, 'try': None}
        grp = FALLBACK_GROUP
        for pat, g, ref, where, act, *rename in FEATURES:
            if re.search(pat, md_plain(md)):
                grp = g
                if rename:
                    item['title'] = rename[0]
                if ref:
                    row = next(r for r in rows if r['section'] == ref[0] and r['action'] == ref[1])
                    item['button'] = button(row, names)
                item['where'], item['try'] = where, act
                break
        groups[grp].append(item)
    body = {'release': heading, 'intro': intro,
            'groups': [{'key': k, 'title': t, 'items': groups[k]} for k, t in GROUPS if groups[k]]}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    out = {'schema': 1, 'id': digest.hexdigest()[:16]}
    out.update(body)
    return json.dumps(out, ensure_ascii=False, indent=1) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--changelog', type=Path, default=ROOT / 'CHANGELOG.md')
    ap.add_argument('--controls', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args(argv)
    try:
        data = build(a.changelog.read_text(encoding='utf-8'), a.controls.read_text(encoding='utf-8'))
    except (GenError, OSError) as e:
        print('gen_whatsnew: ' + str(e), file=sys.stderr)
        return 2
    raw = data.encode('utf-8')
    if a.check:
        same = a.out.is_file() and a.out.read_bytes() == raw
        print(('up to date: ' if same else 'OUT OF DATE: ') + str(a.out))
        return 0 if same else 1
    if a.out.is_file() and a.out.read_bytes() == raw:
        print('unchanged: ' + str(a.out))
        return 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(raw)
    print('written: %s (%d bytes)' % (a.out, len(raw)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
