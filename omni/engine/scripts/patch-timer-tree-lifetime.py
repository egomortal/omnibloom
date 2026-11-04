#!/usr/bin/env python3
"""Detach removed intrusive tree nodes while their former children are alive."""
import pathlib
import sys

path = pathlib.Path(sys.argv[1]) / 'Source/WTF/wtf/RedBlackTree.h'
text = path.read_text()
marker = '// Omni: removed nodes must not retain checked links into the tree.'
if marker not in text:
    anchor = '        return z;\n    }\n'
    if text.count(anchor) != 1:
        raise SystemExit('Unexpected RedBlackTree removal implementation; inspect before patching')
    text = text.replace(anchor, '''        // Omni: removed nodes must not retain checked links into the tree.
        // Former children may be destroyed before this node is reused/destroyed.
        // Rebalancing above is finished; dropping these links is now safe.
        z->reset();
        return z;
    }
''')
    path.write_text(text)
