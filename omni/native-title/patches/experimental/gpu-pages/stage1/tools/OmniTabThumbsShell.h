// OMNI_TAB_THUMBS_V1: tab thumbnails (shell side). Included from OmniFeatures3.h (inside OmniBrowser.cpp's anonymous
// namespace, before OmniTabSwitcherShell.h, whose tiles draw them). The pure part is OmniTabThumbs.h; the reasons are in
// tools/apply_tab_thumbs.py. Main thread only.
// Capture: only when the user switches away from a tab (activate(), before the page buffer is whitened): the page the
// tab shows now is box-filtered on the CPU into 240 x 135 straight from the page buffer the shell already has (the
// half-size page, or the 4K page buffer), or, in zero-copy mode, from the engine's published frame (broker memory the
// title maps at the same address). Nothing is captured per frame; nothing touches the GPU present.
// Memory only (private tabs too), at most 16 thumbnails (about 2 MB); a closed tab's goes with it.
#pragma once

namespace OTTH = OmniTabThumbs;
static OTTH::Store omniTth;
static unsigned omniTthLogs = 0;

// CPU page: the half-size page while the 4K buffer is stale (OMNI_PERF_A_S5), else the page buffer (both ARGB8888 as
// WKPagePaint writes them: memory B, G, R, A).
static bool omniTthFromCpu(uint32_t* out)
{
    OTTH::Source s;
    if (omniPixelsStale) {
        s.w = (renderWidth + 1) / 2; s.h = (renderPageHeight + 1) / 2;
        if (s.w <= 0 || s.h <= 0 || omniPageSmall.size() < size_t(s.w) * size_t(s.h)) return false;
        s.px = reinterpret_cast<const uint8_t*>(omniPageSmall.data());
    } else {
        s.w = renderWidth; s.h = renderPageHeight;
        if (s.w <= 0 || s.h <= 0 || pixels.size() < size_t(s.w) * size_t(s.h) * 4) return false;
        s.px = pixels.data();
    }
    s.stride = size_t(s.w) * 4;
    s.bgra = true;
    return OTTH::downscale(s, 2, OTTH::pack(0, 0, 0), out);
}
// Zero-copy page (OMNI_GPUPAGES_ZEROCOPY_V1): the engine's last published frame (BGRA, the half-size page), read once
// with one row per thumbnail row (GPU-written memory reads slowly). Same seqlock as omniZcTick; dropped if the engine
// may have reused the buffer meanwhile.
static bool omniTthFromZc(uint32_t* out)
{
    OmniZcCtl* c = omniZc.ctl;
    if (!c) return false;
    const uint32_t s1 = __atomic_load_n(&c->seq, __ATOMIC_ACQUIRE);
    const uint64_t frame = c->frame, address = c->address;
    const uint32_t w = c->width, h = c->height, stride = c->stride;
    const uint32_t s2 = __atomic_load_n(&c->seq, __ATOMIC_ACQUIRE);
    if ((s1 & 1) || s1 != s2 || !OTTH::zcUsable(frame, address, w, h, stride)) return false;
    OTTH::Source s;
    s.px = reinterpret_cast<const uint8_t*>(uintptr_t(address));
    s.stride = stride; s.w = int(w); s.h = int(h); s.bgra = true;
    if (!OTTH::downscale(s, 1, OTTH::pack(0, 0, 0), out)) return false;
    return OTTH::frameKept(frame, __atomic_load_n(&c->frame, __ATOMIC_ACQUIRE));
}
// activate(), first thing: the tab being left keeps the page it shows now. Only when the page buffers / the engine's
// frame were last painted for that tab (omniTthSrc): never a neighbour's picture after a close, never the white page of a
// tab that has not painted since it was shown.
static void omniTthCapture(size_t index)
{
    Tab* t = active();
    const void* painted = omniTthSrc;
    omniTthSrc = nullptr;   // activate() whitens the page buffer next; the next paint / frame marks the new tab
    if (!t || index >= tabs.size() || tabs[index].get() == t || painted != t) return;
    if (t->crashed || omniTestMode() || t->omniPaintHold.holding(SDL_GetTicks())) return;
    const Uint64 t0 = SDL_GetPerformanceCounter();
    std::vector<uint32_t> px(OTTH::kPixels);
    const bool zc = omniZcActive();
    const bool ok = zc ? omniTthFromZc(px.data()) : omniTthFromCpu(px.data());
    omniTth.prune(omniTabAlive);
    if (ok) omniTth.put(t, std::move(px));
    const double ms = 1000.0 * double(SDL_GetPerformanceCounter() - t0) / double(SDL_GetPerformanceFrequency());
    if (omniTthLogs < 6 || (ms >= 2 && omniTthLogs < 40)) {
        ++omniTthLogs;
        fprintf(stderr, "OMNI TAB THUMBS: %s (%s) in %.2f ms; %zu kept, %zu KB\n", ok ? "captured" : "not captured",
            zc ? "zero-copy frame" : omniPixelsStale ? "half-size page" : "page buffer", ms, omniTth.size(), omniTth.bytes() >> 10);
        fflush(stderr);
    }
}
static void omniTthForget(const void* tab) { omniTth.forget(tab); }
static bool omniTthHas(const Tab& t) { return omniTth.find(&t) && canvas && canvas->format->format == SDL_PIXELFORMAT_ABGR8888; }
// The tab's thumbnail fitted to a layout box (nearest pixel: the stored one is already box-filtered); an unloaded tab's
// grey. false: none to draw.
static bool omniTthBlit(const Tab& t, int x, int y, int w, int h)
{
    if (!omniTthHas(t)) return false;
    const OTTH::Store::Entry* e = omniTth.find(&t);
    const bool asleep = omniTmIsUnloaded(t);
    const int bx = physical(x), by = physical(y), bw = physical(w), bh = physical(h);
    const int x0 = std::max(bx, 0), x1 = std::min(bx + bw, canvas->w), y0 = std::max(by, 0), y1 = std::min(by + bh, canvas->h);
    if (bw <= 0 || bh <= 0 || x0 >= x1 || y0 >= y1) return true;
    const std::vector<int> xs = OTTH::spread(bw, OTTH::kW), ys = OTTH::spread(bh, OTTH::kH);
    for (int yy = y0; yy < y1; ++yy) {
        const uint32_t* src = e->px.data() + size_t(ys[size_t(yy - by)]) * OTTH::kW;
        uint32_t* dst = omniRow(yy);
        for (int xx = x0; xx < x1; ++xx) {
            const uint32_t p = src[xs[size_t(xx - bx)]];
            dst[xx] = asleep ? OTTH::grey(p) : p;
        }
    }
    return true;
}
// omniFxDrawPanel: before a tab row's title in the Tabs panel and the Tab memory panel (the rows those panels already
// list: private tabs as today). A tab never left since it opened has its site letter, as the quick tab switcher.
// Returns where the label starts.
static int omniTthRowMark(const OmniFxPanel& p, const OmniFxRow& r, int lx, int y, int h)
{
    if (p.build != omniFxTabsBuild && p.kind != omniTmvKind) return lx;
    if (r.id < 0 || r.id >= int(tabs.size())) return lx;
    const Tab& t = *tabs[size_t(r.id)];
    const int ty = y + (h - OTTH::kRowH) / 2;
    if (omniTthHas(t)) {
        fillRounded(lx - 1, ty - 1, OTTH::kRowW + 2, OTTH::kRowH + 2, 3, omniTheme().line);
        omniTthBlit(t, lx, ty, OTTH::kRowW, OTTH::kRowH);
    } else {
        const std::string url = !t.omniLazyURL.empty() && t.omniLazyURL != "newtab" ? t.omniLazyURL : t.url;
        const std::string site = omniWebURL(url) && !t.omniNewTabPage && !t.omniPagesTab ? url : std::string();
        const OmniTabSwitcher::Rgb c = OmniTabSwitcher::colour(OmniTabSwitcher::colourIndex(site, t.title));
        const SDL_Color col { c.r, c.g, c.b, 255 };
        fillRounded(lx, ty, OTTH::kRowW, OTTH::kRowH, 4, omniTmIsUnloaded(t) ? omniTheme().inkFaint : col);
        omniLabel(t.omniNewTabPage ? std::string("+") : OmniTabSwitcher::letter(site, t.title), lx + OTTH::kRowW / 2.f, ty + OTTH::kRowH / 2.f,
            omniBodyBold, { 255, 255, 255, 255 }, 1);
    }
    return lx + OTTH::kRowW + 14;
}
// The quick tab switcher's tile (OmniTabSwitcherShell.h): the thumbnail with the site letter small in its corner.
// false: no thumbnail (a new tab page, or never left): the switcher draws its site-letter square.
static bool omniTthTile(const Tab& t, int x, int y, int w, int h, SDL_Color badge, const std::string& letter)
{
    if (t.omniNewTabPage || !omniTthHas(t)) return false;
    fillRounded(x - 1, y - 1, w + 2, h + 2, 4, omniTheme().line);
    omniTthBlit(t, x, y, w, h);
    fillRounded(x + 4, y + h - 26, 22, 22, 5, badge);
    omniLabel(letter, x + 15.f, y + h - 15.f, omniSmallBold, { 255, 255, 255, 255 }, 1);
    return true;
}
