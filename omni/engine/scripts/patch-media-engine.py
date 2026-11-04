#!/usr/bin/env python3
"""Register the experimental Omni media backend with explicit engine identities."""
import pathlib
import sys
root = pathlib.Path(sys.argv[1]) / 'Source/WebCore/platform/graphics'
for name, anchor in [('MediaPlayerEnums.h', 'enum class MediaPlayerMediaEngineIdentifier : uint8_t {'), ('MediaPlayer.h', 'enum class MediaPlayerType {')]:
    path = root / name
    text = path.read_text()
    if anchor + '\n    OmniFFmpeg,' not in text:
        assert text.count(anchor) == 1
        text = text.replace(anchor, anchor + '\n    OmniFFmpeg,')
        path.write_text(text)
path = root / 'MediaPlayer.cpp'
text = path.read_text()
anchor = '    ASSERT(mediaEngineVectorLock.isLocked());\n'
if '// Omni bounded video backend' not in text:
    text = text.replace('namespace WebCore {\n', 'namespace WebCore {\nvoid registerOmniMediaEngine(MediaEngineRegistrar);\n', 1)
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '    // Omni bounded video backend\n    registerOmniMediaEngine(addMediaEngine);\n')
    path.write_text(text)

# IPC validates enum values independently of the C++ declaration.
path = pathlib.Path(sys.argv[1]) / 'Source/WebKit/Shared/WebCoreArgumentCoders.serialization.in'
text = path.read_text()
anchor = 'enum class WebCore::MediaPlayerMediaEngineIdentifier : uint8_t {'
if anchor + '\n    OmniFFmpeg,' not in text:
    assert text.count(anchor) == 1
    path.write_text(text.replace(anchor, anchor + '\n    OmniFFmpeg,'))
