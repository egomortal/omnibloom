#!/usr/bin/env python3
"""OMNI_PT_4K_PAGECAP_V1 (2026-11-20, owner: "Yes, build it" - step 4K down to 1440p on the hardware instead of failing).

g9l (title decoder gate OMNI_PT_OPEN_GATE_V1) stopped the console hangs (gov8, 4 runs, 0 hangs), but each refused 2160p
open is an MSE error to the page; YouTube ignores decodingInfo / isTypeSupported "no" for 3840x2160 and retried 2160p
up to 5 times before falling to 480p (the stall in gov8 run 4). YouTube does honour its own player's quality range, so:

 1. Web process (OmniMSEPlayer.cpp): omniPt4kPressure() asks the engine starter (OMNI_STARTER_V4, 127.0.0.1:9031,
    "pt\\n" -> "pt <used> <total>") for the kernel page-table count, at most once a second (10 s back-off when the
    starter does not answer). Pressure = used + 450 (a 2160p decoder open, as the title gate counts) >= the line
    (/data/omni/pt-line.txt, default 6400; the title's line).
 2. OmniMSESource.h: MediaSource.isTypeSupported('video/webm; codecs="vp9"; omnipt4k=1') answers that pressure
    (true = a 2160p open would be refused now). Every other type is answered as before.
 3. OmniBrowser.cpp: a shell user script on youtube.com / youtube-nocookie.com checks the probe once a second and, under
    pressure, sets movie_player.setPlaybackQualityRange('hd1440','hd1440') before YouTube opens 2160p (or after a
    refused 2160p open: the video is not advancing). A 2160p stream that is playing is left alone (the title's
    governor watches that one). A new video without pressure gets 'auto' back.
Off: /data/omni/pt-4k-pagecap-off.flag or /data/omni/pt-backstop-off.flag (no pressure is ever reported).
Logged: "OMNI PT 4K PAGECAP: ..." (web process stderr, first 16) and once if the starter cannot be reached.
usage: apply_pt_4k_pagecap.py <engine dir holding entry/>   (child recipe; before the build, CHANGED += the 3 files)"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_4K_PAGECAP_V1'
E = Path(sys.argv[1]) / 'entry'


def load(name):
    p = E / name
    raw = p.read_bytes().decode('utf-8')
    return p, ('\r\n' if '\r\n' in raw else '\n'), raw.replace('\r\n', '\n')


def save(p, nl, s):
    p.write_bytes(s.replace('\n', nl).encode('utf-8'))
    print('applied', p.name)


def once(s, old, name):
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old.strip()[:70]))


# --- 1. OmniMSEPlayer.cpp: the pressure answer -------------------------------------------------------------------
p, nl, s = load('OmniMSEPlayer.cpp')
if MARK not in s:
    INC = '#include <cstdlib> // OMNI_HOLEPUNCH_V7_REV2: getenv (the kill switch)\n'
    once(s, INC, p.name)
    s = s.replace(INC, INC + ''.join('%s // %s\n' % (i, MARK) for i in (
        '#include <sys/socket.h>', '#include <netinet/in.h>', '#include <arpa/inet.h>', '#include <sys/time.h>',
        '#include <time.h>')), 1)
    ANCHOR = '#define SDL_MAIN_HANDLED\n'
    once(s, ANCHOR, p.name)
    FN = ('namespace WebCore {\n'
          '// ' + MARK + ': would a 2160p decoder open cross the page-table line now? (the page script\'s probe)\n'
          'bool omniPt4kPressure()\n'
          '{\n'
          '    static const int line = [] {\n'
          '        if (!access("/data/omni/pt-backstop-off.flag", F_OK) || !access("/data/omni/pt-4k-pagecap-off.flag", F_OK)) return 0;\n'
          '        int v = 6400;\n'
          '        if (FILE* f = fopen("/data/omni/pt-line.txt", "r")) { int x = 0; if (fscanf(f, "%d", &x) == 1 && x >= 5000 && x <= 7600) v = x; fclose(f); }\n'
          '        return v;\n'
          '    }();\n'
          '    if (!line) return false;\n'
          '    static std::atomic<long long> nextAskMs { 0 };\n'
          '    static std::atomic<int> lastUsed { -1 };\n'
          '    timespec ts {}; clock_gettime(CLOCK_MONOTONIC, &ts);\n'
          '    const long long now = (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;\n'
          '    if (now >= nextAskMs.load(std::memory_order_relaxed)) {\n'
          '        nextAskMs.store(now + 1000, std::memory_order_relaxed);\n'
          '        int used = -1, total = 0, err = 0;\n'
          '        const int fd = socket(AF_INET, SOCK_STREAM, 0);\n'
          '        if (fd >= 0) {\n'
          '            timeval tv {}; tv.tv_usec = 300000;\n'
          '            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv); setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);\n'
          '            sockaddr_in a {}; a.sin_family = AF_INET; a.sin_port = htons(9031); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);\n'
          '            if (!connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) && write(fd, "pt\\n", 3) == 3) {\n'
          '                char buf[64] = { 0 }; size_t got = 0; ssize_t r;\n'
          '                while (got < sizeof buf - 1 && (r = read(fd, buf + got, sizeof buf - 1 - got)) > 0) { got += size_t(r); if (memchr(buf, 10, got)) break; }\n'
          '                if (sscanf(buf, "pt %d %d", &used, &total) != 2 || total <= 0) used = -1;\n'
          '            } else err = errno;\n'
          '            close(fd);\n'
          '        } else err = errno;\n'
          '        lastUsed.store(used, std::memory_order_relaxed);\n'
          '        if (used < 0) {\n'
          '            nextAskMs.store(now + 10000, std::memory_order_relaxed);\n'
          '            static std::atomic<bool> said { false };\n'
          '            if (!said.exchange(true)) { fprintf(stderr, "OMNI PT 4K PAGECAP: engine starter gave no page-table count (errno %d); no cap\\n", err); fflush(stderr); }\n'
          '        }\n'
          '    }\n'
          '    const int used = lastUsed.load(std::memory_order_relaxed);\n'
          '    const bool hot = used >= 0 && used + 450 >= line;   // 450 = a 2160p decoder open, as OMNI_PT_OPEN_GATE_V1 counts\n'
          '    static std::atomic<unsigned> logged { 0 };\n'
          '    if (hot && logged.fetch_add(1, std::memory_order_relaxed) < 16) {\n'
          '        fprintf(stderr, "OMNI PT 4K PAGECAP: %d page tables + ~450 for 2160p would reach the line %d: page told to stay at 1440p\\n", used, line);\n'
          '        fflush(stderr);\n'
          '    }\n'
          '    return hot;\n'
          '}\n'
          '}\n\n')
    s = s.replace(ANCHOR, FN + ANCHOR, 1)
    if '#include <cerrno>' not in s and '#include <errno.h>' not in s:
        s = s.replace(INC, INC + '#include <cerrno> // ' + MARK + '\n', 1)
    save(p, nl, s)
else:
    print('already', p.name)

# --- 2. OmniMSESource.h: the probe -----------------------------------------------------------------------------------
p, nl, s = load('OmniMSESource.h')
if MARK not in s:
    OLD = ('inline OmniMedia::Caps::Support omniMSETypeSupport(const ContentType& type)\n{\n')
    once(s, OLD, p.name)
    NEW = ('bool omniPt4kPressure(); // ' + MARK + ' (OmniMSEPlayer.cpp)\n' + OLD +
           '    if (!type.parameter("omnipt4k"_s).isEmpty())   // ' + MARK + ': the page script\'s probe, not a media type\n'
           '        return omniPt4kPressure() ? OmniMedia::Caps::Support::Yes : OmniMedia::Caps::Support::No;\n')
    s = s.replace(OLD, NEW, 1)
    save(p, nl, s)
else:
    print('already', p.name)

# --- 3. OmniBrowser.cpp: the YouTube page script -------------------------------------------------------------------
p, nl, s = load('OmniBrowser.cpp')
if MARK not in s:
    JS = (r"""(function(){if(window.__omniPt4kV1)return;window.__omniPt4kV1=1;"""
          r"""if(!/(^|\.)(youtube\.com|youtube-nocookie\.com)$/.test(location.hostname))return;"""
          r"""var probe='video/webm; codecs="vp9"; omnipt4k=1',capped=false,vid=null,lastT=-1;"""
          r"""function hot(){try{return MediaSource.isTypeSupported(probe);}catch(e){return false;}}"""
          r"""setInterval(function(){"""
          r"""var p=document.getElementById('movie_player');if(!p||typeof p.setPlaybackQualityRange!=='function')return;"""
          r"""var id='';try{var d=p.getVideoData&&p.getVideoData();id=(d&&d.video_id)||'';}catch(e){}"""
          r"""if(id!==vid){vid=id;lastT=-1;if(capped&&!hot()){try{p.setPlaybackQualityRange('auto','auto');}catch(e){}capped=false;}}"""
          r"""if(capped)return;"""
          r"""var q='';try{q=p.getPlaybackQuality();}catch(e){}"""
          r"""var v=p.querySelector('video'),t=v?v.currentTime:-1,moving=!!(v&&!v.paused&&v.readyState>=3&&t>lastT&&lastT>=0);lastT=t;"""
          r"""if((q==='hd2160'||q==='highres')&&moving)return;"""
          r"""if(hot()){try{p.setPlaybackQualityRange('hd1440','hd1440');capped=true;}catch(e){}}"""
          r"""},1000);})();""")
    FN = ('// ' + MARK + ': YouTube retries a refused 2160p decoder open (the title\'s page-table gate) instead of stepping\n'
          '// down, and ignores capability "no" answers; it does honour its player\'s quality range. While a 2160p open would\n'
          '// cross the page-table line (MediaSource probe, OmniMSESource.h), keep the player at 1440p (hardware, HDR).\n'
          'static void omniPt4kPageCapInstall()\n'
          '{\n'
          '    static const char* source = R"JS(' + JS + ')JS";\n'
          '    auto text = adoptWK(WKStringCreateWithUTF8CString(source));\n'
          '    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, false));   // all frames (embeds)\n'
          '    omniBlockerAddShellScript(script.get());\n'
          '}\n\n')
    A1 = '\n// --- layout and drawing ---'
    once(s, A1, p.name)
    s = s.replace(A1, '\n' + FN.rstrip('\n') + '\n' + A1, 1)
    A2 = '        omniSelectInstall(); // OMNI_DIALOGS_V1: <select> menus (not in self-test modes)\n'
    once(s, A2, p.name)
    s = s.replace(A2, A2 + '        omniPt4kPageCapInstall(); // ' + MARK + ': YouTube stays at 1440p while 2160p would not fit\n', 1)
    save(p, nl, s)
else:
    print('already', p.name)
