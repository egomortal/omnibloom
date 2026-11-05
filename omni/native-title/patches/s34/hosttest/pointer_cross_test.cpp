// OMNI_POINTER_CROSS_V1 host test: the real OmniPointerCross.h and the real (patched) OmniFeaturesPanel.h, driven
// through a model of OmniBrowser.cpp's button()/click()/scroll() chain (same order, same OMNI_POINTER_CROSS_V1 lines),
// with the Options menu built exactly as omniFxQuickMenuShow() lays it out (3 x n grid, w 960, rowH 58).
// A wiring check then reads the patched OmniBrowser.cpp and confirms the real shell has those lines where the model has.
// Build: clang++ -std=c++17 -I<entry> pointer_cross_test.cpp ; run: ./a.out <entry>/OmniBrowser.cpp
#if __has_include(<SDL2/SDL.h>)
#include <SDL2/SDL.h>
#else   // minimal stand-ins (values as SDL 2)
#include <cstdint>
struct SDL_Color { uint8_t r, g, b, a; };
struct SDL_Rect { int x, y, w, h; };
enum { SDL_CONTROLLER_BUTTON_A = 0, SDL_CONTROLLER_BUTTON_B = 1, SDL_CONTROLLER_BUTTON_X = 2, SDL_CONTROLLER_BUTTON_Y = 3, SDL_CONTROLLER_BUTTON_BACK = 4,
       SDL_CONTROLLER_BUTTON_START = 6, SDL_CONTROLLER_BUTTON_LEFTSHOULDER = 9, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER = 10,
       SDL_CONTROLLER_BUTTON_DPAD_UP = 11, SDL_CONTROLLER_BUTTON_DPAD_DOWN = 12, SDL_CONTROLLER_BUTTON_DPAD_LEFT = 13, SDL_CONTROLLER_BUTTON_DPAD_RIGHT = 14 };
#endif
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <fstream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

// --- the shell globals and draw helpers OmniFeaturesPanel.h uses (drawing is not under test) ------------------------
static int width = 1280, height = 720, bottom = 44;
static bool editing = false, omniShellDirty = false;
struct OmniTheme { SDL_Color accent, key, tab, accentInk, ink, inkFaint, inkDim, panel, line; };
static const OmniTheme& omniTheme() { static OmniTheme t {}; return t; }
static const SDL_Color omniBad {236, 98, 98, 255};
constexpr int omniRadius = 6;
enum { omniBody, omniBodyBold, omniSmall, omniIconBack = 1, omniIconForward = 2 };
struct { int w = 1280, h = 720; } canvasStore; static auto* canvas = &canvasStore;
static void omniRectPx(SDL_Rect, SDL_Color, int) {}
static void omniShadow(int, int, int, int, int, int, int, int) {}
static void fillRounded(int, int, int, int, int, SDL_Color) {}
static int omniLabel(const std::string&, int, float, int, SDL_Color, int = 0, int = 0) { return 10; }
static void omniIcon(int, float, float, SDL_Color) {}
static void omniPanelHints(const std::vector<std::pair<int, const char*>>&, const char*) {}


#include "OmniPointerCross.h"
#include "OmniFeaturesPanel.h"

// --- model of the shell around the panels (OmniBrowser.cpp order) -----------------------------------------------------
static float pointerX = 640, pointerY = 400;
static bool pointerVisible = true;
static bool mcPage = false;                         // the active tab is the Master Control page (omniMcOrigin)
static std::vector<std::string> mcScripts;          // what omniMcButton sent to window.omniPadController
static std::vector<std::pair<int, int>> pageClicks; // mouse down/up pairs sent to WebKit at the pointer
static std::vector<int> activated;                  // Options rows run (row ids)
static int buttonsToPanel = 0;

static bool overlayOpen() { return omniFxPanelOpen(); }   // the fx layer blocks the page
static bool omniOverlayClick(int x, int y) { return omniFxPanelOpen() && omniFxClick(x, y); }
static bool omniOverlayButton(int b) { if (!omniFxPanelOpen()) return false; ++buttonsToPanel; return omniFxButton(b); }
static bool omniMcButton(int b)   // as OmniBrowser.cpp: not under an overlay; Cross/Circle/D-pad go to the page's script
{
    if (!mcPage || overlayOpen()) return false;
    const char* name = b == SDL_CONTROLLER_BUTTON_A ? "cross" : b == SDL_CONTROLLER_BUTTON_B ? "circle" : b == SDL_CONTROLLER_BUTTON_DPAD_UP ? "up"
        : b == SDL_CONTROLLER_BUTTON_DPAD_DOWN ? "down" : b == SDL_CONTROLLER_BUTTON_DPAD_LEFT ? "left" : b == SDL_CONTROLLER_BUTTON_DPAD_RIGHT ? "right" : nullptr;
    if (!name) return false;
    mcScripts.push_back(name);
    return true;
}
static void click()   // OmniBrowser.cpp click(): overlays first, then (bars aside) a mouse click on the page
{
    if (omniOverlayClick(int(pointerX), int(pointerY))) return;
    if (pointerY >= 120) pageClicks.push_back({ int(pointerX), int(pointerY) });
}
static void button(int b)   // OmniBrowser.cpp button(), the parts on this path
{
#ifndef OMNI_PTR_CROSS_BEFORE   // -DOMNI_PTR_CROSS_BEFORE: s3.1b's button() (the bug), to show the tests catch it
    if (omniPtrCrossRoute(b, pointerVisible)) { { OmniPtrCrossScope scope; click(); } omniShellDirty = true; return; }
#endif
    if (omniMcButton(b)) return;
    if (omniOverlayButton(b)) return;
    if (b == SDL_CONTROLLER_BUTTON_A) click();
}
static void omniPtrHover() { omniFxHover(int(pointerX), int(pointerY)); }
static long omniPtrSelSig() { return omniFxStack.empty() ? 0 : omniFxStack.back().sel + 11; }
static void scroll(double amount)   // right stick / wheel
{
    const long sig = omniPtrSelSig();
    if (omniFxPanelOpen() && omniFxScroll(amount)) { if (omniPtrSelSig() != sig) omniPtrCrossListNav(); return; }
}
static void stickMoveTo(float x, float y) { const float px = pointerX, py = pointerY; pointerX = x; pointerY = y; if (pointerX != px || pointerY != py) { omniPtrCrossMoved(); omniPtrHover(); } }
static void mouseMoveTo(float x, float y) { pointerX = x; pointerY = y; omniPtrCrossMoved(); omniPtrHover(); }

// --- the Options menu as omniFxQuickMenuShow() builds it on a new tab (no earlier page: Back disabled) ---------------
static const char* const quickLabels[] = { "Back", "Forward", "Reload", "Home", "New tab", "Tabs", "Find on page", "Zoom out", "Zoom in",
    "Reset zoom", "Reader view", "Translate", "Bookmark page", "Copy address", "Screenshot", "Page source", "Dark page", "Site settings",
    "Bookmarks", "History", "Downloads", "Apps", "Reopen closed tab", "New private tab", "Browser tools", "Settings", "Browser settings",
    "Controls", "Exit Omni" };
static int idOf(const char* label) { for (int i = 0; i < int(sizeof quickLabels / sizeof *quickLabels); ++i) if (std::string(quickLabels[i]) == label) return i; return -1; }
static void quickBuild(OmniFxPanel& p)
{
    for (int i = 0; i < int(sizeof quickLabels / sizeof *quickLabels); ++i) {
        OmniFxRow r; r.id = i; r.label = quickLabels[i];
        r.enabled = !(r.label == "Back" || r.label == "Forward" || r.label == "Reader view" || r.label == "Translate");
        p.rows.push_back(r);
    }
}
static bool quickInput(OmniFxPanel&, const OmniFxRow& r, int b)   // as omniFxQuickInput: A only; a disabled row does nothing
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    if (!r.enabled) return true;
    activated.push_back(r.id);
    return true;
}
static void openOptions(int selLabelId)
{
    omniFxCloseAll();
    OmniFxPanel p; p.title = "Omni"; p.cols = 3; p.w = 960; p.rowH = 58; p.build = quickBuild; p.input = quickInput;
    omniFxPush(std::move(p));
    omniFxStack.back().sel = selLabelId;
}
static void tileCentre(int row, float& x, float& y)
{
    const OmniFxPanel& p = omniFxStack.back(); const OmniFxGeom g = omniFxGeometry(p);
    const int gap = 8, tw = (g.w - 24 - (p.cols - 1) * gap) / p.cols;
    x = g.x + 12 + (row % p.cols) * (tw + gap) + tw / 2.f; y = g.listY + (row / p.cols) * p.rowH + (p.rowH - gap) / 2.f;
}
static void reset() { omniFxCloseAll(); omniPtrCross = OmniPtrCrossState(); mcPage = false; mcScripts.clear(); pageClicks.clear(); activated.clear(); buttonsToPanel = 0; pointerVisible = true; pointerX = 640; pointerY = 400; }

static int failures = 0, passes = 0;
#define CHECK(cond, what) do { if (cond) { ++passes; printf("  ok   %s\n", what); } else { ++failures; printf("  FAIL %s  (%s:%d)\n", what, __FILE__, __LINE__); } } while (0)

static void testPointerCrossOverApps()
{
    puts("T1 pointer + Cross over Apps (D-pad highlight on Back) runs Apps");
    reset(); openOptions(idOf("Back"));
    float x, y; tileCentre(idOf("Apps"), x, y);
    stickMoveTo(x - 30, y - 10); stickMoveTo(x, y);
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1 && activated[0] == idOf("Apps"), "Apps ran (not the disabled Back)");
    CHECK(omniPtrCross.crossClicks == 1, "Cross ran as a pointer click");
    CHECK(buttonsToPanel == 0, "the panel's D-pad handler was not asked");
}
static void testPointerCrossOverNothing()
{
    puts("T2 pointer + Cross over nothing does nothing");
    reset(); openOptions(idOf("Reload"));
    const OmniFxGeom g = omniFxGeometry(omniFxStack.back());
    stickMoveTo(g.x + 40, g.y + 20);            // the title
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.empty() && omniFxStack.size() == 1, "title: nothing ran, the menu stays open");
    stickMoveTo(5, 5);                           // off the panel
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.empty() && omniFxStack.size() == 1, "off the panel: nothing ran, the menu stays open (a mouse click would close it)");
    CHECK(pageClicks.empty(), "no click reached the page under the menu");
    float x, y; tileCentre(int(omniFxStack.back().rows.size()) - 1, x, y);
    stickMoveTo(x + 330, y);                     // the empty cells right of the last tile (29 tiles in a 3-column grid)
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.empty() && omniFxStack.size() == 1, "empty grid cell: nothing ran");
    CHECK(omniFxStack.back().sel == idOf("Reload"), "the highlight did not move to a non-row");
}
static void testDpadCrossUnchanged()
{
    puts("T3 D-pad + Cross is unchanged");
    reset(); openOptions(idOf("Home"));
    button(SDL_CONTROLLER_BUTTON_DPAD_RIGHT);    // Home -> New tab
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1 && activated[0] == idOf("New tab"), "no pointer motion: Cross runs the D-pad highlight");
    reset(); openOptions(idOf("Reload"));
    float x, y; tileCentre(idOf("Apps"), x, y); stickMoveTo(x, y);
    button(SDL_CONTROLLER_BUTTON_DPAD_DOWN);     // the D-pad takes the lead back: Apps (hovered, column 1) -> Browser tools below it
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1 && activated[0] == idOf("Browser tools"), "after the D-pad, Cross runs the highlight, not the row under the pointer");
    CHECK(!omniPtrCross.active && omniPtrCross.crossClicks == 0, "the pointer no longer leads");
    reset(); openOptions(idOf("Reload")); stickMoveTo(x, y); pointerVisible = false;
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1 && activated[0] == idOf("Apps") && omniPtrCross.crossClicks == 0, "pointer hidden (opacity 0): Cross runs the highlight (hover had moved it to Apps)");
    reset(); openOptions(idOf("Reload")); stickMoveTo(x, y);
    button(SDL_CONTROLLER_BUTTON_B);
    CHECK(omniFxStack.empty(), "Circle closes the menu while the pointer leads");
    reset(); openOptions(idOf("Reload"));
    button(SDL_CONTROLLER_BUTTON_B);
    CHECK(omniFxStack.empty(), "Circle closes the menu in D-pad mode");
}
static void testMouseClickUnchanged()
{
    puts("T4 a real mouse click is unchanged");
    reset(); openOptions(idOf("Back"));
    float x, y; tileCentre(idOf("Apps"), x, y);
    pointerX = x; pointerY = y; click();         // SDL_MOUSEBUTTONDOWN -> click(), no Cross scope
    CHECK(activated.size() == 1 && activated[0] == idOf("Apps"), "mouse click on Apps runs Apps");
    pointerX = 5; pointerY = 5; click();
    CHECK(omniFxStack.empty(), "mouse click off the panel closes it, as before");
    reset(); mcPage = true; pointerX = 300; pointerY = 400; click();
    CHECK(pageClicks.size() == 1 && mcScripts.empty(), "mouse click on the Master Control page reaches the page");
}
static void testMasterControlPointerCross()
{
    puts("T5 Master Control page: pointer + Cross reaches the item under the pointer");
    reset(); mcPage = true;
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(mcScripts.size() == 1 && mcScripts[0] == "cross" && pageClicks.empty(), "D-pad mode: Cross goes to the page's own Cross handler (unchanged)");
    stickMoveTo(512, 333);
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(mcScripts.size() == 1 && pageClicks.size() == 1 && pageClicks[0] == std::make_pair(512, 333), "pointer mode: a click at the pointer, the page handler not asked");
    button(SDL_CONTROLLER_BUTTON_B);
    CHECK(mcScripts.size() == 2 && mcScripts[1] == "circle", "Circle still goes to the page in pointer mode");
    button(SDL_CONTROLLER_BUTTON_DPAD_DOWN); button(SDL_CONTROLLER_BUTTON_A);
    CHECK(mcScripts.size() == 4 && mcScripts[3] == "cross" && pageClicks.size() == 1, "after the D-pad, Cross goes to the page handler again");
    reset(); mcPage = true; openOptions(idOf("Back"));   // Options open over the Master Control page
    float x, y; tileCentre(idOf("Apps"), x, y); stickMoveTo(x, y);
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1 && activated[0] == idOf("Apps") && mcScripts.empty() && pageClicks.empty(), "Options over the Master Control page: pointer + Cross runs Apps");
}
static void testHover()
{
    puts("T6 the highlight follows the pointer");
    reset(); openOptions(idOf("Reload"));
    float x, y; tileCentre(idOf("History"), x, y); stickMoveTo(x, y);
    CHECK(omniFxStack.back().sel == idOf("History"), "stick: hovering History highlights it");
    tileCentre(idOf("Settings"), x, y); mouseMoveTo(x, y);
    CHECK(omniFxStack.back().sel == idOf("Settings"), "mouse: hovering Settings highlights it");
    const OmniFxGeom g = omniFxGeometry(omniFxStack.back()); stickMoveTo(g.x + 40, g.y + 20);
    CHECK(omniFxStack.back().sel == idOf("Settings"), "off the rows: the highlight stays");
    tileCentre(idOf("Back"), x, y); stickMoveTo(x, y);
    CHECK(omniFxStack.back().sel == idOf("Back"), "a disabled row is highlighted too (Cross on it does what it does: nothing)");
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.empty(), "Cross on the disabled Back does nothing");
    button(SDL_CONTROLLER_BUTTON_DPAD_RIGHT);
    CHECK(omniFxStack.back().sel == idOf("Forward"), "the D-pad moves on from the hovered row");
    // a list: the right stick moves the highlight away from the pointer: Cross follows the highlight
    reset(); omniFxCloseAll();
    OmniFxPanel p; p.title = "List"; p.build = [](OmniFxPanel& q) { for (int i = 0; i < 20; ++i) { OmniFxRow r; r.id = 500 + i; r.label = "row"; q.rows.push_back(r); } };
    p.input = quickInput; omniFxPush(std::move(p));
    const OmniFxGeom lg = omniFxGeometry(omniFxStack.back());
    stickMoveTo(lg.x + 100, lg.listY + 2 * 50 + 25);
    CHECK(omniFxStack.back().sel == 2, "list: hovering row 3 highlights it");
    scroll(-120);                                 // right stick down: the highlight moves 2 rows
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1 && activated[0] == 504 && !omniPtrCross.active, "a scroll that moved the highlight: Cross runs the highlight");
    stickMoveTo(lg.x + 100, lg.listY + 9 * 50 + 5);    // bottom padding below the 9 visible rows
    CHECK(omniFxStack.back().sel == 4, "list padding: no hover onto the hidden 10th row");
    button(SDL_CONTROLLER_BUTTON_A);
    CHECK(activated.size() == 1, "list padding: Cross does nothing");
}

// --- wiring: the real shell has the lines the model has -----------------------------------------------------------------
static std::string slurp(const char* path) { std::ifstream f(path, std::ios::binary); std::stringstream s; s << f.rdbuf(); return s.str(); }
static bool has(const std::string& s, const char* what) { return s.find(what) != std::string::npos; }
static void testWiring(const char* browserPath, const char* panelPath)
{
    puts("W  the patched OmniBrowser.cpp / OmniFeaturesPanel.h are wired as the model");
    const std::string b = slurp(browserPath), p = slurp(panelPath);
    CHECK(!b.empty() && !p.empty(), "sources read");
    const size_t at = b.find("void button(int button)\n{\n");
    const size_t route = b.find("if (omniPtrCrossRoute(button, omniPtrAlpha() > 0))", at), saved = b.find("if (omniSavedButton(button))", at),
                 pages = b.find("if (omniPagesButton(button))", at), mc = b.find("if (omniMcButton(button))", at), ov = b.find("if (omniOverlayButton(button))", at);
    CHECK(at != std::string::npos && route != std::string::npos && route < saved && saved < pages && pages < mc && mc < ov, "button(): the pointer route comes before Saved, Pages, Master Control and overlays");
    CHECK(has(b, "{ OmniPtrCrossScope scope; click(); }"), "button(): Cross runs click() inside the Cross scope");
    CHECK(has(b, "mouse(kWKEventMouseMove); omniPtrCrossMoved(); omniPtrHover(); } // OMNI_POINTER_CROSS_V1"), "SDL_MOUSEMOTION: the pointer leads and hovers");
    CHECK(has(b, "if (pointerX != omniPx || pointerY != omniPy) { omniPtrCrossMoved(); omniPtrHover(); }"), "stick tick: a moved pointer leads and hovers");
    CHECK(has(b, "if (omniOverlayScroll(amount)) { if (omniPtrSelSig() != omniPtrSig) omniPtrCrossListNav(); return; }"), "scroll(): a list scroll that moved the highlight hands the lead back");
    CHECK(has(b, "!omniPtrCross.inCross && (x < omniMenuX()"), "Browser tools: Cross off the menu does not close it");
    CHECK(has(b, "else if (event.type == SDL_MOUSEBUTTONDOWN && event.button.button == SDL_BUTTON_LEFT) click();"), "a real mouse button still calls click() directly");
    CHECK(has(p, "if (row == omniFxOutside) { if (!omniPtrCross.inCross) omniFxPop(); return true; }"), "omniFxClick: off the panel pops for a mouse click only");
}

int main(int argc, char** argv)
{
    testPointerCrossOverApps();
    testPointerCrossOverNothing();
    testDpadCrossUnchanged();
    testMouseClickUnchanged();
    testMasterControlPointerCross();
    testHover();
    if (argc > 2) testWiring(argv[1], argv[2]); else { ++failures; puts("W  FAIL: no source paths given"); }
    printf("OMNI_POINTER_CROSS_V1 host test: %d passed, %d failed: %s\n", passes, failures, failures ? "FAIL" : "PASS");
    return failures ? 1 : 0;
}
