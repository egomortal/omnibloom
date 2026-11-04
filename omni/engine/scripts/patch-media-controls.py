#!/usr/bin/env python3
"""Wire upstream WebKit controls and bundled icons into the PlayStation theme."""
import pathlib
import sys

root = pathlib.Path(sys.argv[1]) / 'Source/WebCore'
derived = pathlib.Path(sys.argv[2]) / 'WebCore/DerivedSources'
assets = root / 'Modules/modern-media-controls'
theme = root / 'rendering/playstation'
script = (derived / 'ModernMediaControls.js').read_text()
styles = (derived / 'ModernMediaControls.css').read_text()
for name, class_name in [('adwaita-inline-media-controls', 'AdwaitaInlineMediaControls'),
                         ('adwaita-fullscreen-media-controls', 'AdwaitaFullscreenMediaControls'),
                         ('adwaita-layout-traits', 'AdwaitaLayoutTraits')]:
    if f'class {class_name}' not in script:
        script += '\n' + (assets / 'controls' / (name + '.js')).read_text()
for name in ['adwaita-inline-media-controls', 'adwaita-fullscreen-media-controls', 'adwaita-overrides']:
    styles += '\n' + (assets / 'controls' / (name + '.css')).read_text()
# Upstream source copyright/license comments are retained in the embedded assets.
header = '// Generated from the pinned WebKit sources; do not edit.\n'
for name, value in [('Script', script), ('Styles', styles)]:
    assert ')OMNI_ASSET"' not in value
    header += f'static constexpr char omniMediaControls{name}[] = R"OMNI_ASSET({value})OMNI_ASSET";\n'
lookup = ''
icons = sorted((assets / 'images/adwaita').glob('*'))
assert icons, 'Missing upstream Adwaita media control icons'
for i, path in enumerate(icons):
    if path.suffix not in ('.svg', '.png'):
        continue
    header += f'static constexpr uint8_t omniMediaIcon{i}[] = {{' + ','.join(str(v) for v in path.read_bytes()) + '};\n'
    lookup += f'    if (name == "{path.name}"_s) return SharedBuffer::create(std::span<const uint8_t>(omniMediaIcon{i}));\n'
def write(path, value):
    if not path.exists() or path.read_text() != value:
        path.write_text(value)
write(theme / 'OmniMediaControlsAssets.h', header)
path = theme / 'RenderThemePlayStation.h'
text = path.read_text()
if '// Omni upstream media controls' not in text:
    anchor = '    friend NeverDestroyed<RenderThemePlayStation>;'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '''
    // Omni upstream media controls
    Vector<String, 2> mediaControlsScripts() final;
    Vector<String, 2> mediaControlsStyleSheets(const HTMLMediaElement&) final;
    RefPtr<FragmentedSharedBuffer> mediaControlsImageDataForIconNameAndType(const String&, const String&) final;
''')
    write(path, text)
path = theme / 'RenderThemePlayStation.cpp'
text = path.read_text()
if '// Omni upstream media controls' not in text:
    text = text.replace('#include <wtf/NeverDestroyed.h>', '#include <wtf/NeverDestroyed.h>\n#include "SharedBuffer.h"\n#include <wtf/text/MakeString.h>\n#include "OmniMediaControlsAssets.h"')
    methods = '''
// Omni upstream media controls: runs in WebKit's isolated media-controls world.
Vector<String, 2> RenderThemePlayStation::mediaControlsScripts()
{
    return { String::fromUTF8(omniMediaControlsScript) };
}
Vector<String, 2> RenderThemePlayStation::mediaControlsStyleSheets(const HTMLMediaElement&)
{
    return { String::fromUTF8(omniMediaControlsStyles) };
}
RefPtr<FragmentedSharedBuffer> RenderThemePlayStation::mediaControlsImageDataForIconNameAndType(const String& iconName, const String& iconType)
{
    auto name = makeString(iconName, '.', iconType);
''' + lookup + '''    return nullptr;
}
'''
    text = text.replace('} // namespace WebCore', methods + '\n} // namespace WebCore')
    write(path, text)
path = root / 'Modules/mediacontrols/MediaControlsHost.cpp'
text = path.read_text()
anchor = '#elif USE(THEME_ADWAITA)\n    return "AdwaitaLayoutTraits"_s;'
if anchor in text:
    write(path, text.replace(anchor, '#elif USE(THEME_ADWAITA) || PLATFORM(PLAYSTATION)\n    return "AdwaitaLayoutTraits"_s;'))
