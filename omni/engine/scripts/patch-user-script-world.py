#!/usr/bin/env python3
"""C API for user scripts in a named isolated content world.

uBlock's cosmetic filtering and ISOLATED-world scriptlets run outside the
page's JavaScript world, as they do in browser extensions. The public C API
only offers the page world, so Omni adds one extern "C" entry point.
"""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/UIProcess/API/C/WKUserScriptRef.cpp'
text = path.read_text()
if '[omni-user-script-world]' not in text:
    anchor = 'WKStringRef WKUserScriptCopySource(WKUserScriptRef userScriptRef)\n'
    assert text.count(anchor) == 1
    assert '#include "APIContentWorld.h"' in text or 'API::ContentWorld::pageContentWorldSingleton()' in text
    text = text.replace(anchor, '''// [omni-user-script-world]
extern "C" WKUserScriptRef WKUserScriptCreateWithSourceInWorldOmni(WKStringRef sourceRef, _WKUserScriptInjectionTime injectionTime, bool forMainFrameOnly, WKStringRef worldName)
{
    return toAPILeakingRef(API::UserScript::create(WebCore::UserScript { toWTFString(sourceRef), { }, { }, { }, toUserScriptInjectionTime(injectionTime), forMainFrameOnly ? WebCore::UserContentInjectedFrames::InjectInTopFrameOnly : WebCore::UserContentInjectedFrames::InjectInAllFrames }, API::ContentWorld::sharedWorldWithName(toWTFString(worldName))));
}

''' + anchor, 1)
    if '#include "APIContentWorld.h"' not in text:
        text = text.replace('#include "APIUserScript.h"\n', '#include "APIContentWorld.h"\n#include "APIUserScript.h"\n', 1)
    path.write_text(text)
