#!/usr/bin/env python3
"""OMNI_PT_GENTLE_V1 (2026-11-26, after OMNI_PT_WATCHDOG_V1): a gentler page-table guard that also works in the in-app mode.

Console (gbp12 gates Lnav3 / Lytapp-213312, owner session 11-24): the watchdog stopped the SHOWN page process at 6,624-6,718
page tables, also when another (background) tab was the one that grew, and in the in-app mode it could do nothing at all:
WKPageGetProcessIdentifier answers the synthetic pid 0x7ffffffe there, kill() -> ESRCH, nothing freed.

Same line (6,600 default, pt-watchdog-line.txt), same count thread. Over the line, one step every 6 s:
  1. a background tab with a loaded web page is discarded (silent tabs before tabs playing sound): its own page process is
     stopped when it has one (not shared with the shown tab), otherwise it is sent to about:blank; either way it loads
     its page again when shown (omniLazyURL, also what the session file keeps).
  2. the shown tab, separate page process: stopped exactly as before (20 s between stops, same log line).
  3. the shown tab, in-app (no process to stop): JavaScript garbage collection + YouTube one quality step down
     (hd2160 -> hd1440 -> hd1080 -> hd720 ...); after two such steps still over the line: the tab goes to about:blank for
     4 s and then loads its page again, with a notice (at most once a minute, garbage collection only in between). Steps reset once the count is 150 under the line.
Kill switch: /data/omni/pt-gentle-off.flag (the V1 watchdog as it was).
usage: apply_pt_gentle.py <title tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_GENTLE_V1'
p = Path(sys.argv[1]) / 'engine/entry/OmniBrowser.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)
if 'OMNI_PT_WATCHDOG_V1' not in s:
    sys.exit('apply OMNI_PT_WATCHDOG_V1 first')

OLD = ('    const int used = omniPtWdUsed.load(std::memory_order_relaxed);\n'
       '    if (used < line) return;\n'
       '    static Uint32 lastStop = 0;\n'
       '    const Uint32 now = SDL_GetTicks();\n'
       '    if (lastStop && now - lastStop < 20000) return;\n'
       '    Tab* tab = active();\n'
       '    if (!tab || !tab->page || tab->crashed) return;\n'
       '    const auto pid = WKPageGetProcessIdentifier(tab->page);\n'
       '    if (pid <= 0 || pid == getpid()) return;\n'
       '    lastStop = now;\n')
if s.count(OLD) != 1:
    sys.exit('anchor found %d times' % s.count(OLD))

YTJS = (r"""(function(){try{var p=document.getElementById('movie_player');if(!p||!p.getPlaybackQuality)return 'no player';"""
        r"""var L=['highres','hd2160','hd1440','hd1080','hd720','large','medium','small','tiny'],q=p.getPlaybackQuality(),i=L.indexOf(q);"""
        r"""if(i<0||i>=L.length-1)return 'at '+q;var n=L[i+1];"""
        r"""if(p.setPlaybackQualityRange)p.setPlaybackQualityRange(n,n);else if(p.setPlaybackQuality)p.setPlaybackQuality(n);"""
        r"""return q+' -> '+n;}catch(e){return 'error';}})()""")

NEW = ('    const int used = omniPtWdUsed.load(std::memory_order_relaxed);\n'
       '    // ' + MARK + ' (see tools/apply_pt_gentle.py)\n'
       '    static const bool gentle = access("/data/omni/pt-gentle-off.flag", F_OK) != 0;\n'
       '    static Tab* gPendTab = nullptr; static std::string gPendURL; static Uint32 gPendAt = 0; static int gSteps = 0;\n'
       '    const Uint32 gNow = SDL_GetTicks();\n'
       '    if (gPendTab && int32_t(gNow - gPendAt) >= 0) {   // the in-app shown tab sent to about:blank: its page again\n'
       '        Tab* t = gPendTab; gPendTab = nullptr;\n'
       '        bool alive = false; for (auto& x : tabs) if (x.get() == t) alive = true;\n'
       '        if (alive) { if (t == active()) navigate(gPendURL); else t->omniLazyURL = gPendURL; }\n'
       '        fprintf(stderr, "OMNI PT GENTLE: page loaded again (%s)\\n", alive ? "tab open" : "tab gone"); fflush(stderr);\n'
       '    }\n'
       '    if (used >= 0 && used < line - 150) gSteps = 0;\n'
       '    if (used < line) return;\n'
       '    if (gentle) {\n'
       '        static Uint32 gLast = 0;\n'
       '        if (gLast && gNow - gLast < 6000) return;\n'
       '        Tab* shown = active();\n'
       '        const int apid = shown && shown->page ? int(WKPageGetProcessIdentifier(shown->page)) : -1;\n'
       '        auto synthetic = [](int pid) { return pid <= 0 || pid == int(getpid()) || pid >= 0x7ffffff0; };\n'
       '        auto webPage = [](const std::string& u) { return u.rfind("https://", 0) == 0 || u.rfind("http://", 0) == 0; };\n'
       '        Tab* victim = nullptr; int best = -1; size_t idx = 0;\n'
       '        for (size_t i = 0; i < tabs.size(); ++i) {\n'
       '            Tab* t = tabs[i].get();\n'
       '            if (t == shown || !t->page || t->crashed || !t->omniLazyURL.empty() || !webPage(t->url) || t == gPendTab) continue;\n'
       '            const int score = t->omniTaBadge ? 0 : 1;   // silent tabs first\n'
       '            if (score > best) { best = score; victim = t; idx = i; }\n'
       '        }\n'
       '        if (victim) {\n'
       '            gLast = gNow;\n'
       '            const int vpid = int(WKPageGetProcessIdentifier(victim->page));\n'
       '            victim->omniLazyURL = victim->url;   // loads again when shown; the session keeps it\n'
       '            if (!synthetic(vpid) && vpid != apid) {\n'
       '                const int rc = kill(vpid, SIGKILL);\n'
       '                fprintf(stderr, "OMNI PT GENTLE: %d page tables >= line %d: background tab %zu discarded, its page process %d stopped (rc %d)\\n", used, line, idx, vpid, rc);\n'
       '            } else {\n'
       '                auto blank = adoptWK(WKURLCreateWithUTF8CString("about:blank")); WKPageLoadURL(victim->page, blank.get());\n'
       '                fprintf(stderr, "OMNI PT GENTLE: %d page tables >= line %d: background tab %zu discarded (about:blank, shared process)\\n", used, line, idx);\n'
       '            }\n'
       '            fflush(stderr);\n'
       '            return;\n'
       '        }\n'
       '        if (!shown || !shown->page || shown->crashed || gPendTab) return;\n'
       '        if (synthetic(apid)) {   // in-app: no process to stop\n'
       '            gLast = gNow;\n'
       '            if (context.get()) WKContextGarbageCollectJavaScriptObjects(context.get());\n'
       '            if (gSteps < 2) {\n'
       '                ++gSteps;\n'
       '                const bool yt = shown->url.find("youtube.com/") != std::string::npos;\n'
       '                fprintf(stderr, "OMNI PT GENTLE: %d page tables >= line %d: in-app step %d: garbage collection%s\\n", used, line, gSteps, yt ? " + YouTube quality step down" : "");\n'
       '                fflush(stderr);\n'
       '                if (yt) {\n'
       '                    auto script = adoptWK(WKStringCreateWithUTF8CString(R"JS(' + YTJS + ')JS"));\n'
       '                    WKPageEvaluateJavaScriptInMainFrame(shown->page, script.get(), nullptr, [](WKTypeRef result, WKErrorRef, void*) {\n'
       '                        std::string r = "no answer";\n'
       '                        if (result && WKGetTypeID(result) == WKStringGetTypeID()) { char b[96] = { 0 }; WKStringGetUTF8CString(static_cast<WKStringRef>(result), b, sizeof b); r = b; }\n'
       '                        fprintf(stderr, "OMNI PT GENTLE: YouTube quality %s\\n", r.c_str()); fflush(stderr);\n'
       '                    });\n'
       '                }\n'
       '                return;\n'
       '            }\n'
       '            static Uint32 gLastBlank = 0;   // at most one page reload a minute; only garbage collection in between\n'
       '            if (gLastBlank && gNow - gLastBlank < 60000) return;\n'
       '            gLastBlank = gNow;\n'
       '            gPendTab = shown; gPendURL = shown->url; gPendAt = gNow + 4000;\n'
       '            auto blank = adoptWK(WKURLCreateWithUTF8CString("about:blank")); WKPageLoadURL(shown->page, blank.get());\n'
       '            notice("Low on memory: page reloading");\n'
       '            fprintf(stderr, "OMNI PT GENTLE: %d page tables >= line %d: in-app shown tab to about:blank for 4 s, then its page again\\n", used, line);\n'
       '            fflush(stderr);\n'
       '            return;\n'
       '        }\n'
       '    }\n'
       '    static Uint32 lastStop = 0;\n'
       '    const Uint32 now = SDL_GetTicks();\n'
       '    if (lastStop && now - lastStop < 20000) return;\n'
       '    Tab* tab = active();\n'
       '    if (!tab || !tab->page || tab->crashed) return;\n'
       '    const auto pid = WKPageGetProcessIdentifier(tab->page);\n'
       '    if (pid <= 0 || pid == getpid()) return;\n'
       '    lastStop = now;\n')
s = s.replace(OLD, NEW, 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name, MARK)
