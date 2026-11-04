#!/usr/bin/env python3
"""Bound inherited foreground stack defaults without changing explicit stacks."""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WTF/wtf/posix/ThreadingPOSIX.cpp'
text = path.read_text()
if '[omni-default-stack]' not in text:
    anchor = '    case StackAllocationSpecification::Kind::Default:\n        break;'
    assert anchor in text
    text = text.replace(anchor, '''    case StackAllocationSpecification::Kind::Default: {
        // [omni-default-stack] Foreground loader inherits a 2 MiB default.
        // Leave smaller defaults and all explicit WebKit stack requests intact.
        size_t inheritedSize = 0;
        pthread_attr_getstacksize(&attr, &inheritedSize);
        if (inheritedSize > 512 * 1024) {
            int result = pthread_attr_setstacksize(&attr, 512 * 1024);
            if (result) {
                pthread_attr_destroy(&attr);
                return false;
            }
        }
        break;
    }''', 1)
    path.write_text(text)
