#!/usr/bin/env python3
"""OMNI_PC_LINKS_V1 (2026-11-16): a link sent from Omnibloom Setup on the PC ("Send a link to Omni", setup/pclinks.py)
is offered on the TV: "Link from your PC: <site>" with Dismiss / Open. Omni never opens it on its own.

Why an inbox file and not a listener: Omni does no networking of its own and the PC can't reach the Downloads app's
API (127.0.0.1 on the console). Setup already talks FTP to the console, so it drops a file:
    /data/omni/inbox/links-<YYYYmmdd>-<HHMMSS>-<6 hex>.txt     "omni-pc-links\\t1", then one link per line (<= 20)
uploaded as <name>.omnibloom-new, read back and renamed into place (Omni never sees half a file), a NEW name each time
(nothing is appended to or rewritten while Omni may be reading it, and Setup never deletes on the console). Omni deletes
each file it has read. (OMNI_SEND_LINK_V1 is the same direction over the network: a phone/PC -> Omni LAN server on port
8770, off by default, with a 6-digit code; Setup uses it instead when the user types that code: the link opens at once.)

What Omni does (OmniPcLinksShell.h, UI thread only)
  - Only while Omni is on screen (SDL window focus, omniShoulderFocused) and not in guest mode: one stat() of
    /data/omni/inbox every 5 s; the folder is listed only when its time stamp changed, at once when Omni comes back on
    screen, and every 60 s anyway (two changes in one second keep the same stamp). Nothing while Omni is in the
    background, nothing in test mode, nothing when /data/omni/pc-links-off.flag exists (checked once a minute).
  - Takes up to 32 files whose names are exactly Setup's (links-dddddddd-dddddd-hhhhhh.txt; nothing else there is
    touched), oldest first, each a regular file of at most 64 KiB (lstat: a link or folder is never followed): reads it,
    deletes it, keeps its valid links (OmniSendLink::validUrl: http(s) only, no user name / password, no spaces,
    controls or backslashes; and at most 2048 bytes) in a waiting list of at most 20 (repeats kept once; the rest is
    dropped with a notice). It stops taking files while the list is full, so they wait in the inbox.
  - One question at a time, only when no other dialog is up and the keyboard is closed: Parental controls first
    (OPAR::decide, the rules every navigation gets; a blocked link is never offered: "A link from your PC (<site>) is
    blocked by parental controls"); then the shell's own modal: title "Link from your PC: <site>", the link (cut at 200
    bytes), buttons Dismiss (focused) / Open. Open = "Open in new tab" (tab limit, memory guard, private rules; the
    navigation policy, parental controls included, still runs). If the dialog went away unanswered the next one comes.
  - Guest mode (OMNI_GUEST_MODE_V1, when its OmniGuestMode.h is in the tree: __has_include, so this patch builds with
    or without it): the inbox isn't read and no question is asked; files queue on the console until the owner is back.
    A question answered "Open" just as guest mode starts puts the link back in the list.
  - Logs counts only ("pc-links: 2 links taken, 0 refused"), never a link.

Files: engine/entry/OmniPcLinks.h (pure; from tools/OmniPcLinks.h; tested by tools/test_pc_links.cpp:
       g++ -std=c++20 -Wall -Wextra -I<tree>/engine/entry test_pc_links.cpp -o t && ./t) and OmniPcLinksShell.h.
Anchors in OmniBrowser.cpp (each exactly once; all apply_send_link.py's lines): the OmniSendLink.h include (pure include,
guest-mode probe, OPCL alias), the OmniSendLinkShell.h include (shell), the omniSlTick() call (omniPclTick() after it).
Needs OMNI_SEND_LINK_V1 and OMNI_PARENTAL_V1. Ids / names (omniPcl*, OmniPcLinks, OPCL, OMNI_PCL_*) are checked free in
the tree and the sibling patches before a first apply. No settings row, no new imports (stat / lstat / opendir /
readdir / fopen / unlink / access are already the title's).
usage: apply_pc_links.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_PC_LINKS_V1'
HERE = Path(__file__).resolve().parent
root = Path(sys.argv[1]) / 'engine' / 'entry'

NEEDS = {'OmniBrowser.cpp': ['OMNI_SEND_LINK_V1', 'OMNI_PARENTAL_V1'], 'OmniFeatures3.h': ['OMNI_PARENTAL_V1']}
NAMES = [r'\bomniPcl', r'\bOmniPcLinks', r'\bOPCL\b', r'\bOMNI_PCL_', r'pc-links-off\.flag', r'/data/omni/inbox\b']
MINE = {'OmniPcLinks.h', 'OmniPcLinksShell.h'}

SHELL = r'''// OMNI_PC_LINKS_V1: links sent from Omnibloom Setup on the PC (the pure part is OmniPcLinks.h; the reasons are in
// tools/apply_pc_links.py). Included in OmniBrowser.cpp's anonymous namespace after OmniSendLinkShell.h (so after
// OmniFeatures3.h and its OmniParentalShell.h). UI thread only. Links are never logged.
#pragma once

static const char* const omniPclDir = "/data/omni/inbox";
static const char* const omniPclOffFlag = "/data/omni/pc-links-off.flag";
static OPCL::Queue omniPclQueue;
static OPCL::Poll omniPclPoll;
static bool omniPclAsking = false;
static int64_t omniPclStampSeen = -1;

static bool omniPclGuest()
{
#if OMNI_PCL_HAS_GUEST
    return omniGuest();
#else
    return false;
#endif
}
// The inbox folder's time stamp (changes when Setup renames a file in, or Omni deletes one); -1: no folder.
static int64_t omniPclStamp()
{
    struct stat st {};
    if (stat(omniPclDir, &st) != 0 || !S_ISDIR(st.st_mode)) return -1;
    return int64_t(st.st_mtime) * 4096 + int64_t(st.st_size & 4095);
}
static void omniPclTake()
{
    DIR* d = opendir(omniPclDir);
    if (!d) return;
    std::vector<std::string> names;
    while (dirent* e = readdir(d)) {
        const std::string n = e->d_name;
        if (OPCL::inboxName(n)) names.push_back(n);
        if (names.size() >= OPCL::maxFiles) break;
    }
    closedir(d);
    std::sort(names.begin(), names.end());   // the name starts with the time it was sent
    int files = 0, taken = 0, refused = 0, dropped = 0;
    for (const std::string& n : names) {
        if (!omniPclQueue.room()) break;      // the rest waits in the inbox
        const std::string path = std::string(omniPclDir) + "/" + n;
        struct stat st {};
        if (lstat(path.c_str(), &st) != 0) continue;
        std::string text;
        if (S_ISREG(st.st_mode) && st.st_size <= off_t(OPCL::maxFileBytes)) {
            if (FILE* f = fopen(path.c_str(), "rb")) {
                char buf[4096];
                std::size_t r;
                while (text.size() <= OPCL::maxFileBytes && (r = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, r);
                fclose(f);
            }
        }
        if (!S_ISDIR(st.st_mode)) unlink(path.c_str());   // read once: never offered twice
        ++files;
        const OPCL::Parsed p = OPCL::parse(text);
        refused += p.rejected + (p.badHeader ? 1 : 0);
        const std::size_t before = omniPclQueue.items.size();
        dropped += omniPclQueue.add(p.links);
        taken += int(omniPclQueue.items.size() - before);
    }
    if (!files) return;
    char line[96];
    snprintf(line, sizeof line, "pc-links: %d file(s), %d link(s) taken, %d refused, %d over the limit", files, taken, refused, dropped);
    log(line);
    if (dropped) notice(OPCL::fullNotice(dropped));
}
static void omniPclOpen(const std::string& url)
{
    if (omniPclGuest()) { omniPclQueue.items.push_front(url); return; }   // asked just before guest mode: it waits
    if (!omniWebURL(url)) return;
    if (omniFxOpenInNewTab(url, false, false)) {   // the tab limit, memory guard and private rules apply
        omniFxCloseAll(); settingsOpen = false;
        notice(OPCL::openedNotice());
    } else notice("Couldn't open the link from your PC" + (status.empty() || status == "Ready" ? std::string() : ": " + status));
    log("pc-links: link opened");
}
static void omniPclAskNext()
{
    if (omniPclAsking && !omniModalCurrent()) omniPclAsking = false;   // the dialog went away unanswered
    if (omniPclAsking || omniPclQueue.items.empty() || !omniShoulderFocused || omniPclGuest() || editing || omniModalCurrent()) return;
    const std::string url = omniPclQueue.items.front();
    omniPclQueue.items.pop_front();
    omniParLoad();
    const OPAR::Decision d = OPAR::decide(omniParStore, omniParSession, url, SDL_GetTicks());
    if (d.verdict == OPAR::kBlock) {
        notice(OPCL::blockedNotice(d.host.empty() ? OPCL::host(url) : d.host));
        log("pc-links: a link was blocked by parental controls");
        return;
    }
    auto m = std::make_unique<OmniModal>();
    m->kind = omniModalAsk;
    m->title = OPCL::askTitle(OPCL::host(url));
    m->message = OPCL::askBody(url);
    m->okLabel = OPCL::openLabel();
    m->cancelLabel = OPCL::dismissLabel();
    m->ask = [url](bool ok) { omniPclAsking = false; if (ok) omniPclOpen(url); };
    m->focus = 0;   // Dismiss (left) first
    omniPclAsking = true;
    omniModalPush(std::move(m));
}
static void omniPclTick()
{
    if (omniTestMode()) return;
    const uint32_t now = SDL_GetTicks();
    bool full = false;
    if (omniPclPoll.due(now, omniShoulderFocused && !omniPclGuest(), full)) {
        static uint32_t offAt = 0;
        static bool off = false;
        if (!offAt || now - offAt > 60000) { offAt = now ? now : 1; off = access(omniPclOffFlag, F_OK) == 0; }
        const int64_t stamp = off ? -1 : omniPclStamp();
        if (stamp >= 0 && (full || stamp != omniPclStampSeen) && omniPclQueue.room()) {
            omniPclTake();
            omniPclStampSeen = omniPclStamp();
        }
    }
    omniPclAskNext();
}
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniSendLink.h" // OMNI_SEND_LINK_V1: LAN "send a link to Omni" server (no WebKit types)\n',
         '#include "OmniSendLink.h" // OMNI_SEND_LINK_V1: LAN "send a link to Omni" server (no WebKit types)\n'
         '#include "OmniPcLinks.h" /* OMNI_PC_LINKS_V1: links from Setup on the PC: inbox file, link check (pure) */\n'
         '#if __has_include("OmniGuestMode.h") /* OMNI_PC_LINKS_V1: guest mode holds PC links when that patch is in the tree */\n'
         '#include "OmniGuestMode.h"\n'
         '#define OMNI_PCL_HAS_GUEST 1\n'
         '#else\n'
         '#define OMNI_PCL_HAS_GUEST 0\n'
         '#endif\n'
         'namespace OPCL = OmniPcLinks; /* OMNI_PC_LINKS_V1 */\n'),
        ('#include "OmniSendLinkShell.h" // OMNI_SEND_LINK_V1: opens sent links, Browser settings row\n',
         '#include "OmniSendLinkShell.h" // OMNI_SEND_LINK_V1: opens sent links, Browser settings row\n'
         '#include "OmniPcLinksShell.h" /* OMNI_PC_LINKS_V1: "Link from your PC" (Open / Dismiss) */\n'),
        ('    omniSlTick(); // OMNI_SEND_LINK_V1: start the LAN server, open links sent from a phone (UI thread only)\n',
         '    omniSlTick(); // OMNI_SEND_LINK_V1: start the LAN server, open links sent from a phone (UI thread only)\n'
         '    omniPclTick(); /* OMNI_PC_LINKS_V1: the inbox every 5 s while on screen, one question at a time */\n'),
    ],
}


def variants(old0, s):
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
    if h.exists():
        have = h.read_bytes()
        if have == data:
            return name + ': already'
        if MARK.encode() not in have:
            sys.exit('%s exists and is not ours: stopping' % name)
    h.write_bytes(data)
    return name + ': written'


_CPP_TOK = re.compile(r'//[^\n]*|/\*.*?\*/|R"([^()\\\s"]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\\n])*"' + r"|'(?:\\.|[^'\\\n])*'", re.S)


def cpp_code(s):
    """C/C++ text without its // and /* */ comments (string, char and raw string literals kept; newlines kept, so line
    numbers stay): an id or name in another patch's notes is not a use. (As apply_bf_list.py.)"""
    return _CPP_TOK.sub(lambda m: m.group(0) if m.group(0)[0] in 'R"\'' else '\n' * m.group(0).count('\n'), s)


def code_only(src):
    """A sibling apply_*.py without its comments and module docstring (line numbers kept): names mentioned only in its
    notes are not a use. (As apply_bf_list.py.)"""
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
    starts = [0] + [i + 1 for i, c in enumerate(src) if c == '\n']
    out = list(src)
    for (r0, c0), (r1, c1) in cut:
        for i in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
            if out[i] not in '\r\n':
                out[i] = ' '
    return ''.join(out)


def names_free():
    """Before a first apply: no other patch or tree file uses this patch's names."""
    name = re.compile('|'.join(NAMES))
    for f in sorted(HERE.glob('apply_*.py')):
        if f.name == Path(__file__).name:
            continue
        if f.name == 'apply_controls_help.py' or MARK in f.read_text(encoding='utf-8', errors='replace'):   # OMNI_SIBLING_SKIP: the guide quotes names; a patch built on this one uses them
            continue
        m = name.search(code_only(f.read_text(encoding='utf-8', errors='replace')))
        if m:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))
    for f in sorted(root.iterdir()):
        if f.name in MINE or f.suffix not in ('.h', '.cpp', '.inc'):
            continue
        t = f.read_bytes().decode('utf-8', errors='replace')
        m = name.search(cpp_code(t))
        if m and MARK not in t:
            sys.exit('%s already uses %r: pick other names' % (f.name, m.group(0)))


def main():
    for fname, needs in NEEDS.items():
        s = (root / fname).read_bytes().decode('utf-8')
        for need in needs:
            if need not in s:
                sys.exit('%s: %s missing: apply its patch first' % (fname, need))
    if MARK not in (root / 'OmniBrowser.cpp').read_bytes().decode('utf-8'):
        names_free()
    for fname, edits in EDITS.items():   # every anchor is checked before anything is written
        check(fname, edits)
    pure = (HERE / 'OmniPcLinks.h').read_text(encoding='utf-8')
    if MARK not in pure:
        sys.exit('OmniPcLinks.h: %s missing' % MARK)
    msgs = [write_new('OmniPcLinks.h', pure, 'OmniSendLink.h'),
            write_new('OmniPcLinksShell.h', SHELL, 'OmniSendLinkShell.h')]
    msgs += [patch(fname, edits) for fname, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
