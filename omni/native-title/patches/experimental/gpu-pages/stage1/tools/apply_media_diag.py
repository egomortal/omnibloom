"""OMNI_MEDIA_DIAG_V1 (2026-11-13): the Media downloads shortcut still doesn't open its tab on the owner's console, and
nothing records why. Log every step to /data/omni/media-downloads.log (one line each, capped at 256 KB):
  request   the plan Omni made (create / activate / disabled / unavailable / full ...) and the starter's answer
  fetch     every /healthz and launcher request: state (0 complete, 1 refused, 2 failed), HTTP status, body size, ms
  outcome   what the startup check decided
  tick      the completion as the UI loop takes it, the tab-switch decision and the plan it applies
Cheap: a few short lines per press, nothing in the per-frame path unless a completion is waiting.

Apply AFTER apply_media_health_fix.py and apply_media_switch.py.
usage: apply_media_diag.py <engine tree>   (edits engine/entry/OmniMediaDownloads.h and OmniMediaDownloadsHooks.inc)
"""
import re
import sys
from pathlib import Path

MARK = 'OMNI_MEDIA_DIAG_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'


def patch(name, edits, span=None):
    p = root / name
    raw = p.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    s = raw.decode('utf-8')
    if MARK in s:
        return 'already'
    for old, new in edits:
        old, new = old.replace('\n', nl), new.replace('\n', nl)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old[:90]))
        s = s.replace(old, new, 1)
    if span:
        start, end = s.index(span[0]), s.index(span[1])
        body = s[start:end]
        n = body.count('hooks.fetch(')
        if n < 3:
            sys.exit('%s: expected >= 3 hooks.fetch calls in ensureReady, found %d' % (name, n))
        s = s[:start] + body.replace('hooks.fetch(', 'diagFetch(hooks, ') + s[end:]
    p.write_bytes(s.encode('utf-8'))
    return 'applied'


HEADER_ANCHOR = 'inline Outcome ensureReady(const Hooks& hooks, uint64_t& nextLaunchAt, uint16_t* readyPort = nullptr) {'
HEADER_NEW = '''// OMNI_MEDIA_DIAG_V1: one line per step in /data/omni/media-downloads.log (capped; started afresh past 256 KB).
inline void diag(const char* format, ...) {
    char line[512];
    const int head = snprintf(line, sizeof(line), "%llu ", static_cast<unsigned long long>(nowMs()));
    va_list args;
    va_start(args, format);
    const int body = vsnprintf(line + head, sizeof(line) - head - 1, format, args);
    va_end(args);
    size_t length = static_cast<size_t>(head) + (body > 0 ? std::min<size_t>(static_cast<size_t>(body), sizeof(line) - head - 2) : 0);
    line[length++] = '\\n';
    const char* path = "/data/omni/media-downloads.log";
    struct stat st {};
    const bool fresh = stat(path, &st) == 0 && st.st_size > 256 * 1024;
    const int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | (fresh ? O_TRUNC : 0), 0666);
    if (fd < 0) return;
    (void)!write(fd, line, length);
    close(fd);
}
inline HttpResult diagFetch(const Hooks& hooks, uint16_t port, const std::string& path, unsigned timeoutMs) {
    const uint64_t t0 = nowMs();
    HttpResult r = hooks.fetch(port, path, timeoutMs);
    diag("fetch %u%.80s -> state=%d status=%d body=%zu %llums %.60s", unsigned(port), path.c_str(), int(r.state), r.status,
         r.body.size(), static_cast<unsigned long long>(nowMs() - t0), r.body.c_str());
    return r;
}
''' + HEADER_ANCHOR + '''
    diag("ensureReady: card port %u", hooks.port());'''
RUN_OLD = '''        { std::lock_guard<std::mutex> guard(owner->lock); owner->result = std::move(value); }'''
RUN_NEW = '''        diag("outcome %d port %u", int(value.outcome), unsigned(value.port)); // OMNI_MEDIA_DIAG_V1
        { std::lock_guard<std::mutex> guard(owner->lock); owner->result = std::move(value); }'''
INCLUDES_OLD = '#include <utility>'
INCLUDES_NEW = '#include <utility>\n#include <algorithm> // OMNI_MEDIA_DIAG_V1\n#include <cstdarg>\n#include <fcntl.h>\n#include <sys/stat.h>'

HOOK_EDITS = [
    ('''    const auto plan = OmniMediaSection::plan(omniMediaDownloadsEnabled, true, omniMediaTabSnapshot(), link, false);
    if (plan.action != Action::Create && plan.action != Action::Activate) { omniMediaApplyPlan(plan); return; }
    using OmniMediaDownloads::RequestResult;
    switch (OmniMediaDownloads::starter().request(omniMediaDownloadsEnabled, link, false)) {''',
     '''    const auto plan = OmniMediaSection::plan(omniMediaDownloadsEnabled, true, omniMediaTabSnapshot(), link, false);
    OmniMediaDownloads::diag("request: enabled=%d share=%d saved=%d supplied=%d link=%zu plan=%d", int(omniMediaDownloadsEnabled), // OMNI_MEDIA_DIAG_V1
        int(shareCurrentLink), int(saved), int(supplied), link.size(), int(plan.action));
    if (plan.action != Action::Create && plan.action != Action::Activate) { omniMediaApplyPlan(plan); return; }
    using OmniMediaDownloads::RequestResult;
    const auto requested = OmniMediaDownloads::starter().request(omniMediaDownloadsEnabled, link, false);
    OmniMediaDownloads::diag("request: starter answered %d (0 started, 1 disabled, 2 private, 3 invalid, 4 busy, 5 thread error)", int(requested));
    switch (requested) {'''),
    ('''    if (completion.outcome != OmniMediaDownloads::Outcome::Ready) {
        notice(OmniMediaDownloads::message(completion.outcome));''',
     '''    OmniMediaDownloads::diag("tick: outcome %d port %u; tab same=%d privacy same=%d fullscreen=%d (was %d)", int(completion.outcome), // OMNI_MEDIA_DIAG_V1
        unsigned(completion.port), int(active() && active()->omniMediaIdentity == omniMediaOriginIdentity),
        int(active() && active()->omniPrivate == omniMediaOriginPrivate), int(pageFullscreen), int(omniMediaOriginFullscreen));
    if (completion.outcome != OmniMediaDownloads::Outcome::Ready) {
        notice(OmniMediaDownloads::message(completion.outcome));'''),
    ('''        notice("Media downloads is ready: press L1 + R1 to open it.");''',
     '''        OmniMediaDownloads::diag("tick: not switching (another tab, privacy changed or fullscreen)");
        notice("Media downloads is ready: press L1 + R1 to open it.");'''),
    ('''    omniMediaApplyPlan(plan);
}''',
     '''    OmniMediaDownloads::diag("tick: applying plan %d url %.120s", int(plan.action), plan.url.c_str());
    omniMediaApplyPlan(plan);
}'''),
]

REVIEW_EDITS = [
    ("""static void omniLinkDeliver(int destination, const OmniLinkReview::Context& current, const std::string& wire)
{""",
     """static void omniLinkDeliver(int destination, const OmniLinkReview::Context& current, const std::string& wire)
{
    OmniMediaDownloads::diag("review: deliver destination=%d wire=%zu", destination, wire.size()); // OMNI_MEDIA_DIAG_V1"""),
    ("""    if (!dispatched) { omniLinkGate.finish(serial); omniLinkPending = {}; omniLinkOwed = -1; } // OMNI_C52_FIX1: the caller runs the old path""",
     """    if (!dispatched) { omniLinkGate.finish(serial); omniLinkPending = {}; omniLinkOwed = -1; } // OMNI_C52_FIX1: the caller runs the old path
    OmniMediaDownloads::diag("review: begin destination=%d dispatched=%d", destination, int(dispatched)); // OMNI_MEDIA_DIAG_V1"""),
    ("""        const int destination = omniLinkOwed;
        omniLinkOwed = -1;
        if (running) omniMediaDownloadsOpen(destination == omniLinkToShare);""",
     """        const int destination = omniLinkOwed;
        omniLinkOwed = -1;
        OmniMediaDownloads::diag("review: owed press %d answered by the old path", destination); // OMNI_MEDIA_DIAG_V1
        if (running) omniMediaDownloadsOpen(destination == omniLinkToShare);"""),
]
print('OmniMediaDownloads.h', patch('OmniMediaDownloads.h', [(INCLUDES_OLD, INCLUDES_NEW), (HEADER_ANCHOR, HEADER_NEW), (RUN_OLD, RUN_NEW)],
                                    span=('    diag("ensureReady: card port %u", hooks.port());', 'class Starter {')))
print('OmniMediaDownloadsHooks.inc', patch('OmniMediaDownloadsHooks.inc', HOOK_EDITS))
print('OmniNativeLinkReview.inc', patch('OmniNativeLinkReview.inc', REVIEW_EDITS))
