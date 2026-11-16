#!/usr/bin/env python3
"""OMNI_COOKIE_POLICY_V1 (2026-11-16): Browser settings > "Cookies: Allow all / Block third-party" (backlog E02).

What the user sees
  - Browser settings has a new row after "Ask sites not to sell or share my data":
        "Cookies"     value "Allow all" (default) or "Block third-party"; Cross / Left / Right switch it.
        subtitle (Allow all):         "Every site can set cookies, embedded ones too. Block third-party stops cross-site
                                       trackers; some sign-ins inside other sites (embedded logins) may break"
        subtitle (Block third-party): "Only the site in the address bar (and its subdomains) gets cookies; embedded
                                       sites get none. Some sign-ins inside other sites (embedded logins) may break"
    A notice confirms the change ("Third-party cookies blocked (private tabs too). Reload open pages; ..." /
    "Cookies allowed for all sites ..."). Saved in /data/omni/cookie-policy.txt ("cookies=block-third-party").
  - Private tabs use their own (non-persistent) data store: the same policy is set on it when it is created and on
    every change.

What WebKit's C API really does here (checked in the engine's WebKit tree (s1/webkit), Curl network backend):
  works:  WKHTTPCookieStoreSetHTTPCookieAcceptPolicy(WKWebsiteDataStoreGetHTTPCookieStore(store), policy, ...)
          -> API::HTTPCookieStore::setHTTPCookieAcceptPolicy -> Messages::WebCookieManager::SetHTTPCookieAcceptPolicy
          (session of that store) -> WebCookieManagerCurl::platformSetHTTPCookieAcceptPolicy
          -> NetworkStorageSession::setCookieAcceptPolicy -> CookieJarDB::setAcceptPolicy. CookieJarDB checks it in
          searchCookies (HTTP Cookie header + document.cookie) and canAcceptCookie (Set-Cookie + document.cookie
          writes) with the request's first party (the top document): ExclusivelyFromMainDocumentDomain lets a
          request have cookies only when its host is the first party's host or shares its registrable domain
          (RegistrableDomain::matches). Already-stored third-party cookies stay in the database but are neither sent
          nor readable; "Allow all" brings them back.
  stub:   WKCookieManagerSetHTTPCookieAcceptPolicy / WKCookieManagerGetHTTPCookieAcceptPolicy (empty bodies).
  no effect on Curl: ITP / WKWebsiteDataStoreSetResourceLoadStatisticsShouldBlockThirdPartyCookiesForTesting and
          every per-domain tracking-prevention call (NetworkStorageSessionCurl ignores ApplyTrackingPrevention /
          ShouldRelaxThirdPartyCookieBlocking; no shouldBlockCookies there).
  So: no per-site exceptions exist (CookieJarDB has one policy per session and no allow list): this is global only,
  no Site settings row, no per-site "Allow". "Block all" (kWKHTTPCookieAcceptPolicyNever) is NOT offered: it makes
  CookieJarDB::isEnabled() false, which also turns deleteAllCookies / deleteCookie into no-ops, so Clear browsing
  data would silently keep every cookie while it is set.
  The session's policy is not persisted by WebKit: NetworkSessionCurl ignores NetworkSessionCreationParameters::
  cookieAcceptPolicy, every Curl session starts at CookieJarDB's default (Always). Hence:
    - main(): right after the primary data store is set, the saved policy is sent (only when it is not Allow all:
      the default run stays byte-for-byte what it was, no early network-process launch);
    - omniNewPrivateTab(): the same for the private store when it is created;
    - a change: sent to the main store and (if it exists) the private store;
    - network process crash: WKContextClientV0.networkProcessDidCrash (installed on both contexts; neither had a
      context client) sets a flag; omniCkpTick (omniF3Tick) re-sends the policy to both stores (the relaunched
      process starts at Always again). Pages loading between the crash and the next tick may get third-party
      cookies once.

Pure part: engine/entry/OmniCookiePolicy.h (no SDL / WebKit): modes, the WebKit policy values, file parse /
serialize, step, texts, when to send. Tested by tools/test_cookie_policy.cpp:
    g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_cookie_policy.cpp -o t && ./t
Shell side: engine/entry/OmniCookiePolicyShell.h (included from OmniFeatures3.h after OmniHttpsOnlyShell.h); its
static_asserts tie the pure values to WebKit's kWKHTTPCookieAcceptPolicy* enum. Alias OCKP, names omniCkp*, row id 887 (894 is apply_audio_bar.py's;
free in the tree and in every sibling's code on 2026-11-16).

Anchors (exactly once each, full lines; MARK makes each file idempotent):
  OmniBrowser.cpp       the OmniHttpsOnly.h include line (pure include); the omniPrivateStore definition (forward
                        declaration after it); omniNewPrivateTab's omniAdNotePrivateContext line (private store);
                        main()'s WKContextSetPrimaryWebsiteDataStore(context.get(), ...) line (main store).
  OmniBrowserSettings.h the omniHoSettingsInput declaration, the omniHoSettingsRows call, the omniHo input line.
  OmniFeatures3.h       the OmniHttpsOnlyShell.h include line; the omniClrTick line of omniF3Tick.
Apply AFTER apply_https_only.py, apply_clear_range.py and apply_addons (their lines are anchors).
usage: apply_cookie_policy.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_COOKIE_POLICY_V1'
HERE = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    sys.exit('usage: apply_cookie_policy.py <engine tree>')
root = Path(sys.argv[1]) / 'engine' / 'entry'
IDS = ('887',)
NAMES = ('OCKP', 'omniCkp', 'OmniCookiePolicy', 'OMNI_COOKIE_POLICY')

PURE = r'''// OMNI_COOKIE_POLICY_V1: the pure part of Browser settings > "Cookies" (no SDL, no WebKit). The shell side is
// OmniCookiePolicyShell.h; the reasons (what this WebKit's Curl backend honours) are in tools/apply_cookie_policy.py.
// Tested on the host with g++ (test_cookie_policy.cpp).
#pragma once
#include <cstdint>
#include <string>

namespace OmniCookiePolicy {

// Global only: CookieJarDB has one accept policy per session and no per-site exceptions.
enum Mode : int { kAllowAll = 0, kBlockThirdParty = 1 };
constexpr int kModes = 2;
constexpr const char* kFileName = "cookie-policy.txt";
constexpr long kMaxFileBytes = 4096;

// WebKit's WKHTTPCookieAcceptPolicy values (WKCookieManager.h; the shell static_asserts them).
constexpr uint32_t kWkAlways = 0, kWkNever = 1, kWkOnlyFromMainDocumentDomain = 2, kWkExclusivelyFromMainDocumentDomain = 3;
// Block third-party: Exclusively (not OnlyFromMainDocumentDomain, which still lets a third party that already has
// cookies read and write them). Never is not used (it also stops cookie deletion on Curl).
inline uint32_t wkPolicy(Mode m) { return m == kBlockThirdParty ? kWkExclusivelyFromMainDocumentDomain : kWkAlways; }

inline Mode clampMode(int v) { return v == kBlockThirdParty ? kBlockThirdParty : kAllowAll; }
inline const char* key(Mode m) { return m == kBlockThirdParty ? "block-third-party" : "allow-all"; }
inline const char* name(Mode m) { return m == kBlockThirdParty ? "Block third-party" : "Allow all"; }

inline std::string trim(const std::string& s)
{
    size_t a = 0, b = s.size();
    while (a < b && (s[a] == ' ' || s[a] == '\t' || s[a] == '\r')) ++a;
    while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t' || s[b - 1] == '\r')) --b;
    return s.substr(a, b - a);
}
// "cookies=block-third-party" (the last valid line wins); anything else: Allow all (WebKit's own default).
inline Mode parse(const std::string& text)
{
    Mode m = kAllowAll;
    size_t p = 0;
    while (p <= text.size()) {
        size_t nl = text.find('\n', p);
        if (nl == std::string::npos) nl = text.size();
        const std::string line = trim(text.substr(p, nl - p));
        p = nl + 1;
        if (line.empty() || line[0] == '#') continue;
        const size_t eq = line.find('=');
        if (eq == std::string::npos || trim(line.substr(0, eq)) != "cookies") continue;
        const std::string v = trim(line.substr(eq + 1));
        if (v == "block-third-party") m = kBlockThirdParty;
        else if (v == "allow-all") m = kAllowAll;
    }
    return m;
}
inline std::string serialize(Mode m)
{
    return std::string("# Omni: Browser settings > Cookies (allow-all / block-third-party)\ncookies=") + key(m) + "\n";
}
// Cross / Right: next, Left: previous (wraps).
inline Mode step(Mode m, int dir)
{
    const int n = ((int(m) + (dir < 0 ? -1 : 1)) % kModes + kModes) % kModes;
    return clampMode(n);
}

// The row's subtitle: always says that embedded sign-ins may break.
inline std::string detail(Mode m)
{
    return m == kBlockThirdParty
        ? "Only the site in the address bar (and its subdomains) gets cookies; embedded sites get none. Some sign-ins inside other sites (embedded logins) may break"
        : "Every site can set cookies, embedded ones too. Block third-party stops cross-site trackers; some sign-ins inside other sites (embedded logins) may break";
}
inline std::string changedNotice(Mode m, bool privateOpen)
{
    std::string s = m == kBlockThirdParty ? "Third-party cookies blocked" : "Cookies allowed for all sites";
    s += privateOpen ? " (private tabs too)." : ".";
    s += m == kBlockThirdParty ? " Reload open pages; if a sign-in breaks, switch back" : " Reload open pages to use it";
    return s;
}

// Whether the shell sends the policy to a store. A fresh Curl session (a new store, or any session after a network
// process restart) starts at Always, so Allow all needs nothing there; a change is always sent.
inline bool shouldApply(Mode m, bool freshSession) { return !freshSession || m != kAllowAll; }

} // namespace OmniCookiePolicy
'''

SHELL = r'''// OMNI_COOKIE_POLICY_V1: Browser settings > "Cookies" (shell side). Included from OmniFeatures3.h (inside
// OmniBrowser.cpp's anonymous namespace, after OmniHttpsOnlyShell.h). The pure part is OmniCookiePolicy.h; the
// reasons are in tools/apply_cookie_policy.py. Main thread only; the file is written by omniIoQueue.
#pragma once

namespace OCKP = OmniCookiePolicy;
static_assert(OCKP::kWkAlways == kWKHTTPCookieAcceptPolicyAlways, "OMNI_COOKIE_POLICY_V1: WebKit enum changed");
static_assert(OCKP::kWkNever == kWKHTTPCookieAcceptPolicyNever, "OMNI_COOKIE_POLICY_V1: WebKit enum changed");
static_assert(OCKP::kWkOnlyFromMainDocumentDomain == kWKHTTPCookieAcceptPolicyOnlyFromMainDocumentDomain, "OMNI_COOKIE_POLICY_V1: WebKit enum changed");
static_assert(OCKP::kWkExclusivelyFromMainDocumentDomain == kWKHTTPCookieAcceptPolicyExclusivelyFromMainDocumentDomain, "OMNI_COOKIE_POLICY_V1: WebKit enum changed");

static OCKP::Mode omniCkpMode = OCKP::kAllowAll;
static bool omniCkpLoaded = false;
static bool omniCkpNetLost = false;   // the network process crashed: its relaunched sessions start at Always

static void omniCkpLoad()
{
    if (omniCkpLoaded) return;
    omniCkpLoaded = true;
    FILE* f = fopen(omniData(OCKP::kFileName).c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0 && long(text.size()) < OCKP::kMaxFileBytes) text.append(buf, n);
    fclose(f);
    omniCkpMode = OCKP::parse(text);
}
static void omniCkpWrite()
{
    if (omniTestMode()) return;
    omniIoQueue(omniData(OCKP::kFileName), OCKP::serialize(omniCkpMode), false);
}
static void omniCkpSent(void* ctx)
{
    const uintptr_t v = reinterpret_cast<uintptr_t>(ctx);
    fprintf(stderr, "OMNI COOKIES: %s store accept policy %u set\n", (v & 0x10u) ? "private" : "main", unsigned(v & 0xfu)); fflush(stderr);
}
static void omniCkpSend(WKWebsiteDataStoreRef store, bool priv)
{
    if (!store) return;
    WKHTTPCookieStoreRef cookies = WKWebsiteDataStoreGetHTTPCookieStore(store);
    if (!cookies) return;
    const uint32_t wk = OCKP::wkPolicy(omniCkpMode);
    WKHTTPCookieStoreSetHTTPCookieAcceptPolicy(cookies, wk, reinterpret_cast<void*>(uintptr_t(wk | (priv ? 0x10u : 0u))), omniCkpSent);
}
static void omniCkpSendAll(bool fresh)
{
    omniCkpLoad();
    if (!OCKP::shouldApply(omniCkpMode, fresh)) return;
    omniCkpSend(websiteDataStore.get(), false);
    if (omniPrivateStore) omniCkpSend(omniPrivateStore.get(), true);
}
static void omniCkpNetCrashed(WKContextRef, const void*) { omniCkpNetLost = true; }
// main() (main store) and omniNewPrivateTab() (private store), right after the store is the context's primary one.
static void omniCkpStoreCreated(WKContextRef c, WKWebsiteDataStoreRef store, bool priv)
{
    omniCkpLoad();
    if (c) {
        WKContextClientV0 client {};
        client.base.version = 0;
        client.base.clientInfo = nullptr;
        client.networkProcessDidCrash = omniCkpNetCrashed;
        WKContextSetClient(c, &client.base);
    }
    if (OCKP::shouldApply(omniCkpMode, true)) omniCkpSend(store, priv);
}
static void omniCkpTick()   // from omniF3Tick
{
    if (!omniCkpNetLost) return;
    omniCkpNetLost = false;
    fprintf(stderr, "OMNI COOKIES: network process crashed, policy %s sent again\n", OCKP::key(omniCkpMode)); fflush(stderr);
    omniCkpSendAll(true);
}

// --- Browser settings ----------------------------------------------------------------------------------------------
static void omniCkpSettingsRow(OmniFxPanel& p)
{
    omniCkpLoad();
    OmniFxRow r; r.id = omniCkpRowId; r.label = "Cookies"; r.value = OCKP::name(omniCkpMode); r.stepper = true;
    r.detail = OCKP::detail(omniCkpMode);
    p.rows.push_back(r);
}
static bool omniCkpSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A && b != SDL_CONTROLLER_BUTTON_DPAD_LEFT && b != SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return false;
    omniCkpLoad();
    omniCkpMode = OCKP::step(omniCkpMode, b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? -1 : 1);
    omniCkpWrite();
    omniCkpSendAll(false);
    notice(OCKP::changedNotice(omniCkpMode, omniPrivateStore.get() != nullptr));
    return true;
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n',
         '#include "OmniHttpsOnly.h" // OMNI_HTTPS_ONLY_V1: HTTPS-only mode + GPC, https-only.txt (pure)\n'
         '#include "OmniCookiePolicy.h" // OMNI_COOKIE_POLICY_V1: Browser settings > Cookies (pure)\n'),
        ('static WKRetainPtr<WKWebsiteDataStoreRef> omniPrivateStore;\n',
         'static WKRetainPtr<WKWebsiteDataStoreRef> omniPrivateStore;\n'
         'static void omniCkpStoreCreated(WKContextRef c, WKWebsiteDataStoreRef store, bool priv); /* OMNI_COOKIE_POLICY_V1 (OmniCookiePolicyShell.h) */\n'),
        ('        omniAdNotePrivateContext(omniPrivateContext.get()); // OMNI_ADDONS_V1\n',
         '        omniAdNotePrivateContext(omniPrivateContext.get()); // OMNI_ADDONS_V1\n'
         '        omniCkpStoreCreated(omniPrivateContext.get(), omniPrivateStore.get(), true); /* OMNI_COOKIE_POLICY_V1: the same cookie policy for private tabs */\n'),
        ('    WKContextSetPrimaryWebsiteDataStore(context.get(), websiteDataStore.get());\n',
         '    WKContextSetPrimaryWebsiteDataStore(context.get(), websiteDataStore.get());\n'
         '    omniCkpStoreCreated(context.get(), websiteDataStore.get(), false); /* OMNI_COOKIE_POLICY_V1: saved cookie policy (nothing sent for Allow all) */\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static bool omniHoSettingsInput(int id, int b);\n',
         'static bool omniHoSettingsInput(int id, int b);\n'
         'constexpr int omniCkpRowId = 887; /* OMNI_COOKIE_POLICY_V1: "Cookies" (OmniCookiePolicyShell.h) */\n'
         'static void omniCkpSettingsRow(OmniFxPanel& p);\n'
         'static bool omniCkpSettingsInput(int b);\n'),
        ('    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n',
         '    omniHoSettingsRows(p); // OMNI_HTTPS_ONLY_V1: HTTPS-only mode, Ask sites not to sell or share my data\n'
         '    omniCkpSettingsRow(p); /* OMNI_COOKIE_POLICY_V1: Cookies (Allow all / Block third-party) */\n'),
        ('    if (r.id == omniHoRowId || r.id == omniHoGpcRowId) return omniHoSettingsInput(r.id, b); // OMNI_HTTPS_ONLY_V1 (before the >= 300 rows)\n',
         '    if (r.id == omniCkpRowId) return omniCkpSettingsInput(b); /* OMNI_COOKIE_POLICY_V1 (before the >= 300 rows) */\n'
         '    if (r.id == omniHoRowId || r.id == omniHoGpcRowId) return omniHoSettingsInput(r.id, b); // OMNI_HTTPS_ONLY_V1 (before the >= 300 rows)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n',
         '#include "OmniHttpsOnlyShell.h" // OMNI_HTTPS_ONLY_V1\n'
         '#include "OmniCookiePolicyShell.h" /* OMNI_COOKIE_POLICY_V1 */\n'),
        ('    omniClrTick(now);   /* OMNI_CLEAR_RANGE_V1: native timeout of Clear browsing data */\n',
         '    omniClrTick(now);   /* OMNI_CLEAR_RANGE_V1: native timeout of Clear browsing data */\n'
         '    omniCkpTick();      /* OMNI_COOKIE_POLICY_V1: sends the cookie policy again after a network process crash */\n'),
    ],
}
NEEDS = {'OmniBrowser.cpp': ('OMNI_HTTPS_ONLY_V1', 'OMNI_ADDONS_V1'),
         'OmniBrowserSettings.h': ('OMNI_HTTPS_ONLY_V1',),
         'OmniFeatures3.h': ('OMNI_HTTPS_ONLY_V1', 'OMNI_CLEAR_RANGE_V1')}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits):
    s = (root / name).read_bytes().decode('utf-8')
    if MARK in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if MARK in s:
        return name + ': already'
    for old0, new0 in edits:
        old, e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))
        s = s.replace(old, new0.replace('\n', e), 1)
    p.write_bytes(s.encode('utf-8'))
    return name + ': applied'


def write_new(name, text, like):
    raw = (root / like).read_bytes()
    nl = '\r\n' if raw.count(b'\r\n') * 2 > raw.count(b'\n') else '\n'
    data = text.replace('\r\n', '\n').replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


# The Controls guide's table names other patches' handlers by design: never a name clash (numbers still count there).
GUIDE = ('OmniControlsHelp.h', 'OmniControlsHelpShell.h')
_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes (e.g. "834-839" in a generated header) is not a use."""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. Numeric ids are never looked for in siblings (their notes list other patches' id ranges)."""
    import io
    import tokenize
    cut, first = [], True
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.COMMENT or (first and t.type == tokenize.STRING):
                cut.append((t.start, t.end))
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                              tokenize.ENCODING):
                first = False
    except (tokenize.TokenError, SyntaxError):
        return ''.join(r for r in src.splitlines(True) if not r.lstrip().startswith('#'))
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']   # tokenize's rows end at '\n' only
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def ids_free():
    """Before a first apply: no other patch or tree file uses this patch's ids or names."""
    word = re.compile(r'\b(%s)\b' % '|'.join(IDS))
    name = re.compile('|'.join(NAMES))
    mine = {'OmniCookiePolicy.h', 'OmniCookiePolicyShell.h'}
    # A sibling not applied to this tree yet still owns its ids: its code (generated headers / edits included,
    # comments and docstring stripped) assigning one of ours to a row id ("kRowId = 894", "omniAbrRowId = 894",
    # "kSettingsRowId = 894", "constexpr int x = 894") is a clash.
    assign = re.compile(r'(?:\b\w*[Rr]ow\w*|\bconstexpr\s+int\s+\w+)\s*=\s*(%s)(?![\w.])' % '|'.join(IDS))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        t = code_only(f.read_text(encoding='utf-8', errors='replace'))
        m = name.search(t) or assign.search(t)   # bare numbers: not looked for (siblings' notes list others' ids)
        if m:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in mine or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        c = cpp_code(t)
        m = word.search(c) or (None if f.name in GUIDE else name.search(c))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other ids / names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        ids_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    msgs = [write_new('OmniCookiePolicy.h', PURE, 'OmniHttpsOnly.h'),
            write_new('OmniCookiePolicyShell.h', SHELL, 'OmniHttpsOnlyShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
