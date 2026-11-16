#!/usr/bin/env python3
"""Tests for tools/gen_whatsnew.py (OMNI_WHATSNEW_V1). python -m unittest tools/test_gen_whatsnew.py"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_whatsnew as G  # noqa: E402

GUIDE = r'''
inline const std::vector<Entry>& table()
{
    static const std::vector<Entry> t = {
    { kTabs, { gDpadH }, 0, false, "Pin / unpin the tab", "Not for private tabs", "omniPtTabsInput" },
    { kTabs, { gTriangle }, 0, false, "Mute / unmute the tab", "", "x" },
    { kTabs, { gCross }, 0, false, "Save these tabs as a session", "The row below the tabs", "x" },
    { kQuick, { gCross }, 0, true, "Open the link in a background tab", "Then {Cross}: the link menu's first row ({R1} shows it)", "x" },
    { kQuick, { gL2, gDpadV }, '+', false, "Zoom this site in / out", "Remembered for the site", "x" },
    { kQuick, { gL2, gR3 }, '+', false, "Screenshot", "Downloads", "x" },
    { kReading, { gOptions }, 0, false, "Save page for later", "Options > Browse, or the page menu (hold {Cross})", "x" },
    { kVideo, { gDpad }, 0, false, "YouTube TV mode: the remote's arrows", "{Cross} is Enter", "x" },
    { kVideo, { gOptions }, 0, false, "Now playing", "", "x" },
    { kVideo, { gOptions }, 0, false, "Sleep timer", "", "x" },
    { kKeyboard, { gDpadUp }, 0, false, "Word suggestions", "", "x" },
    { kHistory, { gTriangle }, 0, false, "Search", "", "x" },
    { kBrowsing, { gOptions }, 0, false, "Options menu", "{Options} again closes it", "x" },
    { kImage, { gL2, gR2 }, '/', false, "Zoom out / in", "Hold for more", "x" },
    };
    return t;
}
inline const char* glyphName(int g, bool ps)
{
    switch (g) {
    case gCross: return ps ? "Cross" : "A";
    case gTriangle: return ps ? "Triangle" : "Y";
    case gR1: return ps ? "R1" : "RB";
    case gL2: return ps ? "L2" : "LT";
    case gR2: return ps ? "R2" : "RT";
    case gR3: return ps ? "R3" : "RS";
    case gOptions: return ps ? "Options" : "Menu";
    case gDpad: return "D-pad";
    case gDpadV: return "D-pad up / down";
    case gDpadH: return "D-pad left / right";
    case gDpadUp: return "D-pad up";
    }
    return "";
}
'''

CHANGELOG = '''# Changelog\r
\r
## Unreleased (dev branch)\r
\r
Intro line one\r
and two.\r
\r
### Omni\r
- **Pinned tabs:** D-pad left / right on a tab row. Up to\r
  6; kept after a restart.\r
- **Open in background tab** is now the first row.\r
- **Zoom per site** (50-200%): L2 + D-pad up / down.\r
- The " Omni/<version>" user-agent token is off by default.\r
- **Ad block in embedded frames:** uBlock's fixes run in frames.\r
- **Something unknown** that no pattern matches.\r
- **"Now playing"** controls in the Options menu.\r
\r
### Setup\r
- **Back up** settings.\r
\r
## v0.5.3\r
### Omni\r
- **Old feature** must not appear.\r
'''


class GenTest(unittest.TestCase):
    def data(self, changelog=CHANGELOG, guide=GUIDE):
        return json.loads(G.build(changelog, guide))

    def items(self, d):
        return {i['title']: (g['key'], i) for g in d['groups'] for i in g['items']}

    def test_deterministic(self):
        a, b = G.build(CHANGELOG, GUIDE), G.build(CHANGELOG.replace('\r\n', '\n'), GUIDE)
        self.assertEqual(a, b)
        self.assertTrue(a.endswith('\n') and '\r' not in a)
        d = json.loads(a)
        self.assertEqual(list(d)[:2], ['schema', 'id'])
        self.assertRegex(d['id'], r'^[0-9a-f]{16}$')

    def test_id_follows_content(self):
        other = G.build(CHANGELOG.replace('Up to', 'At most'), GUIDE)
        self.assertNotEqual(json.loads(other)['id'], self.data()['id'])

    def test_section_and_bullets(self):
        d = self.data()
        self.assertEqual(d['release'], 'Unreleased (dev branch)')
        self.assertEqual(d['intro'], 'Intro line one and two.')
        it = self.items(d)
        self.assertNotIn('Old feature', it)
        self.assertNotIn('Back up', it)
        self.assertEqual(it['Pinned tabs'][1]['text'], 'D-pad left / right on a tab row. Up to 6; kept after a restart.')
        self.assertEqual(it['Open in background tab'][1]['text'], 'Open in background tab is now the first row.')
        self.assertTrue(it['Ad block in embedded frames'][1]['text'].startswith("uBlock's"))
        self.assertIn('Now playing', it)                  # quotes stripped from the title

    def test_groups_buttons_try(self):
        it = self.items(self.data())
        key, pin = it['Pinned tabs']
        self.assertEqual(key, 'tabs')
        self.assertEqual(pin['button']['ps'], 'D-pad left / right')
        self.assertEqual(pin['try'], 'tabs')
        bg = it['Open in background tab'][1]['button']
        self.assertEqual((bg['ps'], bg['xbox']), ('Hold Cross', 'Hold A'))
        self.assertEqual(bg['note'], "Then Cross: the link menu's first row (R1 shows it)")
        self.assertEqual(bg['noteXbox'], "Then A: the link menu's first row (RB shows it)")
        zoom = it['Zoom per site']
        self.assertEqual(zoom[0], 'accessibility')
        self.assertEqual((zoom[1]['button']['ps'], zoom[1]['button']['xbox']), ('L2 + D-pad up / down', 'LT + D-pad up / down'))
        self.assertEqual(it['Tell sites this is Omni (off)'][0], 'privacy')
        unknown = it['Something unknown']
        self.assertEqual(unknown[0], G.FALLBACK_GROUP)
        self.assertIsNone(unknown[1]['button'])
        self.assertIsNone(unknown[1]['try'])
        order = [g['key'] for g in self.data()['groups']]
        self.assertEqual(order, [k for k, _ in G.GROUPS if k in order])
        self.assertNotIn('keyboard', order)               # empty groups are left out

    def test_guide_join_slash(self):
        rows, names = G.guide(GUIDE)
        r = next(r for r in rows if r['action'] == 'Zoom out / in')
        self.assertEqual(G.button(r, names)['xbox'], 'LT / RT')

    def test_errors(self):
        with self.assertRaises(G.GenError):
            G.build('# Changelog\n## v1\n', GUIDE)
        with self.assertRaises(G.GenError):
            G.build('## Unreleased\n### Setup\n- **x**\n', GUIDE)
        with self.assertRaises(G.GenError):     # a FEATURES row whose guide row is gone
            G.build(CHANGELOG, GUIDE.replace('"Pin / unpin the tab"', '"Pin the tab"'))
        with self.assertRaises(G.GenError):
            G.build(CHANGELOG, 'nothing here')

    def test_actions_match_engine(self):
        h = Path(__file__).resolve().parents[1] / 'omni' / 'pages' / 'bundle-clean4' / 'whatsnew' / 'whatsnew.js'
        self.assertTrue(h.is_file())
        for _p, _g, _r, _w, act, *_ in G.FEATURES:
            self.assertTrue(act is None or act in G.ACTIONS, act)

    def test_cli_check_and_write(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'CHANGELOG.md').write_text(CHANGELOG, encoding='utf-8', newline='')
            (t / 'guide.h').write_text(GUIDE, encoding='utf-8')
            out = t / 'w' / 'whatsnew.json'
            args = ['--changelog', str(t / 'CHANGELOG.md'), '--controls', str(t / 'guide.h'), '--out', str(out)]
            self.assertEqual(G.main(args + ['--check']), 1)
            self.assertEqual(G.main(args), 0)
            first = out.read_bytes()
            self.assertEqual(G.main(args + ['--check']), 0)
            self.assertEqual(G.main(args), 0)
            self.assertEqual(out.read_bytes(), first)
            self.assertEqual(G.main(['--changelog', str(t / 'missing.md'), '--controls', str(t / 'guide.h'), '--out', str(out)]), 2)


if __name__ == '__main__':
    unittest.main()
