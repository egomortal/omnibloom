#!/usr/bin/env python3
"""Bounded font diagnostics for comparing interactive and offscreen rendering."""
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
path = root / 'Source/WebCore/platform/graphics/skia/FontCacheSkia.cpp'
text = path.read_text()
if '[omni-font-diagnostic]' not in text:
    anchor = '    RELEASE_ASSERT(m_fontManager);'
    assert anchor in text
    text = text.replace(anchor, anchor + '''
    // [omni-font-diagnostic]
    static int reports = 0;
    if (reports++ < 4) fprintf(stderr, "omni font manager: families=%d config=%s\\n", m_fontManager->countFamilies(), getenv("FONTCONFIG_FILE"));''', 1)
    anchor = '        typeface = SkTypeface::MakeEmpty();'
    assert anchor in text
    text = text.replace(anchor, '        fprintf(stderr, "omni font: empty last-resort fallback\\n");\n' + anchor, 1)
    path.write_text(text)
