#!/usr/bin/env python3
"""Preserve text supplied to the PlayStation native keyboard API."""
import pathlib
import sys
p = pathlib.Path(sys.argv[1]) / 'Source/WebKit/UIProcess/API/C/playstation/WKPagePrivatePlayStation.cpp'
s = p.read_text()
if '[omni-keyboard-text]' not in s:
    anchor = 'NativeWebKeyboardEvent::create(&wpeEvent, ""_s, false,'
    assert anchor in s
    s = s.replace(anchor, 'NativeWebKeyboardEvent::create(&wpeEvent, event.text && event.length > 0 ? String::fromUTF8(std::span(event.text, static_cast<size_t>(event.length))) : String(), false,', 1)
    s += '\n// [omni-keyboard-text] Preserve typed text; null text uses backend key mapping.\n'
    p.write_text(s)
