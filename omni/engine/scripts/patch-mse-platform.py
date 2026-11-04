#!/usr/bin/env python3
"""Add distinct experimental MSE identities; run after patch-media-engine.py.

Does not enable MEDIA_SOURCE. Fail closed on unexpected pinned header layouts.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
def patch(relative, old, new, marker):
    path = root / relative
    text = path.read_text()
    if marker in text:
        return
    assert text.count(old) == 1, (relative, old)
    path.write_text(text.replace(old, new))

graphics = 'Source/WebCore/platform/graphics/'
# The class already exports this member. Prospero rejects redundant dllexport
# on the member, unlike the compilers used by the upstream Apple port.
patch(graphics + 'MediaSourcePrivate.h',
      '    WEBCORE_EXPORT static PlatformTimeRanges computeBufferedRanges(',
      '    static PlatformTimeRanges computeBufferedRanges(',
      '    static PlatformTimeRanges computeBufferedRanges(')
for file, anchor in [
    (graphics + 'MediaPlayerEnums.h', 'enum class MediaPlayerMediaEngineIdentifier : uint8_t {'),
    (graphics + 'MediaPlayer.h', 'enum class MediaPlayerType {'),
    ('Source/WebKit/Shared/WebCoreArgumentCoders.serialization.in', 'enum class WebCore::MediaPlayerMediaEngineIdentifier : uint8_t {')]:
    patch(file, anchor + '\n    OmniFFmpeg,', anchor + '\n    OmniFFmpeg,\n    OmniMSE,', anchor + '\n    OmniFFmpeg,\n    OmniMSE,')

patch(graphics + 'MediaPlayer.h', 'enum class MediaPlatformType {',
      'enum class MediaPlatformType {\n    OmniFFmpeg,', 'enum class MediaPlatformType {\n    OmniFFmpeg,')
sample = 'Source/WebCore/platform/MediaSample.h'
patch(sample, 'class MockSampleBox;', 'class MockSampleBox;\nclass OmniMediaSample;', 'class OmniMediaSample;')
patch(sample, 'using VariantType = Variant<const MockSampleBox*',
      'using VariantType = Variant<const MockSampleBox*, const OmniMediaSample*', 'Variant<const MockSampleBox*, const OmniMediaSample*')
patch(sample, '    const MockSampleBox* mockSampleBox()',
      '    const OmniMediaSample* omniSample() const { return std::get<const OmniMediaSample*>(m_sample); }\n\n    const MockSampleBox* mockSampleBox()', 'const OmniMediaSample* omniSample()')
patch(sample, '        GStreamerSample,', '        GStreamerSample,\n        OmniFFmpegSample,', '        OmniFFmpegSample,')
patch(graphics + 'MediaPlayer.cpp', 'void registerOmniMediaEngine(MediaEngineRegistrar);',
      'void registerOmniMediaEngine(MediaEngineRegistrar);\n#if ENABLE(MEDIA_SOURCE)\nvoid registerOmniMSEEngine(MediaEngineRegistrar);\n#endif', 'void registerOmniMSEEngine(MediaEngineRegistrar);')
patch(graphics + 'MediaPlayer.cpp', '    registerOmniMediaEngine(addMediaEngine);',
      '    registerOmniMediaEngine(addMediaEngine);\n#if ENABLE(MEDIA_SOURCE)\n    registerOmniMSEEngine(addMediaEngine);\n#endif', '    registerOmniMSEEngine(addMediaEngine);')
print('Experimental Omni MSE platform identities registered (feature flag unchanged).')
