#!/usr/bin/env python3
"""Honor explicit page user agents before PlayStation's unconditional fallback."""
import pathlib
import sys
p = pathlib.Path(sys.argv[1]) / 'Source/WebKit/WebProcess/WebPage/playstation/WebPagePlayStation.cpp'
s = p.read_text()
if '[omni-custom-user-agent]' not in s:
    anchor = '    if (url.isNull() || !m_page->settings().needsSiteSpecificQuirks())'
    assert anchor in s
    s = s.replace(anchor, '    // [omni-custom-user-agent] Explicit app configuration takes precedence.\n    if (m_hasCustomUserAgent || url.isNull() || !m_page->settings().needsSiteSpecificQuirks())', 1)
    p.write_text(s)
