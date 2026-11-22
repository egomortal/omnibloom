#!/usr/bin/env python3
"""OMNI_PT_WATCHDOG_V1 (2026-11-20, owner: "how do we just fix it period i dont wanna run around").

The console hangs when the kernel CPU page-table pool (8,192) gets past ~6,770 (lowest hang seen 6,771). Earlier guards each
closed one road (decoder open gate, pace-queue ceiling, YouTube 1440p cap); gov9 run 2 hung through another one (the
YouTube page process grew 752 -> 1,900 MiB while YouTube retried). This guard watches the number itself:

 1. A background thread asks the engine starter (OMNI_STARTER_V4, 127.0.0.1:9031, "pt") for the count once a second
    (the UI thread never waits on a socket).
 2. The browser tick (title, OmniBrowser.cpp): count >= the watchdog line (default 6,600; /data/omni/pt-watchdog-line.txt
    6000..7200; off with /data/omni/pt-watchdog-off.flag) -> the shown tab's page process is stopped exactly like
    the shell's own RELOAD TEST (kill(WKPageGetProcessIdentifier, SIGKILL)). That frees the page's memory (~1 GB on
    4K YouTube, ~500 page tables) and, through the web process, its video decoders. The normal crash path then runs:
    OMNI_CRASH_AUTORELOAD_V1 reloads the page once with its notice; a 2nd stop on the same site within 5 min shows the
    panel (no loop). 20 s between stops. Logged "OMNI PT WATCHDOG: ...".
 3. The YouTube 1440p page script (OMNI_PT_4K_PAGECAP_V1 part 3) is installed HERE: the browser shell runs in the title,
    so the copy added to the child build was never injected (gov9: no PAGECAP line). Its probe answer comes from the
    child (81c1fe7b+). Adds a saved-quality fallback: under pressure at document start, localStorage
    yt-player-quality = 1440 (YouTube's own remembered choice), so the first pick is 1440p even without the player API.
usage: apply_pt_watchdog.py <title tree root holding engine/entry>"""
import sys
from pathlib import Path

MARK = 'OMNI_PT_WATCHDOG_V1'
p = Path(sys.argv[1]) / 'engine/entry/OmniBrowser.cpp'
raw = p.read_bytes().decode('utf-8')
nl = '\r\n' if '\r\n' in raw else '\n'
s = raw.replace('\r\n', '\n')
if MARK in s:
    print('already', p.name); sys.exit(0)


def once(old):
    if s.count(old) != 1:
        sys.exit('%s: anchor found %d times: %r' % (p.name, s.count(old), old.strip()[:70]))


# includes (first #include line)
first = s.index('#include ')
s = s[:first] + ''.join('%s  // %s\n' % (i, MARK) for i in (
    '#include <sys/socket.h>', '#include <netinet/in.h>', '#include <arpa/inet.h>', '#include <sys/time.h>',
    '#include <signal.h>', '#include <atomic>', '#include <thread>')) + s[first:]

JS = (r"""(function(){if(window.__omniPt4kV1)return;window.__omniPt4kV1=1;"""
      r"""if(!/(^|\.)(youtube\.com|youtube-nocookie\.com)$/.test(location.hostname))return;"""
      r"""var probe='video/webm; codecs="vp9"; omnipt4k=1',capped=false,vid=null,lastT=-1;"""
      r"""function hot(){try{return MediaSource.isTypeSupported(probe);}catch(e){return false;}}"""
      r"""try{if(hot()&&window.top===window){var n=Date.now();localStorage.setItem('yt-player-quality',JSON.stringify({data:JSON.stringify({quality:1440,previousQuality:2160}),expiration:n+86400000,creation:n}));}}catch(e){}"""
      r"""setInterval(function(){"""
      r"""var p=document.getElementById('movie_player');if(!p)return;"""
      r"""var id='';try{var d=p.getVideoData&&p.getVideoData();id=(d&&d.video_id)||'';}catch(e){}"""
      r"""var h=hot();"""
      r"""if(id!==vid){vid=id;lastT=-1;if(capped&&!h){try{p.setPlaybackQualityRange&&p.setPlaybackQualityRange('auto','auto');}catch(e){}capped=false;}}"""
      r"""if(capped||!h)return;"""
      r"""var q='';try{q=p.getPlaybackQuality?p.getPlaybackQuality():'';}catch(e){}"""
      r"""var v=p.querySelector('video'),t=v?v.currentTime:-1,moving=!!(v&&!v.paused&&v.readyState>=3&&t>lastT&&lastT>=0);lastT=t;"""
      r"""if((q==='hd2160'||q==='highres')&&moving)return;"""
      r"""try{if(p.setPlaybackQualityRange){p.setPlaybackQualityRange('hd1440','hd1440');capped=true;}else if(p.setPlaybackQuality){p.setPlaybackQuality('hd1440');capped=true;}}catch(e){}"""
      r"""},1000);})();""")

FN = ('// ' + MARK + ': kernel page-table watchdog (see tools/apply_pt_watchdog.py) + the YouTube 1440p page script\n'
      'static std::atomic<int> omniPtWdUsed { -1 };\n'
      'static int omniPtWdLine()\n'
      '{\n'
      '    static const int line = [] {\n'
      '        if (!access("/data/omni/pt-watchdog-off.flag", F_OK)) return 0;\n'
      '        int v = 6600;\n'
      '        if (FILE* f = fopen("/data/omni/pt-watchdog-line.txt", "r")) { int x = 0; if (fscanf(f, "%d", &x) == 1 && x >= 6000 && x <= 7200) v = x; fclose(f); }\n'
      '        return v;\n'
      '    }();\n'
      '    return line;\n'
      '}\n'
      'static int omniPtWdAsk()\n'
      '{\n'
      '    const int fd = socket(AF_INET, SOCK_STREAM, 0);\n'
      '    if (fd < 0) return -1;\n'
      '    timeval tv {}; tv.tv_usec = 300000;\n'
      '    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv); setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);\n'
      '    sockaddr_in a {}; a.sin_family = AF_INET; a.sin_port = htons(9031); a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);\n'
      '    int used = -1, total = 0;\n'
      '    if (!connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) && write(fd, "pt\\n", 3) == 3) {\n'
      '        char buf[64] = { 0 }; size_t got = 0; ssize_t r;\n'
      '        while (got < sizeof buf - 1 && (r = read(fd, buf + got, sizeof buf - 1 - got)) > 0) { got += size_t(r); if (memchr(buf, 10, got)) break; }\n'
      '        if (sscanf(buf, "pt %d %d", &used, &total) != 2 || total <= 0) used = -1;\n'
      '    }\n'
      '    close(fd);\n'
      '    return used;\n'
      '}\n'
      'static void omniPtWdTick()\n'
      '{\n'
      '    const int line = omniPtWdLine();\n'
      '    if (!line || omniTestMode()) return;\n'
      '    static bool started = false;\n'
      '    if (!started) {\n'
      '        started = true;\n'
      '        std::thread([] { for (;;) { omniPtWdUsed.store(omniPtWdAsk(), std::memory_order_relaxed); sleep(1); } }).detach();\n'
      '        fprintf(stderr, "OMNI PT WATCHDOG: on, line %d page tables\\n", line); fflush(stderr);\n'
      '    }\n'
      '    const int used = omniPtWdUsed.load(std::memory_order_relaxed);\n'
      '    if (used < line) return;\n'
      '    static Uint32 lastStop = 0;\n'
      '    const Uint32 now = SDL_GetTicks();\n'
      '    if (lastStop && now - lastStop < 20000) return;\n'
      '    Tab* tab = active();\n'
      '    if (!tab || !tab->page || tab->crashed) return;\n'
      '    const auto pid = WKPageGetProcessIdentifier(tab->page);\n'
      '    if (pid <= 0 || pid == getpid()) return;\n'
      '    lastStop = now;\n'
      '    const int rc = kill(pid, SIGKILL);\n'
      '    fprintf(stderr, "OMNI PT WATCHDOG: %d page tables >= line %d: page process %d stopped (rc %d) to keep the console from hanging\\n", used, line, int(pid), rc);\n'
      '    fflush(stderr);\n'
      '}\n'
      'static void omniPt4kPageCapInstall()\n'
      '{\n'
      '    static const char* source = R"JS(' + JS + ')JS";\n'
      '    auto text = adoptWK(WKStringCreateWithUTF8CString(source));\n'
      '    auto script = adoptWK(WKUserScriptCreateWithSource(text.get(), kWKInjectAtDocumentStart, false));   // all frames (embeds)\n'
      '    omniBlockerAddShellScript(script.get());\n'
      '}\n')
A1 = '\n// --- layout and drawing ---'
once(A1)
s = s.replace(A1, '\n' + FN + A1, 1)
A2 = '        omniSelectInstall(); // OMNI_DIALOGS_V1: <select> menus (not in self-test modes)\n'
once(A2)
s = s.replace(A2, A2 + '        omniPt4kPageCapInstall(); // ' + MARK + ': YouTube stays at 1440p while 2160p would not fit\n', 1)
A3 = '    omniEverydayTick(); // OMNI_EVERYDAY_V1: re-issued loads, session save (background write)\n'
once(A3)
s = s.replace(A3, A3 + '    omniPtWdTick(); // ' + MARK + ': page-table watchdog\n', 1)
p.write_bytes(s.replace('\n', nl).encode('utf-8'))
print('applied', p.name)
