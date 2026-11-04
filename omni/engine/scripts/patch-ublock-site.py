#!/usr/bin/env python3
"""Skip uBlock network filtering for pages on the user's trusted-site list.

Applies after patch-ublock-network.py. The top-level site comes from the
request's first-party URL; update-server protection is still checked first.
"""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/NetworkProcess/NetworkResourceLoader.cpp'
text = path.read_text()
if '// omni ublock trusted sites' not in text:
    anchor = 'extern "C" bool omniUBlockShouldBlock(const char*, const char*, const char*);\n'
    assert text.count(anchor) == 1, 'run patch-ublock-network.py first'
    text = text.replace(anchor, anchor + 'extern "C" bool omniUBlockSiteAllowed(const char*); // omni ublock trusted sites\n', 1)
    anchor = '    const auto& origin = documentURL.isValid() ? documentURL : request.firstPartyForCookies();\n'
    assert text.count(anchor) == 1
    text = text.replace(anchor, '''    if (omniUBlockSiteAllowed(reinterpret_cast<const char*>(request.firstPartyForCookies().host().toString().utf8().data()))) return false;
''' + anchor, 1)
    # Update protection must stay ahead of the trusted-site exemption.
    assert text.index('// omni independent update protection') < text.index('omniUBlockSiteAllowed(reinterpret_cast')
    path.write_text(text)
