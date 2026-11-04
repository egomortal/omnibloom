#!/usr/bin/env python3
"""files-broker-1: applies OMNI_FILES_BROKER_V1 to the 56c entry copies in changes/files-broker-1/entry.
Keeps CRLF line endings. Every replacement must match exactly once (else it stops)."""
import sys
from pathlib import Path

E = Path(sys.argv[1])

def patch(name, pairs):
    p = E / name
    raw = p.read_bytes().decode('utf-8')
    crlf = '\r\n' in raw
    text = raw.replace('\r\n', '\n')
    for old, new in pairs:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f'{name}: expected 1 match, found {n}: {old[:80]!r}')
        text = text.replace(old, new)
    if crlf:
        text = text.replace('\n', '\r\n')
    p.write_bytes(text.encode('utf-8'))
    print('patched', name)

patch('OmniFeatures2Includes.h', [(
    '#include <string>\n',
    '#include <string>\n'
    '// OMNI_FILES_BROKER_V1: loopback client for the native title\'s USB broker (OmniFilesBroker.h)\n'
    '#include <sys/socket.h>\n#include <sys/time.h>\n#include <netinet/in.h>\n#include <arpa/inet.h>\n#include <fcntl.h>\n#include <atomic>\n'
    '// Defined only in the native title (outputs/omni-native-s1b/src/NativeFilesBroker.cpp); null in the big-app.\n'
    'extern "C" int omni_native_title_active(void) __attribute__((weak));\n')])

patch('OmniFeatures.h', [(
    '#include "OmniDownloadsPage.h"\n',
    '#include "OmniFilesBroker.h" // OMNI_FILES_BROKER_V1\n#include "OmniDownloadsPage.h"\n')])

# ---------------------------------------------------------------- file picker
patch('OmniFilePicker.h', [
    # state: cached places (native), copy in progress
    ('    std::vector<std::string> chosen;         // full paths (multi-select)\n};',
     '    std::vector<std::string> chosen;         // full paths (multi-select)\n'
     '    bool copying = false;                    // OMNI_FILES_BROKER_V1: USB files being copied in before the hand-off\n'
     '    std::vector<OmniPickPlace> places;       // native title: places cached per picker (the broker call can take a moment)\n'
     '    bool placesValid = false;\n'
     '};'),
    # places: native -> local places + broker roots
    ('static std::vector<OmniPickPlace> omniPickPlaces()\n{\n    std::vector<OmniPickPlace> out;\n',
     'static std::vector<OmniPickPlace> omniPickPlaces()\n{\n'
     '    if (omniNativeTitle() && omniPick.placesValid) return omniPick.places;   // OMNI_FILES_BROKER_V1\n'
     '    std::vector<OmniPickPlace> out;\n'),
    ('    for (int i = 0; i < 8; ++i) add("USB drive " + std::to_string(i + 1), "/mnt/usb" + std::to_string(i));\n'
     '    for (int i = 0; i < 2; ++i) add("Extended storage " + std::to_string(i + 1), "/mnt/ext" + std::to_string(i));\n'
     '    add("Omni data", omniData("").substr(0, omniData("").size() - 1));\n'
     '    add("Console data", "/data");\n'
     '    return out;\n}',
     '    if (omniNativeTitle()) {   // OMNI_FILES_BROKER_V1: the title can\'t see /mnt/usb*, /mnt/ext*: ask the broker\n'
     '        for (const auto& p : omniOfbPlaces()) {\n'
     '            const bool usb = p.root.rfind("/mnt/usb", 0) == 0;\n'
     '            const int n = atoi(p.root.c_str() + (usb ? 8 : 8)) + 1;\n'
     '            out.push_back({ std::string(usb ? "USB drive " : "Extended storage ") + std::to_string(n), p.root });\n'
     '        }\n'
     '    } else {\n'
     '    for (int i = 0; i < 8; ++i) add("USB drive " + std::to_string(i + 1), "/mnt/usb" + std::to_string(i));\n'
     '    for (int i = 0; i < 2; ++i) add("Extended storage " + std::to_string(i + 1), "/mnt/ext" + std::to_string(i));\n'
     '    }\n'
     '    add("Omni data", omniData("").substr(0, omniData("").size() - 1));\n'
     '    add("Console data", "/data");\n'
     '    if (omniNativeTitle()) { omniPick.places = out; omniPick.placesValid = true; }\n'
     '    return out;\n}'),
    # scan: remote dirs through the broker
    ('    if (omniPick.dir.empty()) return;\n    if (DIR* dp = opendir(omniPick.dir.c_str())) {',
     '    if (omniPick.dir.empty()) return;\n'
     '    if (omniOfbRemote(omniPick.dir)) {   // OMNI_FILES_BROKER_V1\n'
     '        std::vector<OmniOfbEntry> rows;\n'
     '        const int err = omniOfbList(omniPick.dir, rows);\n'
     '        if (err) notice("Couldn\'t read " + omniPick.dir + ": " + omniOfbErr(err));\n'
     '        for (auto& r : rows) {\n'
     '            if (r.name.empty() || r.name[0] == \'.\') continue;\n'
     '            OmniPickEntry e; e.name = r.name; e.dir = r.dir; e.size = r.size; e.mtime = r.mtime;\n'
     '            omniPick.entries.push_back(std::move(e));\n'
     '            if (omniPick.entries.size() >= 2000) break;\n'
     '        }\n'
     '    } else if (DIR* dp = opendir(omniPick.dir.c_str())) {'),
    # finish: remote paths are copied in first (background), then handed to WebKit
    ('static bool omniPickIsChosen(const std::string& path)',
     '// OMNI_FILES_BROKER_V1: WebKit reads the chosen files itself, so USB files are copied to\n'
     '// /data/omni/uploads/ first (on the broker job thread); omniPickTick hands the copies over.\n'
     'static void omniPickChoose(const std::vector<std::string>& paths)\n'
     '{\n'
     '    bool remote = false;\n'
     '    for (auto& p : paths) remote |= omniOfbRemote(p);\n'
     '    if (!remote) { omniPickFinish(paths); return; }\n'
     '    if (omniOfbBusy()) { notice("A USB copy is already running"); omniPickFinish({}); return; }\n'
     '    omniPick.copying = true;\n'
     '    mkdir(omniData("uploads").c_str(), 0777);\n'
     '    notice("Copying from the USB drive...");\n'
     '    omniOfbStart(1, [paths]() {\n'
     '        static unsigned serial = 0;\n'
     '        std::vector<std::string> local;\n'
     '        for (auto& p : paths) {\n'
     '            if (!omniOfbRemote(p)) { local.push_back(p); continue; }\n'
     '            const std::string dest = omniData("uploads/") + std::to_string(time(nullptr)) + "-" + std::to_string(++serial) + "-" + omniSafeFileName(omniOfbBaseName(p));\n'
     '            const int err = omniOfbCopyIn(p, dest);\n'
     '            if (err) { omniOfbJob.error = "Couldn\'t copy " + omniOfbBaseName(p) + ": " + omniOfbErr(err); omniOfbJob.state = 3; return; }\n'
     '            local.push_back(dest);\n'
     '        }\n'
     '        omniOfbJob.results = local;\n'
     '        omniOfbJob.state = 2;\n'
     '    });\n'
     '}\n'
     'static bool omniPickIsChosen(const std::string& path)'),
    ('    if (omniPick.dirs) add(3, "Upload this whole folder");',
     '    if (omniPick.dirs && !omniOfbRemote(omniPick.dir)) add(3, "Upload this whole folder");   // OMNI_FILES_BROKER_V1: files only from USB'),
    ('    if (r.id == 2 && a) { const auto paths = omniPick.chosen; omniPickFinish(paths); omniFxPop(); return true; }',
     '    if (r.id == 2 && a) { const auto paths = omniPick.chosen; omniFxPop(); omniPickChoose(paths); return true; }'),
    ('        if (a) { omniPickFinish({ path }); omniFxPop(); return true; }',
     '        if (a) { omniFxPop(); omniPickChoose({ path }); return true; }'),
    # open: drop stale upload copies; fresh places
    ('    if (editing) dismissKeyboard();\n    omniFxCloseAll();\n',
     '    if (omniNativeTitle()) omniOfbCleanUploads(3600);   // OMNI_FILES_BROKER_V1: copies from earlier pickers\n'
     '    if (editing) dismissKeyboard();\n    omniFxCloseAll();\n'),
    ('    if (omniPickIsDir(dl)) omniPickGo(dl, dl); else omniPickGo("", "");\n    omniPickShow();\n}',
     '    if (omniPickIsDir(dl)) omniPickGo(dl, dl); else omniPickGo("", "");\n    omniPickShow();\n}\n'
     + open(Path(__file__).with_name('picker_tick.inc')).read().replace('\r\n', '\n').rstrip('\n')),
    ('static void omniPickTick()\n{\n    if (!omniPick.listener) return;\n',
     'static void omniPickTick()\n{\n'
     '    omniOfbTick();   // OMNI_FILES_BROKER_V1: copy jobs, the files self-test\n'
     '    if (!omniPick.listener) return;\n'
     '    if (omniPick.copying) return;   // the copy job finishes (or cancels) the hand-off\n'),
])

# ---------------------------------------------------------------- downloads page
patch('OmniDownloadsPage.h', [
    ('        if (b == SDL_CONTROLLER_BUTTON_X) {\n            omniFxDeleteName = name;',
     '        if (b == SDL_CONTROLLER_BUTTON_Y && omniNativeTitle()) {   // OMNI_FILES_BROKER_V1: copy to a USB drive\n'
     '            omniOfbCopyToUsb(omniData("downloads/") + name);\n'
     '            return true;\n'
     '        }\n'
     '        if (b == SDL_CONTROLLER_BUTTON_X) {\n            omniFxDeleteName = name;'),
    ('    p.faces = { { 0, "Open" }, { 2, "Delete / cancel" }, { 1, "Back" } };',
     '    p.faces = { { 0, "Open" }, { 2, "Delete / cancel" }, { 1, "Back" } };\n'
     '    if (omniNativeTitle()) p.faces = { { 0, "Open" }, { 2, "Delete / cancel" }, { 3, "Copy to USB" }, { 1, "Back" } };   // OMNI_FILES_BROKER_V1'),
])
