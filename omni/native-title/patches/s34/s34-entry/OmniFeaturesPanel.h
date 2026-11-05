// OMNI_FEATURES_V1: one controller-first panel used by every new page (Options menu, context menu,
// site settings, downloads, bookmarks, tabs, browser settings). Panels stack: B returns to the one
// below, Options closes them all. Drawn with the same helpers and colours as History and Browser
// tools (omniShadow, fillRounded, omniLabel, omniPanelHints), only when the shell redraws.
#pragma once

struct OmniFxRow {
    int id = 0;                    // what the row does (meaning is per panel)
    std::string label, value, detail;
    int icon = -1;                 // omniIcon id, -1 none
    bool enabled = true, danger = false, stepper = false;
};
struct OmniFxPanel;
using OmniFxBuild = void (*)(OmniFxPanel&);
using OmniFxInput = bool (*)(OmniFxPanel&, const OmniFxRow&, int button);   // true: handled
struct OmniFxPanel {
    int kind = 0;
    std::string title, subtitle, corner;
    std::vector<OmniFxRow> rows;
    int sel = 0, scroll = 0;
    int cols = 1, w = 760, rowH = 50, maxVisible = 9;
    int anchorX = -1, anchorY = -1;          // >= 0: shown next to the pointer (context menu)
    OmniFxBuild build = nullptr;
    OmniFxInput input = nullptr;
    std::vector<std::pair<int, const char*>> faces;
    std::string extra;
    std::string link, image, text, page;     // context menu payload
    int mode = 0;                            // panel-specific (bookmarks: 0 bookmarks, 1 shortcuts)
    float scrollAcc = 0;
};
static std::deque<OmniFxPanel> omniFxStack;  // deque: pushing never moves the panels below

static bool omniFxPanelOpen() { return !omniFxStack.empty() && !editing; }   // hidden while the keyboard edits for it
static void omniFxClamp(OmniFxPanel& p)
{
    const int n = int(p.rows.size());
    p.sel = n ? std::clamp(p.sel, 0, n - 1) : 0;
}
static void omniFxRebuild(OmniFxPanel& p) { if (p.build) { p.rows.clear(); p.build(p); } omniFxClamp(p); }
static void omniFxRefresh() { if (!omniFxStack.empty()) omniFxRebuild(omniFxStack.back()); omniShellDirty = true; }
static void omniFxPush(OmniFxPanel p)
{
    omniFxStack.push_back(std::move(p));
    omniFxRebuild(omniFxStack.back());
    // the first enabled row is focused
    auto& q = omniFxStack.back();
    if (q.sel == 0) for (size_t i = 0; i < q.rows.size(); ++i) if (q.rows[i].enabled) { q.sel = int(i); break; }
    omniShellDirty = true;
}
static void omniFxPop() { if (!omniFxStack.empty()) omniFxStack.pop_back(); if (!omniFxStack.empty()) omniFxRebuild(omniFxStack.back()); omniShellDirty = true; }
static void omniFxCloseAll() { omniFxStack.clear(); omniShellDirty = true; }

struct OmniFxGeom { int x, y, w, h, listY, vis, header; };
static OmniFxGeom omniFxGeometry(const OmniFxPanel& p)
{
    OmniFxGeom g {};
    const int n = int(p.rows.size());
    g.header = p.subtitle.empty() ? 64 : 88;
    g.vis = p.cols > 1 ? std::max(1, std::min((n + p.cols - 1) / p.cols, p.maxVisible)) : std::max(1, std::min(n, p.maxVisible)); // OMNI_MQ_NATIVE_V1
    g.w = p.w;
    g.h = g.header + g.vis * p.rowH + 14;
    if (p.anchorX >= 0) {
        g.x = std::clamp(p.anchorX + 18, 16, width - g.w - 16);
        g.y = std::clamp(p.anchorY - 24, 12, std::max(12, height - bottom - g.h - 10));
    } else {
        g.x = (width - g.w) / 2;
        g.y = std::max(10, (height - bottom - g.h) / 2);
    }
    g.listY = g.y + g.header;
    return g;
}
static void omniFxKeepVisible(OmniFxPanel& p, int vis)
{
    if (p.cols > 1) { // OMNI_MQ_NATIVE_V1: scroll is the first visible grid row
        const int rows = (int(p.rows.size()) + p.cols - 1) / p.cols, selectedRow = p.sel / p.cols;
        if (selectedRow < p.scroll) p.scroll = selectedRow;
        if (selectedRow >= p.scroll + vis) p.scroll = selectedRow - vis + 1;
        p.scroll = std::clamp(p.scroll, 0, std::max(0, rows - vis)); return;
    }
    const int n = int(p.rows.size());
    if (p.sel < p.scroll) p.scroll = p.sel;
    if (p.sel >= p.scroll + vis) p.scroll = p.sel - vis + 1;
    p.scroll = std::clamp(p.scroll, 0, std::max(0, n - vis));
}
static void omniFxDrawPanel(OmniFxPanel& p)
{
    omniFxRebuild(p);
    const OmniTheme& T = omniTheme();
    const OmniFxGeom g = omniFxGeometry(p);
    omniFxKeepVisible(p, g.vis);
    omniRectPx({ 0, 0, canvas->w, canvas->h }, { 0, 0, 0, 255 }, p.anchorX >= 0 ? 70 : 110);
    omniShadow(g.x, g.y, g.w, g.h, omniRadius + 2, 22, 160, 6);
    fillRounded(g.x, g.y, g.w, g.h, omniRadius + 2, T.panel);
    const int cornerW = p.corner.empty() ? 0 : omniLabel(p.corner, g.x + g.w - 28, g.y + 34, omniSmall, T.inkFaint, 2);
    omniLabel(p.title, g.x + 28, g.y + 34, omniBodyBold, T.ink, 0, g.w - 70 - cornerW);
    if (!p.subtitle.empty()) omniLabel(p.subtitle, g.x + 28, g.y + 64, omniSmall, T.inkDim, 0, g.w - 56);
    const int n = int(p.rows.size());
    if (p.cols > 1) {
        const int gap = 8, tw = (g.w - 24 - (p.cols - 1) * gap) / p.cols;
        for (int i = p.scroll * p.cols; i < std::min(n, (p.scroll + g.vis) * p.cols); ++i) { // OMNI_MQ_NATIVE_V1
            const OmniFxRow& r = p.rows[i];
            const int c = i % p.cols, row = i / p.cols - p.scroll;
            const int tx = g.x + 12 + c * (tw + gap), ty = g.listY + row * p.rowH, th = p.rowH - gap;
            const bool sel = i == p.sel, on = r.enabled;
            fillRounded(tx, ty, tw, th, omniRadius, sel ? (on ? T.accent : T.key) : T.tab);
            const SDL_Color ink = sel && on ? T.accentInk : on ? (r.danger ? omniBad : T.ink) : T.inkFaint;
            const SDL_Color side = sel && on ? T.accentInk : T.inkDim;
            const float cy = ty + th / 2.f;
            if (r.icon >= 0) omniIcon(r.icon, tx + 24, cy, ink);
            const int vw = r.value.empty() ? 0 : omniLabel(r.value, tx + tw - 14, cy, omniSmall, side, 2, tw / 3);
            omniLabel(r.label, tx + 46, cy, omniBody, ink, 0, tw - 60 - vw);
        }
    } else {
        for (int k = 0; k < g.vis && p.scroll + k < n; ++k) {
            const int i = p.scroll + k;
            const OmniFxRow& r = p.rows[i];
            const int ry = g.listY + k * p.rowH;
            const bool sel = i == p.sel, on = r.enabled;
            if (sel) fillRounded(g.x + 12, ry + 2, g.w - 24, p.rowH - 4, omniRadius, on ? T.accent : T.key);
            const SDL_Color ink = sel && on ? T.accentInk : on ? (r.danger ? omniBad : T.ink) : T.inkFaint;
            const SDL_Color side = sel && on ? T.accentInk : T.inkDim;
            const float cy = ry + p.rowH / 2.f;
            int lx = g.x + 32;
            if (r.icon >= 0) { omniIcon(r.icon, g.x + 42, cy, ink); lx = g.x + 66; }
            int right = 0;
            if (r.stepper && !r.value.empty()) {
                omniIcon(omniIconBack, g.x + g.w - 196, cy, side);
                omniLabel(r.value, g.x + g.w - 118, cy, omniBodyBold, sel && on ? T.accentInk : T.ink, 1, 130);
                omniIcon(omniIconForward, g.x + g.w - 42, cy, side);
                right = 214;
            } else if (!r.value.empty()) right = omniLabel(r.value, g.x + g.w - 32, cy, omniSmall, side, 2, g.w / 3) + 18;
            const int room = g.x + g.w - 32 - right - lx;
            const int lw = omniLabel(r.label, lx, cy, omniBody, ink, 0, r.detail.empty() ? room : std::min(room, room * 3 / 5));
            if (!r.detail.empty() && room - lw > 40) omniLabel(r.detail, lx + lw + 14, cy, omniSmall, side, 0, room - lw - 14);
        }
        if (n > g.vis) {   // scroll position
            const int trackY = g.listY + 4, trackH = g.vis * p.rowH - 8;
            const int thumbH = std::max(24, trackH * g.vis / n), thumbY = trackY + (trackH - thumbH) * p.scroll / std::max(1, n - g.vis);
            fillRounded(g.x + g.w - 8, trackY, 3, trackH, 1, T.line);
            fillRounded(g.x + g.w - 8, thumbY, 3, thumbH, 1, T.inkDim);
        }
    }
    omniPanelHints(p.faces, p.extra.empty() ? nullptr : p.extra.c_str());
}
static void omniFxDraw() { if (omniFxPanelOpen()) omniFxDrawPanel(omniFxStack.back()); }

// Runs the panel's handler for `row`; the handler may push, pop or close panels.
static bool omniFxAct(int row, int b)
{
    if (omniFxStack.empty()) return false;
    OmniFxPanel& p = omniFxStack.back();
    if (row < 0 || row >= int(p.rows.size()) || !p.input) return false;
    const OmniFxRow r = p.rows[row];   // copy: the handler may rebuild the rows
    const bool handled = p.input(p, r, b);
    omniFxRefresh();
    return handled;
}
static bool omniFxButton(int b)
{
    if (omniFxStack.empty()) return false;
    OmniFxPanel& p = omniFxStack.back();
    const int n = int(p.rows.size());
    if (b == SDL_CONTROLLER_BUTTON_START) { omniFxCloseAll(); return true; }
    if (b == SDL_CONTROLLER_BUTTON_B || b == SDL_CONTROLLER_BUTTON_BACK) { omniFxPop(); return true; }
    if (n == 0) return true;
    if (p.cols > 1) {
        const int rowsN = (n + p.cols - 1) / p.cols;
        int c = p.sel % p.cols, r = p.sel / p.cols;
        bool moved = true;
        switch (b) {
        case SDL_CONTROLLER_BUTTON_DPAD_UP: r = (r + rowsN - 1) % rowsN; break;
        case SDL_CONTROLLER_BUTTON_DPAD_DOWN: r = (r + 1) % rowsN; break;
        case SDL_CONTROLLER_BUTTON_DPAD_LEFT: c = (c + p.cols - 1) % p.cols; break;
        case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: c = (c + 1) % p.cols; break;
        default: moved = false; break;
        }
        if (moved) { p.sel = std::min(n - 1, r * p.cols + c); omniShellDirty = true; return true; }
    } else if (b == SDL_CONTROLLER_BUTTON_DPAD_UP || b == SDL_CONTROLLER_BUTTON_DPAD_DOWN) {
        const int d = b == SDL_CONTROLLER_BUTTON_DPAD_UP ? -1 : 1;
        p.sel = n <= 12 ? (p.sel + d + n) % n : std::clamp(p.sel + d, 0, n - 1);
        omniShellDirty = true;
        return true;
    }
    if (omniFxAct(p.sel, b)) return true;
    if (!omniFxStack.empty() && omniFxStack.back().cols == 1) {   // unhandled L1/R1: page up / down
        OmniFxPanel& q = omniFxStack.back();
        const int page = std::max(1, q.maxVisible - 1), m = int(q.rows.size());
        if (b == SDL_CONTROLLER_BUTTON_LEFTSHOULDER) q.sel = std::max(0, q.sel - page);
        if (b == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER) q.sel = std::min(m - 1, q.sel + page);
    }
    return true;   // a panel takes every button while it is open
}
// OMNI_POINTER_CROSS_V1: the row under (x, y), shared by the click, Cross at the pointer and the hover highlight.
// omniFxOutside: off the panel; omniFxNoRow: on the panel but on no row (title, padding, past the last row).
// visibleOnly: the bottom padding of a list does not reach the first row below the visible ones.
enum { omniFxNoRow = -1, omniFxOutside = -2 };
static int omniFxRowAt(const OmniFxPanel& p, const OmniFxGeom& g, int x, int y, bool visibleOnly)
{
    if (x < g.x || x >= g.x + g.w || y < g.y || y >= g.y + g.h) return omniFxOutside;
    if (y < g.listY) return omniFxNoRow;
    int row = -1;
    if (p.cols > 1) {
        const int gap = 8, tw = (g.w - 24 - (p.cols - 1) * gap) / p.cols;
        const int c = (x - g.x - 12) / (tw + gap), r = (y - g.listY) / p.rowH;
        if (x < g.x + 12 || c < 0 || c >= p.cols || r < 0 || r >= g.vis) return omniFxNoRow;
        if ((x - g.x - 12) % (tw + gap) >= tw || (y - g.listY) % p.rowH >= p.rowH - gap) return omniFxNoRow;
        row = (r + p.scroll) * p.cols + c; // OMNI_MQ_NATIVE_V1
    } else {
        const int k = (y - g.listY) / p.rowH;
        if (visibleOnly && k >= g.vis) return omniFxNoRow;
        row = p.scroll + k;
    }
    if (row < 0 || row >= int(p.rows.size())) return omniFxNoRow;
    return row;
}
// OMNI_POINTER_CROSS_V1: the pointer moved: the row under it becomes the highlight (true: changed).
static bool omniFxHover(int x, int y)
{
    if (!omniFxPanelOpen()) return false;
    OmniFxPanel& p = omniFxStack.back();
    const int row = omniFxRowAt(p, omniFxGeometry(p), x, y, true);
    if (row < 0 || row == p.sel) return false;
    p.sel = row;
    return true;
}
static bool omniFxClick(int x, int y)
{
    if (omniFxStack.empty()) return false;
    OmniFxPanel& p = omniFxStack.back();
    const OmniFxGeom g = omniFxGeometry(p);
    const int row = omniFxRowAt(p, g, x, y, omniPtrCross.inCross);
    // OMNI_POINTER_CROSS_V1: a mouse click off the panel closes it as before; Cross there does nothing (Circle closes).
    if (row == omniFxOutside) { if (!omniPtrCross.inCross) omniFxPop(); return true; }
    if (row < 0) return true;
    p.sel = row;
    if (p.rows[row].stepper && p.cols == 1) {   // the arrows of a stepper row change its value
        if (x >= g.x + g.w - 70) { omniFxAct(row, SDL_CONTROLLER_BUTTON_DPAD_RIGHT); return true; }
        if (x >= g.x + g.w - 214 && x < g.x + g.w - 170) { omniFxAct(row, SDL_CONTROLLER_BUTTON_DPAD_LEFT); return true; }
    }
    omniFxAct(row, SDL_CONTROLLER_BUTTON_A);
    return true;
}
static bool omniFxScroll(double amount)
{
    if (omniFxStack.empty()) return false;
    OmniFxPanel& p = omniFxStack.back();
    const int n = int(p.rows.size());
    p.scrollAcc -= float(amount);
    const int step = p.cols > 1 ? p.cols : 1;
    while (p.scrollAcc >= 50) { p.scrollAcc -= 50; p.sel = std::min(n - 1, p.sel + step); }
    while (p.scrollAcc <= -50) { p.scrollAcc += 50; p.sel = std::max(0, p.sel - step); }
    return true;
}
