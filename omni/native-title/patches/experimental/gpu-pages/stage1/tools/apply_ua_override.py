"""OMNI_UA_OVERRIDE_V1 (2026-11-13, YouTube "replay" work): the desktop user agent can be set from a file.

Omni tells every site it is Safari 17 on a Mac, but the engine is WebKit 620 (Safari 18 era). Feature/claim mismatches
are a known reason for YouTube's BotGuard to distrust a session (a distrusted session = rejected PO token = the guard
reloads the page = the video "replays"). This makes the desktop UA a file setting so it can be A/B tested on the
console without a rebuild, and changed later without one:

  /data/omni/ua-desktop.txt   first line = the desktop user agent (20..400 printable ASCII characters); read once at
                              start. Missing or invalid: the built-in Safari 17 string, as before.

The UA in use is logged once at start ("OMNI UA: ..."). The mobile UA (per-site Mobile setting) is unchanged.
usage: apply_ua_override.py <engine tree>   (edits engine/entry/OmniBrowser.cpp)
"""
import sys
from pathlib import Path

MARK = 'OMNI_UA_OVERRIDE_V1'
p = Path(sys.argv[1]) / 'engine' / 'entry' / 'OmniBrowser.cpp'
raw = p.read_bytes()
nl = '\r\n' if b'\r\n' in raw else '\n'
s = raw.decode('utf-8')
if MARK in s:
    print('already'); sys.exit(0)

SAFARI17 = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
EDITS = [
    ('static void omniApplyUserAgent(Tab* tab, const std::string& url);\n',
     '''static void omniApplyUserAgent(Tab* tab, const std::string& url);
// OMNI_UA_OVERRIDE_V1: the desktop user agent; /data/omni/ua-desktop.txt (first line) replaces the built-in one.
static const std::string& omniUaDesktop()
{
    static std::string* ua = nullptr;
    if (ua) return *ua;
    ua = new std::string("%s");
    if (FILE* f = fopen("/data/omni/ua-desktop.txt", "r")) {
        char line[512] = {0};
        if (fgets(line, sizeof line, f)) {
            std::string v(line);
            while (!v.empty() && (v.back() == '\\n' || v.back() == '\\r' || v.back() == ' ')) v.pop_back();
            bool ok = v.size() >= 20 && v.size() <= 400;
            for (char c : v) if (c < 32 || c > 126) ok = false;
            if (ok) *ua = v;
            else fprintf(stderr, "OMNI UA: /data/omni/ua-desktop.txt ignored (needs 20-400 printable characters)\\n");
        }
        fclose(f);
    }
    fprintf(stderr, "OMNI UA: desktop user agent: %%s (OMNI_UA_OVERRIDE_V1)\\n", ua->c_str());
    return *ua;
}
''' % SAFARI17),
    ('    auto userAgent = adoptWK(WKStringCreateWithUTF8CString("%s"));\n' % SAFARI17,
     '    auto userAgent = adoptWK(WKStringCreateWithUTF8CString(omniUaDesktop().c_str())); // OMNI_UA_OVERRIDE_V1\n'),
    ('    auto ua = adoptWK(WKStringCreateWithUTF8CString(mobile ? omniMobileUAString : omniDesktopUA));\n',
     '    auto ua = adoptWK(WKStringCreateWithUTF8CString(mobile ? omniMobileUAString : omniUaDesktop().c_str())); // OMNI_UA_OVERRIDE_V1\n'),
]
for old, new in EDITS:
    old, new = old.replace('\n', nl), new.replace('\n', nl)
    if s.count(old) != 1:
        sys.exit('OmniBrowser.cpp: anchor found %d times: %r' % (s.count(old), old[:90]))
    s = s.replace(old, new, 1)
p.write_bytes(s.encode('utf-8'))
print('applied')
