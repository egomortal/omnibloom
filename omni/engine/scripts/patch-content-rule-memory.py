#!/usr/bin/env python3
"""Supply the Curl port's missing shared-memory copy for content-rule IPC."""
import pathlib
import sys
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/NetworkProcess/cache/NetworkCacheDataCurl.cpp'
text = path.read_text()
if '[omni-content-rule-memory]' not in text:
    anchor = '#if ENABLE(SHAREABLE_RESOURCE) && OS(WINDOWS)'
    assert anchor in text
    text = text.replace(anchor, '''// [omni-content-rule-memory] Curl's mapped-file wrapper does not retain a POSIX fd.
#if PLATFORM(PLAYSTATION)
RefPtr<WebCore::SharedMemory> Data::tryCreateSharedMemory() const
{
    if (isNull() || !isMap() || !size())
        return nullptr;
    auto memory = WebCore::SharedMemory::allocate(size());
    if (memory)
        memcpySpan(memory->mutableSpan(), span());
    return memory;
}
#endif

''' + anchor, 1)
    path.write_text(text)

# Compiler errors have a different category from store errors. The C API must
# return a compile failure instead of asserting on an unfamiliar error value.
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/UIProcess/API/C/WKUserContentExtensionStoreRef.cpp'
text = path.read_text()
if '[omni-rule-error]' not in text:
    anchor = '    RELEASE_ASSERT_NOT_REACHED();'
    assert anchor in text
    text = text.replace(anchor, '    return kWKUserContentExtensionStoreCompileFailed; // [omni-rule-error]', 1)
    path.write_text(text)
