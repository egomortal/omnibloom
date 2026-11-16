#!/usr/bin/env python3
"""OMNI_TEXT_CACHE_CAP_V1 (2026-11-16): byte budget + LRU for the shell's rendered-text cache.

The cache (audit, r-T tree with every patch up to apply_bookmarks_manager.py)
  OmniBrowser.cpp omniTextSurface(id, value, color): a function-static unordered_map<string, SDL_Surface*> + deque
  of keys, key "<face id>|rrggbb|<text>", value = TTF_RenderUTF8_Blended's surface (CPU memory, 32-bit ARGB, freed
  with SDL_FreeSurface; NOT a GPU / SDL_Texture: the shell composes into the `canvas` surface by hand,
  omniBlendSurface). Capped at 256 entries, first in first out. At 4K (displayScale 3: body face 66 px, title 84 px)
  a wide label is ~0.3-0.8 MB, so 256 of them reach ~81 MB (the audit's worst case).
  (The audit's name "textCacheEntries" does not exist in this tree; omniTextWidthPx / omniFit keep only ints /
  short strings, and the text field draws into its own surface, see "not the shared text cache"; both untouched.)

Callers and pointer lifetime
  Exactly two: omniLabel() and text() (OmniBrowser.cpp). Both call omniTextSurface once (omniLabel calls omniFit
  BEFORE it, which does not touch this cache), then blit the surface at once (omniBlitText) and drop the pointer;
  nothing stores it across calls or frames. The entry just returned is the most recent one, and the cap never
  evicts the entry being inserted, so the pointer stays valid until the caller's blit is done.

What changes
  - engine/entry/OmniTextCacheCap.h (pure, no SDL / WebKit; copied from tools/OmniTextCacheCap.h): OTCC::Lru<V>
    (byte + entry-count LRU), OTCC::budgetFor(w, h) = 48 MiB x (w*h)/(3840*2160), at least 16 MiB
    (4K 48 MiB, 1080p / 720p 16 MiB), surfaceBytes(w, h, pitch) = pitch * h.
  - omniTextSurface: the map/deque become the file-static omniTcCache (OTCC::Lru<SDL_Surface*>); a hit moves the
    entry to the front (LRU, was FIFO); on a miss the budget is re-derived from renderWidth x renderHeight (set once
    at start; a change evicts at once) and the new surface is put with its pitch*h bytes; evictions SDL_FreeSurface.
    The 256-entry cap stays. One string larger than the whole budget is kept alone until the next insert.
  - OmniTabMemory.h: the existing "OMNI TABMEM:" line (logged only on tab-memory events / settings, never per
    frame) gets "text_cache=<KiB>/<entries> (budget <KiB>, peak <KiB>, evicted <n>)".
  Names: omniTc*, namespace OmniTextCacheCap (alias OTCC). Panels / UI scale (apply_ui_scale.py) untouched; the
  key line (face id + colour) is unchanged, so a later zoom-in-key edit there still applies.

Anchors (exactly once each; MARK makes each file idempotent):
  OmniBrowser.cpp  the OmniTabSessions.h include line (file scope; review fix: the OmniJank.h line is inside the anonymous namespace);
                   the omniTextSurface signature + its OMNI_SHELL_DRAW_V1 comment + the two static containers;
                   its cache.find line; its emplace / order / FIFO block up to "return surface;".
  OmniTabMemory.h  the two lines of the "OMNI TABMEM:" fprintf in omniTmLog (CRLF file).
Tested by tools/test_text_cache_cap.cpp:
  g++ -std=c++20 -Wall -Wextra -I<tools> test_text_cache_cap.cpp -o t && ./t
usage: apply_text_cache_cap.py <engine tree>   (keeps each file's line endings; re-run prints "already")
"""
import sys
from pathlib import Path

MARK = 'OMNI_TEXT_CACHE_CAP_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'
HEADER = Path(__file__).with_name('OmniTextCacheCap.h')   # kept next to the script so the tests use the same text

EDITS = {
    'OmniBrowser.cpp': [
        # review fix: the OmniJank.h include is INSIDE the anonymous namespace (<list> broke); anchor on a file-scope include.
        ('#include "OmniTabSessions.h" // OMNI_TAB_SESSIONS_V1: named tab sessions, sessions.txt (pure)\n',
         '#include "OmniTabSessions.h" // OMNI_TAB_SESSIONS_V1: named tab sessions, sessions.txt (pure)\n'
         '#include "OmniTextCacheCap.h" // OMNI_TEXT_CACHE_CAP_V1: byte budget + LRU for rendered UI text (pure)\n'),
        ('static SDL_Surface* omniTextSurface(int id, const std::string& value, SDL_Color color)\n'
         '{\n'
         '    // OMNI_SHELL_DRAW_V1: rendering text with SDL_ttf every frame was a large part of the\n'
         "    // shell's per-frame cost; keep the most recent 256 rendered strings.\n"
         '    static std::unordered_map<std::string, SDL_Surface*> cache;\n'
         '    static std::deque<std::string> order;\n',
         '// OMNI_TEXT_CACHE_CAP_V1: the rendered-text cache; its counters are in the "OMNI TABMEM:" line.\n'
         'static OTCC::Lru<SDL_Surface*> omniTcCache;\n'
         'static void omniTcDrop(SDL_Surface* s) { if (s) SDL_FreeSurface(s); }\n'
         'static SDL_Surface* omniTextSurface(int id, const std::string& value, SDL_Color color)\n'
         '{\n'
         '    // OMNI_SHELL_DRAW_V1: rendering text with SDL_ttf every frame was a large part of the\n'
         "    // shell's per-frame cost; keep the most recent 256 rendered strings.\n"
         '    // OMNI_TEXT_CACHE_CAP_V1: ... and at most OTCC::budgetFor(output) bytes, least recently used first out.\n'
         '    // Callers blit the returned surface at once and keep no pointer; the newest entry is never evicted.\n'),
        ('    if (auto found = cache.find(key); found != cache.end()) return found->second;\n',
         '    if (SDL_Surface** found = omniTcCache.find(key)) return *found;   // OMNI_TEXT_CACHE_CAP_V1\n'),
        ('    cache.emplace(key, surface);\n'
         '    order.push_back(key);\n'
         '    if (order.size() > 256) {\n'
         '        auto oldest = cache.find(order.front());\n'
         '        if (oldest != cache.end()) { SDL_FreeSurface(oldest->second); cache.erase(oldest); }\n'
         '        order.pop_front();\n'
         '    }\n'
         '    return surface;\n',
         '    // OMNI_TEXT_CACHE_CAP_V1: the budget follows the output size (set at start; re-checked per miss, cheap).\n'
         '    if (const size_t budget = OTCC::budgetFor(renderWidth, renderHeight); budget != omniTcCache.budget())\n'
         '        omniTcCache.setBudget(budget, omniTcDrop);\n'
         '    omniTcCache.put(key, surface, OTCC::surfaceBytes(surface->w, surface->h, surface->pitch), omniTcDrop);\n'
         '    return surface;\n'),
    ],
    'OmniTabMemory.h': [
        ('    fprintf(stderr, "OMNI TABMEM: %s tabs=%zu loaded=%d limit=%d keep=%d shell_free=%lld MiB (refuse<%d unload<%d) hw_decoders=%d hw_shm=%zu MiB\\n", why, tabs.size(),\n'
         '        omniTmLoadedCount(), omniF3Set.tabLimit, omniF3Set.keepLoaded, omniTmFree, omniF3Set.refuseMiB, omniF3Set.unloadMiB, decoders, shm >> 20);\n',
         '    const OTCC::Stats& tc = omniTcCache.stats(); // OMNI_TEXT_CACHE_CAP_V1\n'
         '    fprintf(stderr, "OMNI TABMEM: %s tabs=%zu loaded=%d limit=%d keep=%d shell_free=%lld MiB (refuse<%d unload<%d) hw_decoders=%d hw_shm=%zu MiB'
         ' text_cache=%zu KiB/%zu (budget %zu KiB, peak %zu KiB, evicted %llu)\\n", why, tabs.size(),\n'
         '        omniTmLoadedCount(), omniF3Set.tabLimit, omniF3Set.keepLoaded, omniTmFree, omniF3Set.refuseMiB, omniF3Set.unloadMiB, decoders, shm >> 20,\n'
         '        tc.bytes >> 10, tc.entries, tc.budget >> 10, tc.peakBytes >> 10, tc.evictions);\n'),
    ],
}


def variants(old0, s):
    """The anchor with the file's own line endings (mixed files: whichever spelling is present)."""
    for e in ('\r\n', '\n'):
        old = old0.replace('\n', e)
        if s.count(old):
            return old, e
    return old0, '\n'


def check(name, edits, mark=MARK):
    s = (root / name).read_bytes().decode('utf-8')
    if mark in s:
        return
    for old0, _ in edits:
        old, _e = variants(old0, s)
        if s.count(old) != 1:
            sys.exit('%s: anchor found %d times: %r' % (name, s.count(old), old0[:90]))


def patch(name, edits, mark=MARK):
    p = root / name
    s = p.read_bytes().decode('utf-8')
    if mark in s:
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


def main():
    if not HEADER.exists():
        sys.exit('%s missing (it ships next to this script)' % HEADER)
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniTextCacheCap.h', HEADER.read_bytes().decode('utf-8'), 'OmniBrowser.cpp')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
