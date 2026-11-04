#!/usr/bin/env python3
"""Complete PlayStation view resizing and fullscreen state tracking."""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/UIProcess/playstation/PlayStationWebView.cpp'
text = path.read_text()
old = '''    m_viewSize = viewSize;
}'''
new = '''    m_viewSize = viewSize;
    // Omni: notify the live page when the shell viewport changes.
    if (auto* area = m_page->drawingArea())
        area->setSize(viewSize);
}'''
if old in text:
    text = text.replace(old, new, 1)
old = '''    if (m_client && !isFullScreen())
        m_client->enterFullScreen(*this, WTF::move(completionHandler));
    else
        completionHandler(false);'''
new = '''    if (m_client && !isFullScreen()) {
        // Omni: the current fullscreen manager does not call the old willEnter hook.
        m_isFullScreen = true;
        m_client->enterFullScreen(*this, [this, protectedThis = Ref { *this }, completionHandler = WTF::move(completionHandler)](bool entered) mutable {
            if (!entered)
                m_isFullScreen = false;
            completionHandler(entered);
        });
    } else
        completionHandler(false);'''
if old in text:
    text = text.replace(old, new, 1)
if path.read_text() != text:
    path.write_text(text)
