#!/usr/bin/env python3
"""OMNI_CONTROLS_HELP_V1 (2026-11-16): an on-screen Controls guide.

What the user sees
  - Options (top level) has a "Controls" tile (value "All shortcuts"), placed before "Now playing"; Browser settings has a
    "Show controls guide" row after "Bottom button bar"; the older Options > Settings > Controls row opens the same guide.
  - The guide is full screen: "Controls", a row of section tabs (Browsing, Keyboard, Tabs, Video, Quick actions, Reading
    list, Downloads, History), and two columns of rows: the button pictures the hint bar uses (PlayStation or Xbox, as
    set), the action, and a dim note (when / where). L1 / R1 (or D-pad left / right) switch sections, Circle goes back to
    the panel it was opened from, Options closes everything; D-pad up / down page only if a section ever outgrows a page.
  - Context: the section of the panel it was opened from comes first (Tabs, Sessions, Reading list, Downloads, Now
    playing / Sleep timer, page menu, History; full-screen video), else the panel seen in the last 30 s, else Browsing.
  - First launch after this update: once, 5 s after start on a quiet screen, the notice
    "Press Options -> Controls for all shortcuts" ("Menu" with Xbox labels) for 8 s; /data/omni/controls-hint-shown.flag
    keeps it from coming back.

Content: one table in OmniControlsHelp.h (pure); every row names its handler. Verified against the patched tree
(button(), omniKbButton, omniKwButton, omniSuggestButton, omniKbTick, omniKbShortcutButton, omniFxTabsInput,
omniPtTabsInput, omniTsListInput, omniFxButton, the full-screen keys in button(), omniYtTvButton, omniFxButtonEvent,
omniQaShotChord, omniL2Chord, omniRlInput, omniFxDownloadsInput, omniSavedAxis, omniShoulderButton, omniHistoryButton,
omniFindButton). No playback-speed row: the tree has no speed control yet.

Files
  new  OmniControlsHelp.h        pure: table, glyph names / tokens, section order, context, layout, hint
                                 (tests: tools/test_controls_help.cpp)
  new  OmniControlsHelpShell.h   the overlay (input layer inserted first, draw layer appended last), entry rows, tick
  OmniBrowser.cpp       after the OmniMediaControls.h include line: the pure include
  OmniFeatures3.h       after the OmniMediaControlsShell.h include (the last shell include, so every panel it recognises
                        is declared; other helpers add after OmniSiteClearShell.h, which is left alone);
                        after the omniSecTick line of omniF3Tick: omniChTick
  OmniQuickMenu.h       omniControlsShow opens the guide (declarations before it); before the omniNpQuickRow line: the
                        tile; before the omniNpQuickInput line: its input
  OmniBrowserSettings.h before omniFxHomeEdit: declarations; after the "Bottom button bar" row: the row; before the
                        omniSlRowId input line: its input
Ids: Options tile 8200 (8000-8005 groups, 8100 Now playing); Browser settings row 836 (845-891, 900+ taken).
Each anchor once, CRLF / LF kept per file, idempotent (MARK per file). Apply after apply_media_controls.py and
apply_sleep_timer.py.
"""
import sys
from pathlib import Path

MARK = 'OMNI_CONTROLS_HELP_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'

PURE = r'''// OMNI_CONTROLS_HELP_V1: the pure part of the Controls guide (Options > Controls, Browser settings > Show controls guide):
// one table of every controller shortcut, grouped by context, plus section order, layout math and the first-launch hint.
// No SDL, no WebKit. Shell side: OmniControlsHelpShell.h.
//
// KEEP THIS TABLE CURRENT: every row names the handler that implements it (`where`). When a button's action changes in
// one of those handlers, change its row here; tests/test_controls_help.cpp checks the table's shape, not the code.
// Text tokens such as {Cross} or {Options} become the PlayStation or Xbox name (expand()).
#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace OmniControlsHelp {

constexpr const char* kFlagPath = "/data/omni/controls-hint-shown.flag";   // the first-launch hint was shown
constexpr int kQuickTileId = 8200;     // Options (top level) tile; Options' group rows are 8000-8005, Now playing 8100
constexpr int kSettingsRowId = 836;    // Browser settings row (845-891 and 900+ are taken there)
constexpr uint32_t kHintDelayMs = 5000;    // the hint waits this long after start, and for a quiet screen
constexpr uint32_t kHintShowMs = 8000;     // how long the hint stays up
constexpr uint32_t kRecentMs = 30000;      // a panel closed this recently still decides the first section

enum Section : int { kBrowsing, kKeyboard, kTabs, kVideo, kQuick, kReading, kDownloads, kHistory, kImage, kSectionCount };

// Where the guide was opened from (the panel under it, or the last panel seen).
enum From : int { kFromNone, kFromOptions, kFromSettings, kFromKeyboard, kFromTabs, kFromSessions, kFromFullscreen, kFromNowPlaying,
    kFromSleep, kFromContextMenu, kFromReading, kFromDownloads, kFromHistory, kFromCount };

enum Glyph : int {
    gNone, gCross, gCircle, gSquare, gTriangle, gL1, gR1, gShoulders /* L1 / R1 pair */, gL2, gR2, gL3, gR3,
    gOptions, gCreate, gTouchpad, gDpad, gDpadV, gDpadH, gDpadUp, gLStick, gRStick, gGlyphCount
};

struct Entry {
    int section;
    int keys[3];          // up to three glyphs, gNone-terminated
    char join;            // between the keys: '+' (together) or '/' (either)
    bool hold;            // "Hold" before the first key
    const char* action;   // what it does (tokens allowed)
    const char* note;     // when / where ("" none; tokens allowed)
    const char* where;    // the handler that implements it (for whoever updates the table)
};

// clang-format off
inline const std::vector<Entry>& table()
{
    static const std::vector<Entry> t = {
    // --- Browsing: button(), OmniBrowser.cpp, a page with no panel open ---------------------------------------------
    { kBrowsing, { gCross }, 0, false, "Click", "", "button()" },
    { kBrowsing, { gCircle }, 0, false, "Back", "", "button() omniFxBack" },
    { kBrowsing, { gCircle }, 0, true, "Back history", "Earlier / later pages; D-pad picks, {Cross} goes. Options > Browse too", "omniBflButtonEvent (OMNI_BF_LIST_V1)" },
    { kBrowsing, { gTriangle }, 0, false, "Address bar", "In a page's text box: type there", "button() editAddress / editPage" },
    { kBrowsing, { gSquare }, 0, false, "New tab", "", "button() newTab" },
    { kBrowsing, { gShoulders }, 0, false, "Previous / next tab", "", "button() activate" },
    { kBrowsing, { gR3 }, 0, false, "Close tab", "A pinned tab asks first", "button() omniPtMayClose + closeTab" },
    { kBrowsing, { gL3 }, 0, false, "Add this page to shortcuts", "Unless an add-on quick switch uses {L3}", "button() omniShortcutAddCurrent / omniAdShortcut" },
    { kBrowsing, { gTouchpad }, 0, false, "Translate page", "Unless an add-on quick switch uses the touchpad", "button() omniTranslateToggle / omniAdShortcut" },
    { kBrowsing, { gDpadH }, 0, false, "Back / forward", "Browser settings > D-pad left / right can switch tabs", "omniFxDpadSide (OmniQuickMenu.h)" },
    { kBrowsing, { gDpadV }, 0, false, "Scroll", "Browser settings > Scroll speed", "button() scroll" },
    { kBrowsing, { gDpad }, 0, false, "Move the focus ring between links", "Settings > D-pad navigation; nothing that way: scrolls", "omniOspn* (OMNI_SPATIAL_NAV_V1)" },
    { kBrowsing, { gCross }, 0, false, "Open the ringed link or button", "D-pad navigation; a text box opens the keyboard", "omniOspn* (OMNI_SPATIAL_NAV_V1)" },
    { kBrowsing, { gLStick }, 0, false, "Move the pointer", "", "OmniPointerFeel.h" },
    { kBrowsing, { gRStick }, 0, false, "Scroll in any direction", "Browser settings > Scroll speed", "OmniPointerFeel.h (wheel / side)" },
    { kBrowsing, { gL2, gRStick }, '+', false, "Page up / down", "Keep pushed: top / bottom", "omniScpStick (OMNI_SCROLL_PLUS_V1)" },
    { kBrowsing, { gOptions }, 0, false, "Options menu", "{Options} again closes it", "button() omniFxQuickMenuShow" },
    { kBrowsing, { gCreate }, 0, false, "Browser settings", "", "button() omniFxSettingsShow (OMNI_SETTINGS_CREATE_V1)" },
    { kBrowsing, { gShoulders }, 0, false, "Find bar: previous / next match", "D-pad left / right too", "omniFindButton (OMNI_FIND_PLUS_V1)" },
    { kBrowsing, { gTriangle }, 0, false, "Find bar: search for something else", "Options > More > Find on page opens the bar", "omniFindButton" },
    { kBrowsing, { gSquare }, 0, false, "Find bar: Match case on / off", "", "omniFindButton (OMNI_FIND_PLUS_V1)" },
    { kBrowsing, { gCircle }, 0, false, "Find bar: close", "Escape too; clears the highlights", "omniFindButton (OMNI_FIND_PLUS_V1)" },
    // --- Address bar & keyboard: omniKbButton, omniKwButton, omniSuggestButton, omniKbTick, omniKbShortcutButton ------
    { kKeyboard, { gDpad }, 0, false, "Move between keys", "The left stick too", "omniKbButton / tick() stick repeat" },
    { kKeyboard, { gCross }, 0, false, "Type the key", "Hold on a letter for accents; D-pad picks, Circle cancels", "omniKbButton (accents: apply_kb_layouts.py)" },
    { kKeyboard, { gSquare }, 0, false, "Delete", "Hold to delete whole words", "omniKbButton" },
    { kKeyboard, { gTriangle }, 0, false, "Space", "", "omniKbButton" },
    { kKeyboard, { gOptions }, 0, false, "Go", "", "omniKbButton omniKbGoKey" },
    { kKeyboard, { gCircle }, 0, false, "Close the keyboard", "{Create} too", "button() dismissKeyboard" },
    { kKeyboard, { gShoulders }, 0, false, "Cursor left / right", "", "omniKbButton omniKbMove(0)" },
    { kKeyboard, { gL2, gR2 }, '/', false, "Cursor by word", "", "omniKbTick omniKbMove(1)" },
    { kKeyboard, { gRStick }, 0, false, "Cursor left / right, scroll up / down", "", "omniKbTick" },
    { kKeyboard, { gL3 }, 0, false, "Shift, then Caps lock", "", "omniKbButton omniKbShiftKey" },
    { kKeyboard, { gR3 }, 0, false, "Symbols / letters", "Numbers in number fields", "omniKbButton omniKbLayerKey" },
    { kKeyboard, { gTouchpad }, 0, false, "Sites page (address bar)", "In a page's text box: edit tools", "omniKbButton omniKbSitesKey / omniKbToolsKey" },
    { kKeyboard, { gTouchpad }, 0, false, "Clipboard history: Edit > Clips", "Last 10; {Cross} pastes, {Square} removes. Options > Clipboard", "omniClhKb* (OMNI_CLIP_HISTORY_V1)" },
    { kKeyboard, { gDpadUp }, 0, false, "Word suggestions", "From the top row; {Cross} uses the word", "omniKwButton (OMNI_KB_WORDS_V1)" },
    { kKeyboard, { gDpadUp }, 0, false, "Address suggestions", "Above the words; {Cross} or {Triangle} opens one", "omniSuggestButton" },
    { kKeyboard, { gSquare }, 0, false, "Sites page: remove a shortcut", "", "omniKbShortcutButton" },
    { kKeyboard, { gR3 }, 0, false, "Sites page: translate this page", "", "omniKbShortcutButton" },
    { kKeyboard, { gShoulders }, 0, false, "Sites page: back to the letters", "{Triangle} and the touchpad too", "omniKbShortcutButton" },
    { kKeyboard, { gR3 }, 0, false, "Emoji: symbols, then the smiley key", "The last key of the symbols' last row", "omniKbEmoji (OMNI_KB_EMOJI_V1)" },
    { kKeyboard, { gDpad }, 0, false, "Emoji page: choose", "{Cross} inserts, {Square} deletes, {Triangle} letters", "omniKemButton" },
    { kKeyboard, { gShoulders }, 0, false, "Emoji page: previous / next category", "", "omniKemButton" },
    // --- Tabs panel (Options > Browse > Tabs): omniFxTabsInput, omniPtTabsInput, omniTsTabsInput, omniTsListInput ---
    { kTabs, { gCross }, 0, false, "Switch to the tab", "", "omniFxTabsInput" },
    { kTabs, { gSquare }, 0, false, "Close the tab", "A pinned tab asks first", "omniFxTabsInput" },
    { kTabs, { gTriangle }, 0, false, "Mute / unmute the tab", "", "omniFxTabsInput omniTaToggle (OMNI_TAB_AUDIO_V1)" },
    { kTabs, { gDpadH }, 0, false, "Pin / unpin the tab", "Not for private tabs", "omniPtTabsInput (OMNI_PINNED_TABS_V1)" },
    { kTabs, { gDpadV }, 0, false, "Choose a tab or a row", "", "omniFxButton" },
    { kTabs, { gShoulders }, 0, false, "Page up / down", "", "omniFxButton" },
    { kTabs, { gCross }, 0, false, "Save these tabs as a session", "The row below the tabs", "omniTsTabsInput (OMNI_TAB_SESSIONS_V1)" },
    { kTabs, { gCross }, 0, false, "Sessions: open a saved session", "The Sessions row", "omniTsListInput" },
    { kTabs, { gTriangle }, 0, false, "Sessions: rename", "", "omniTsListInput" },
    { kTabs, { gSquare }, 0, false, "Sessions: delete", "Press twice", "omniTsListInput" },
    { kTabs, { gCross }, 0, true, "Tab menu", "Group, duplicate, move, close others, reload / bookmark all", "omniTgHoldFire + omniTacMenuInput (OMNI_TAB_ACTIONS_V1)" },
    { kTabs, { gCross }, 0, false, "Tab menu: Move left / right", "Press again; stays among pinned / its group", "omniTacMove" },
    { kTabs, { gCross }, 0, false, "Tab menu: Close other tabs / to the right", "Asks once; pinned tabs stay", "omniTacAskClose" },
    { kTabs, { gCircle }, 0, false, "Back", "", "omniFxButton" },
    // --- Video: full-screen keys in button(), Now playing, Sleep timer, YouTube TV mode ----------------------------
    { kVideo, { gSquare }, 0, false, "Play / pause", "Full-screen video (YouTube's keys)", "button() omniFullscreenKey k" },
    { kVideo, { gShoulders }, 0, false, "Back / forward 10 seconds", "Full-screen video (YouTube's keys)", "button() omniFullscreenKey j / l" },
    { kVideo, { gDpadH }, 0, false, "Back / forward 5 seconds", "Full-screen video", "button() omniFullscreenKey arrows" },
    { kVideo, { gDpadV }, 0, false, "Volume up / down", "Full-screen video", "button() omniFullscreenKey arrows" },
    { kVideo, { gTriangle }, 0, false, "Captions on / off", "Full-screen video (YouTube's keys)", "button() omniFullscreenKey c" },
    { kVideo, { gL3 }, 0, false, "Mute", "Full-screen video (YouTube's keys)", "button() omniFullscreenKey m" },
    { kVideo, { gCircle }, 0, false, "Leave full screen", "{Options} and {Create} too", "button() WKViewRequestExitFullScreen" },
    { kVideo, { gR2, gShoulders }, '+', false, "Back / forward 1 minute", "Full-screen video", "OmniVideoKeys::plan (OMNI_VIDEO_KEYS_V1)" },
    { kVideo, { gR2, gDpadH }, '+', false, "Frame back / forward", "Full-screen video", "OmniVideoKeys::plan" },
    { kVideo, { gR2, gTriangle }, '+', false, "Next captions track", "Full-screen video", "OmniVideoKeys::plan" },
    { kVideo, { gR2, gSquare }, '+', false, "Next audio track", "Full-screen video, two or more tracks", "OmniVideoKeys::plan" },
    { kVideo, { gR3 }, 0, false, "Show position, speed, captions", "Full-screen video", "OmniVideoKeys::plan kInfo" },
    { kVideo, { gTouchpad }, 0, false, "Next playback speed", "Full-screen video; shows it too", "omniSpShortcut (OMNI_PLAYBACK_SPEED_V1) + kInfo" },
    { kVideo, { gCross }, 0, false, "Resume prompt: choose", "D-pad left / right picks", "OmniVideoKeys::plan kConfirm / fBoxKey" },
    { kVideo, { gOptions }, 0, false, "Now playing", "Options tile while a tab plays: pause, tracks, 10 s, mute", "omniNpQuickRow / omniNpInput (OMNI_MEDIA_CONTROLS_V1)" },
    { kVideo, { gOptions }, 0, false, "Sleep timer", "Options > Now playing > Sleep timer: 15-90 min or end of video", "omniStOpen (OMNI_SLEEP_TIMER_V1)" },
    { kVideo, { gDpad }, 0, false, "YouTube TV mode: the remote's arrows", "{Cross} is Enter, {Circle} is Back", "omniYtTvButton (OMNI_YOUTUBE_TV_V1)" },
    // --- Quick actions: omniFxButtonEvent (hold Cross), omniQaShotChord, omniL2Chord --------------------------------
    { kQuick, { gCross }, 0, true, "Link or page menu", "Over the page", "omniFxButtonEvent (OMNI_FEATURES_V1)" },
    { kQuick, { gCross }, 0, true, "Open the link in a background tab", "Then {Cross}: the link menu's first row ({R1} shows it)", "omniFxContextBuild omniCxBackground" },
    { kQuick, { gCross }, 0, true, "Select text", "Over text: page menu > Select text", "omniTslContextRow (OMNI_TEXT_SELECT_V1)" },
    { kQuick, { gDpadH }, 0, false, "Select text: extend by a word", "D-pad up / down: by a line", "omniTslButton" },
    { kQuick, { gCross }, 0, false, "Select text: Copy, Search, address bar, QR", "", "omniTslActions" },
    { kQuick, { gCircle }, 0, false, "Select text: cancel", "", "omniTslButton" },
    { kQuick, { gL2, gR3 }, '+', false, "Screenshot", "Downloads > Saved > Screenshots (not in private tabs)", "omniQaShotChord (OMNI_QUICK_ACTIONS_V1)" },
    { kQuick, { gL2, gSquare }, '+', false, "Copy the text, link or page address", "", "omniL2Chord omniL2Copy (OMNI_L2_CHORDS_V1)" },
    { kQuick, { gL2, gTriangle }, '+', false, "Paste into the text box", "Pick the text box with {Cross} first", "omniL2Chord omniL2Paste" },
    { kQuick, { gL2, gCross }, '+', false, "Options menu", "", "omniL2Chord" },
    { kQuick, { gL2, gCircle }, '+', false, "Browser settings", "", "omniL2Chord" },
    { kQuick, { gL2, gDpadV }, '+', false, "Zoom this site in / out", "Remembered for the site", "omniL2Chord (OMNI_SITE_ZOOM_V1)" },
    { kQuick, { gL2, gShoulders }, '+', false, "Quick tab switcher (most recent first)", "Keep {L2} held: {L1} / {R1} or D-pad choose, let go; {Circle} cancels", "omniTswChord (OMNI_TAB_SWITCHER_V1)" },
    // --- Reading list (Options > Browse > Reading list): omniRlInput -----------------------------------------------
    { kReading, { gOptions }, 0, false, "Save page for later", "Options > Browse, or the page menu (hold {Cross})", "omniRlQuickAction / omniRlContextAction" },
    { kReading, { gCross }, 0, false, "Open the saved copy", "", "omniRlInput" },
    { kReading, { gTriangle }, 0, false, "Open the live page", "", "omniRlInput" },
    { kReading, { gSquare }, 0, false, "Delete", "Asks first", "omniRlInput" },
    { kReading, { gCircle }, 0, false, "Back", "", "omniFxButton" },
    // --- Downloads (Options > More > Downloads): omniFxDownloadsInput; Media downloads: omniSavedAxis, omniShoulderButton
    { kDownloads, { gCross }, 0, false, "Open the file", "", "omniFxDownloadsInput" },
    { kDownloads, { gSquare }, 0, false, "Delete a file / cancel a download", "Deleting asks first", "omniFxDownloadsInput" },
    { kDownloads, { gTriangle }, 0, false, "Copy to a USB drive", "When Omni runs as its own app", "omniFxDownloadsInput (OMNI_FILES_BROKER_V1)" },
    { kDownloads, { gCircle }, 0, false, "Back", "", "omniFxButton" },
    { kDownloads, { gCross }, 0, true, "Save link / Save image", "Page menu over a link or an image", "omniFxContextInput omniCxSaveLink / omniCxSaveImage" },
    { kDownloads, { gL2 }, 0, false, "Saved links", "Media downloads on: tap {L2}", "omniSavedAxis / omniL2Track omniSavedL2" },
    { kDownloads, { gR2 }, 0, false, "Send this page to Media downloads", "Media downloads on", "omniSavedAxis Prefill" },
    { kDownloads, { gL1, gR1 }, '+', false, "Open Media downloads", "Media downloads on: press both", "omniShoulderButton OpenSection" },
    // --- History (Options > Browse > History): omniHistoryButton ---------------------------------------------------
    { kHistory, { gDpadV }, 0, false, "Choose", "", "omniHistoryButton" },
    { kHistory, { gDpadH }, 0, false, "Previous / next day", "", "omniHistoryButton OHP::dayJump" },
    { kHistory, { gShoulders }, 0, false, "Page up / down", "", "omniHistoryButton" },
    { kHistory, { gCross }, 0, false, "Open", "", "omniHistoryButton" },
    { kHistory, { gSquare }, 0, false, "Delete this visit", "", "omniHistoryButton omniHistoryDelete" },
    { kHistory, { gTriangle }, 0, false, "Search", "", "omniHistoryButton omniHpSearch" },
    { kHistory, { gR3 }, 0, false, "Delete everything from this site", "", "omniHistoryButton omniHpDeleteSite" },
    { kHistory, { gCircle }, 0, false, "Clear the search, then close", "", "omniHistoryButton" },
    // --- Image viewer (hold Cross on a picture > View image): omniImvButton, omniImvTick (OMNI_IMAGE_VIEWER_V1) ---------
    { kImage, { gCross }, 0, true, "View image", "Page menu over a picture: its first row", "omniImvContextRow" },
    { kImage, { gL2, gR2 }, '/', false, "Zoom out / in", "Hold for more", "omniImvTick OIMV::triggerZoom" },
    { kImage, { gDpadV }, 0, false, "Zoom in / out a step", "", "omniImvButton" },
    { kImage, { gLStick }, 0, false, "Move the picture", "", "omniImvTick OIMV::stickPan" },
    { kImage, { gDpadH }, 0, false, "Previous / next picture", "{L1} / {R1} too", "omniImvButton" },
    { kImage, { gCross }, 0, false, "Fit / actual size", "", "omniImvButton" },
    { kImage, { gSquare }, 0, false, "Save", "To Downloads", "omniImvButton (Save image)" },
    { kImage, { gCircle }, 0, false, "Close", "", "omniImvButton" },
    };
    return t;
}
// clang-format on

inline const char* sectionTitle(int s)
{
    static const char* const t[kSectionCount] = { "Browsing", "Keyboard", "Tabs", "Video", "Quick actions", "Reading list", "Downloads", "History", "Image viewer" };
    return s >= 0 && s < kSectionCount ? t[s] : "";
}
// Where the section's controls apply (tokens allowed).
inline const char* sectionWhere(int s)
{
    static const char* const t[kSectionCount] = {
        "A web page, no panel open", "Address bar and text boxes", "Options > Browse > Tabs", "Full-screen video, Now playing",
        "Over a web page", "Options > Browse > Reading list", "Options > More > Downloads", "Options > Browse > History",
        "Hold {Cross} on a picture > View image" };
    return s >= 0 && s < kSectionCount ? t[s] : "";
}

// The PlayStation or Xbox name of a glyph (pills and text).
inline const char* glyphName(int g, bool ps)
{
    switch (g) {
    case gCross: return ps ? "Cross" : "A";
    case gCircle: return ps ? "Circle" : "B";
    case gSquare: return ps ? "Square" : "X";
    case gTriangle: return ps ? "Triangle" : "Y";
    case gL1: return ps ? "L1" : "LB";
    case gR1: return ps ? "R1" : "RB";
    case gShoulders: return ps ? "L1 / R1" : "LB / RB";
    case gL2: return ps ? "L2" : "LT";
    case gR2: return ps ? "R2" : "RT";
    case gL3: return ps ? "L3" : "LS";
    case gR3: return ps ? "R3" : "RS";
    case gOptions: return ps ? "Options" : "Menu";
    case gCreate: return ps ? "Create" : "View";
    case gTouchpad: return "Touchpad";
    case gDpad: return "D-pad";
    case gDpadV: return "D-pad up / down";
    case gDpadH: return "D-pad left / right";
    case gDpadUp: return "D-pad up";
    case gLStick: return "Left stick";
    case gRStick: return "Right stick";
    default: return "";
    }
}
// Glyphs drawn as a text pill (the others are the controller pictures the hint bar uses).
inline bool glyphIsPill(int g) { return g == gL2 || g == gR2 || g == gL3 || g == gR3 || g == gTouchpad; }

// {Cross}, {Options}, ... -> the controller's names. Unknown tokens stay as written.
inline std::string expand(const std::string& text, bool ps)
{
    static const struct { const char* token; int glyph; } tokens[] = {
        { "{Cross}", gCross }, { "{Circle}", gCircle }, { "{Square}", gSquare }, { "{Triangle}", gTriangle }, { "{L1}", gL1 },
        { "{R1}", gR1 }, { "{L2}", gL2 }, { "{R2}", gR2 }, { "{L3}", gL3 }, { "{R3}", gR3 }, { "{Options}", gOptions }, { "{Create}", gCreate } };
    std::string out;
    out.reserve(text.size());
    for (size_t i = 0; i < text.size();) {
        bool hit = false;
        if (text[i] == '{')
            for (const auto& t : tokens) {
                const std::string k(t.token);
                if (text.compare(i, k.size(), k) == 0) { out += glyphName(t.glyph, ps); i += k.size(); hit = true; break; }
            }
        if (!hit) out += text[i++];
    }
    return out;
}

inline std::vector<int> entriesOf(int section)
{
    std::vector<int> v;
    const auto& t = table();
    for (size_t i = 0; i < t.size(); ++i) if (t[i].section == section) v.push_back(int(i));
    return v;
}

// The section a context shows first. Options and Browser settings themselves are browsing.
inline int sectionFor(int from)
{
    switch (from) {
    case kFromKeyboard: return kKeyboard;
    case kFromTabs: case kFromSessions: return kTabs;
    case kFromFullscreen: case kFromNowPlaying: case kFromSleep: return kVideo;
    case kFromContextMenu: return kQuick;
    case kFromReading: return kReading;
    case kFromDownloads: return kDownloads;
    case kFromHistory: return kHistory;
    default: return kBrowsing;
    }
}
inline bool specific(int from) { return from > kFromSettings && from < kFromCount; }
// Remembered as "the last panel" for a guide opened soon after it closed. Not the keyboard: it opens for every address.
inline bool rememberable(int from) { return specific(from) && from != kFromKeyboard; }
// direct: the panel under the guide; recent: the last panel seen before it, ageMs ago.
inline int firstSection(int direct, int recent, uint32_t ageMs)
{
    if (specific(direct)) return sectionFor(direct);
    if (specific(recent) && ageMs <= kRecentMs) return sectionFor(recent);
    return kBrowsing;
}
// The tab order: `first`, then the others in their usual order.
inline std::vector<int> order(int first)
{
    if (first < 0 || first >= kSectionCount) first = kBrowsing;
    std::vector<int> v { first };
    for (int s = 0; s < kSectionCount; ++s) if (s != first) v.push_back(s);
    return v;
}
inline int step(int index, int dir, int count) { return count <= 0 ? 0 : ((index + dir) % count + count) % count; }

// --- layout (layout pixels, 1280 x 720; the hint bar is the bottom 32) -------------------------------------------------
constexpr int kScreenW = 1280, kScreenH = 720, kHintBarH = 32;
constexpr int kMarginX = 48;
constexpr int kTitleY = 40;                 // title / section-where line centre
constexpr int kTabsY = 70, kTabsH = 40;     // section tabs
constexpr int kListTop = 128;               // first entry row
constexpr int kRowH = 48;                   // two lines: action, note (11 rows a column)
constexpr int kColGap = 32;
constexpr int kGlyphColW = 200;             // the button pictures; the text starts after it
constexpr int kListBottom = kScreenH - kHintBarH - 8;

struct Tab { int x, w; };
inline Tab tabRect(int index, int count)
{
    const int room = kScreenW - 2 * kMarginX, gap = 8;
    const int w = count > 0 ? (room - (count - 1) * gap) / count : room;
    return { kMarginX + index * (w + gap), w };
}
inline int tabAt(int x, int y, int count)
{
    if (y < kTabsY || y >= kTabsY + kTabsH) return -1;
    for (int i = 0; i < count; ++i) { const Tab t = tabRect(i, count); if (x >= t.x && x < t.x + t.w) return i; }
    return -1;
}

struct Layout { int cols, rowsPerCol, perPage, pages, colW; };
inline Layout layout(int n, int maxCols = 2)
{
    Layout L {};
    L.rowsPerCol = std::max(1, (kListBottom - kListTop) / kRowH);
    L.cols = n <= L.rowsPerCol ? 1 : std::max(1, maxCols);
    L.perPage = L.cols * L.rowsPerCol;
    L.pages = n <= 0 ? 1 : (n + L.perPage - 1) / L.perPage;
    L.colW = (kScreenW - 2 * kMarginX - (L.cols - 1) * kColGap) / L.cols;
    if (L.cols == 1) L.colW = std::min(L.colW, 760);   // one column stays readable
    return L;
}
struct Slot { int page, col, row, x, y; };
inline Slot place(int i, const Layout& L)
{
    Slot s {};
    s.page = i / L.perPage;
    const int k = i % L.perPage;
    s.col = k / L.rowsPerCol;   // column-major: read down, then across
    s.row = k % L.rowsPerCol;
    s.x = kMarginX + s.col * (L.colW + kColGap);
    s.y = kListTop + s.row * kRowH;
    return s;
}

// Estimated width of a glyph group (pills: ~8 px per character at the small bold face + padding). The shell measures
// the real text; this keeps the table honest about fitting the glyph column.
inline int glyphWidth(int g, bool ps)
{
    if (g == gShoulders) return 62;
    if (glyphIsPill(g)) { const std::string n = glyphName(g, ps); return int(n.size()) * 8 + 12; }
    return 28;
}
inline int comboWidth(const Entry& e, bool ps)
{
    int w = e.hold ? 4 * 8 + 12 + 6 : 0;   // "Hold" pill
    int n = 0;
    for (int k : e.keys) {
        if (k == gNone) break;
        if (n++) w += 14;                  // "+" / "/"
        w += glyphWidth(k, ps);
    }
    return w;
}

// First-launch hint: once, after kHintDelayMs, when nothing else is on screen (not in self-tests).
inline bool hintDue(bool testMode, bool busy, uint32_t sinceStartMs) { return !testMode && !busy && sinceStartMs >= kHintDelayMs; }
inline std::string hintText(bool ps) { return expand("Press {Options} \xe2\x86\x92 Controls for all shortcuts", ps); }

} // namespace OmniControlsHelp
'''

SHELL = r'''// OMNI_CONTROLS_HELP_V1: the full-screen Controls guide (shell side). Included from OmniFeatures3.h after the other
// feature shells (it recognises their panels). Content, order and layout: OmniControlsHelp.h (pure).
//   Open: Options > Controls (top-level tile), Options > Settings > Controls, Browser settings > Show controls guide.
//   L1 / R1 (and D-pad left / right): section; D-pad up / down: page (only when a section has more rows than fit);
//   Circle: back to the panel it was opened from; Options: close everything.
// While it is open the panels under it are moved aside (omniChUnder) so their layer neither draws nor takes buttons, and
// come back unchanged on Circle. Its input layer is the first one asked (before the find bar and suggestions); its
// drawing layer is the last one drawn (over every other layer; modals still above).
#pragma once

namespace OCH = OmniControlsHelp;

// OMNI_BUTTON_MAP_V1 hook: a later patch may set omniChRemap; for a row whose button the user remapped it returns true
// with the action / note to show instead (arguments: the row's action and `where`, as written in the table).
#define OMNI_CH_REMAP_HOOK 1
static bool (*omniChRemap)(const char*, const char*, std::string&, std::string&) = nullptr;

static bool omniChShown = false;
static std::vector<int> omniChOrder;          // sections, the context's first
static int omniChIndex = 0, omniChPage = 0;
static std::deque<OmniFxPanel> omniChUnder;   // the panels under the guide while it is open
static int omniChRecent = OCH::kFromNone;     // the last panel seen (ticks), and when
static uint32_t omniChRecentAt = 0;
static bool omniChHintDone = false;
static uint32_t omniChStartedAt = 0;
static float omniChScrollAcc = 0;

// The top-most panel of the stack that has a section.
static int omniChFromStack(const std::deque<OmniFxPanel>& stack)
{
    for (auto it = stack.rbegin(); it != stack.rend(); ++it) {
        if (it->build == omniFxTabsBuild) return OCH::kFromTabs;
        if (it->build == omniTsListBuild || it->build == omniTsChoiceBuild) return OCH::kFromSessions;
        if (it->build == omniRlBuild) return OCH::kFromReading;
        if (it->build == omniFxDownloadsBuild) return OCH::kFromDownloads;
        if (it->build == omniFxContextBuild) return OCH::kFromContextMenu;
        if (it->kind == omniNpKind) return OCH::kFromNowPlaying;
        if (it->kind == omniStKind) return OCH::kFromSleep;
    }
    return OCH::kFromNone;
}
static int omniChFromState()
{
    if (pageFullscreen) return OCH::kFromFullscreen;
    if (editing) return OCH::kFromKeyboard;
    if (omniHistoryOpenFlag) return OCH::kFromHistory;
    return omniChFromStack(omniFxStack);
}

static void omniChOpen()
{
    if (omniChShown || omniModalVisible()) return;
    const uint32_t now = SDL_GetTicks();
    const int first = OCH::firstSection(omniChFromState(), omniChRecent, now - omniChRecentAt);
    omniChOrder = OCH::order(first);
    omniChIndex = omniChPage = 0;
    omniChScrollAcc = 0;
    omniChUnder.clear();
    std::swap(omniChUnder, omniFxStack);   // the panels wait under the guide (Circle brings them back)
    omniChShown = true;
    omniShellDirty = true;
    fprintf(stderr, "OMNI_CONTROLS_HELP_V1: guide opened at %s (%zu panels under it)\n", OCH::sectionTitle(first), omniChUnder.size());
}
static void omniChClose(bool all)
{
    if (!omniChShown) return;
    omniChShown = false;
    if (all) omniChUnder.clear();
    if (omniFxStack.empty()) std::swap(omniFxStack, omniChUnder); else omniChUnder.clear();   // nothing pushed meanwhile
    if (!omniFxStack.empty()) omniFxRebuild(omniFxStack.back());
    omniShellDirty = true;
}
static bool omniChOpenNow() { return omniChShown; }
static int omniChSection() { return omniChOrder.empty() ? int(OCH::kBrowsing) : omniChOrder[size_t(std::clamp(omniChIndex, 0, int(omniChOrder.size()) - 1))]; }
static void omniChGo(int index)
{
    omniChIndex = OCH::step(index, 0, int(omniChOrder.size()));
    omniChPage = 0;
    omniShellDirty = true;
}

static bool omniChButton(int b)
{
    const int n = int(omniChOrder.size());
    const OCH::Layout L = OCH::layout(int(OCH::entriesOf(omniChSection()).size()));
    switch (b) {
    case SDL_CONTROLLER_BUTTON_B: case SDL_CONTROLLER_BUTTON_BACK: omniChClose(false); break;
    case SDL_CONTROLLER_BUTTON_START: omniChClose(true); break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: case SDL_CONTROLLER_BUTTON_DPAD_LEFT: omniChGo(OCH::step(omniChIndex, -1, n)); break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: omniChGo(OCH::step(omniChIndex, 1, n)); break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: if (omniChPage > 0) { --omniChPage; omniShellDirty = true; } break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: if (omniChPage + 1 < L.pages) { ++omniChPage; omniShellDirty = true; } break;
    default: break;
    }
    return true;   // the guide takes every button while it is open
}
static bool omniChClick(int x, int y)
{
    const int tab = OCH::tabAt(x, y, int(omniChOrder.size()));
    if (tab >= 0) omniChGo(tab);
    return true;
}
static bool omniChScroll(double amount)
{
    const OCH::Layout L = OCH::layout(int(OCH::entriesOf(omniChSection()).size()));
    omniChScrollAcc -= float(amount);
    if (omniChScrollAcc >= 120) { omniChScrollAcc = 0; if (omniChPage + 1 < L.pages) ++omniChPage; omniShellDirty = true; }
    if (omniChScrollAcc <= -120) { omniChScrollAcc = 0; if (omniChPage > 0) --omniChPage; omniShellDirty = true; }
    return true;
}

// One glyph at x (layout px), centred on cy; returns its width. Uses the hint bar's pictures (faceIcon, controllerAsset,
// menuIcon, stickIcon, the D-pad icons) and its text pills (L2 / R2 / L3 / R3 / Touchpad, as omniKbHints draws them).
static int omniChPill(const std::string& text, int x, float cy)
{
    const OmniTheme& T = omniTheme();
    const int w = int(omniTextWidthPx(omniSmallBold, text) / displayScale + 0.5) + 12;
    fillRounded(x, int(cy) - 11, w, 22, 5, T.key);
    omniLabel(text, x + w / 2.f, cy, omniSmallBold, T.ink, 1);
    return w;
}
static int omniChGlyph(int g, int x, float cy, bool ps)
{
    using namespace OmniControllerAssets;
    const OmniTheme& T = omniTheme();
    const int y = int(cy + 0.5f);
    switch (g) {
    case OCH::gCross: faceIcon(x + 14, y, 0, ps); return 28;
    case OCH::gCircle: faceIcon(x + 14, y, 1, ps); return 28;
    case OCH::gSquare: faceIcon(x + 14, y, 2, ps); return 28;
    case OCH::gTriangle: faceIcon(x + 14, y, 3, ps); return 28;
    case OCH::gL1: controllerAsset(x + 14, y, ps ? ps_lb : xbox_lb); return 28;
    case OCH::gR1: controllerAsset(x + 14, y, ps ? ps_rb : xbox_rb); return 28;
    case OCH::gShoulders: controllerAsset(x + 14, y, ps ? ps_lb : xbox_lb); controllerAsset(x + 48, y, ps ? ps_rb : xbox_rb); return 62;
    case OCH::gOptions: menuIcon(x + 14, y); return 28;
    case OCH::gCreate: menuIcon(x + 14, y, true); return 28;
    case OCH::gLStick: stickIcon(x + 14, y); return 28;
    case OCH::gRStick: stickIcon(x + 14, y, true); return 28;
    case OCH::gDpad: omniIcon(omniIconDpad, x + 14, cy, T.ink); return 28;
    case OCH::gDpadV: omniIcon(omniIconDpad, x + 14, cy, T.inkFaint); omniIcon(omniIconDpadV, x + 14, cy, T.ink); return 28;
    case OCH::gDpadH: controllerAsset(x + 14, y, ps ? ps_dpad_horizontal : xbox_dpad_horizontal); return 28;
    case OCH::gDpadUp: omniIcon(omniIconDpad, x + 14, cy, T.inkFaint); omniLabel("\xe2\x96\xb2", x + 14.f, cy - 6, omniCaption, T.ink, 1); return 28;
    default: break;
    }
    if (OCH::glyphIsPill(g)) return omniChPill(OCH::glyphName(g, ps), x, cy);
    return 0;
}
static void omniChCombo(const OCH::Entry& e, int x, float cy, bool ps)
{
    const OmniTheme& T = omniTheme();
    if (e.hold) x += omniChPill("Hold", x, cy) + 6;
    int n = 0;
    for (int k : e.keys) {
        if (k == OCH::gNone) break;
        if (n++) { omniLabel(e.join == '/' ? "/" : "+", x + 7.f, cy, omniSmallBold, T.inkDim, 1); x += 14; }
        x += omniChGlyph(k, x, cy, ps);
    }
}

static void omniChDraw()
{
    const OmniTheme& T = omniTheme();
    const bool ps = playStationIcons;
    const int section = omniChSection();
    fill(0, 0, width, height, T.bg);
    omniLabel("Controls", OCH::kMarginX, OCH::kTitleY, omniTitle, T.ink);
    omniLabel(OCH::expand(OCH::sectionWhere(section), ps), width - OCH::kMarginX, OCH::kTitleY, omniSmall, T.inkDim, 2, 700);
    const int n = int(omniChOrder.size());
    for (int i = 0; i < n; ++i) {
        const OCH::Tab r = OCH::tabRect(i, n);
        const bool sel = i == omniChIndex;
        if (sel) { omniEdgeRect(r.x, OCH::kTabsY, r.w, OCH::kTabsH, 8, T.edge, T.tabOn); omniAccentLine(r.x + 10, OCH::kTabsY, r.w - 20, 2); }
        else fillRounded(r.x, OCH::kTabsY, r.w, OCH::kTabsH, omniRadius, T.tab);
        omniLabel(OCH::sectionTitle(omniChOrder[size_t(i)]), r.x + r.w / 2.f, OCH::kTabsY + OCH::kTabsH / 2.f, sel ? omniSmallBold : omniSmall, sel ? T.ink : T.inkDim, 1, r.w - 12);
    }
    omniRectPx({ 0, physical(OCH::kTabsY + OCH::kTabsH + 8), renderWidth, omniHairPx() }, T.line);
    const std::vector<int> rows = OCH::entriesOf(section);
    const OCH::Layout L = OCH::layout(int(rows.size()));
    omniChPage = std::clamp(omniChPage, 0, L.pages - 1);
    const auto& table = OCH::table();
    for (size_t i = 0; i < rows.size(); ++i) {
        const OCH::Slot s = OCH::place(int(i), L);
        if (s.page != omniChPage) continue;
        const OCH::Entry& e = table[size_t(rows[i])];
        const float cy = s.y + OCH::kRowH / 2.f;
        if (s.row % 2 == 0) fillRounded(s.x - 10, s.y + 2, L.colW + 20, OCH::kRowH - 4, omniRadius, omniMix(T.bg, T.tab, 0.6f));
        omniChCombo(e, s.x, cy, ps);
        const int tx = s.x + OCH::kGlyphColW, room = L.colW - OCH::kGlyphColW;
        std::string act = OCH::expand(e.action, ps), note = OCH::expand(e.note, ps);
        std::string ra, rn;
        if (omniChRemap && omniChRemap(e.action, e.where, ra, rn)) { act = OCH::expand(ra, ps); note = OCH::expand(rn, ps); }   // remapped button
        if (note.empty()) omniLabel(act, float(tx), cy, omniBody, T.ink, 0, room);
        else {
            omniLabel(act, float(tx), cy - 9, omniBody, T.ink, 0, room);
            omniLabel(note, float(tx), cy + 13, omniCaption, T.inkDim, 0, room);
        }
    }
    omniHintBarBg();
    std::string more;
    if (L.pages > 1) more = "Page " + std::to_string(omniChPage + 1) + " of " + std::to_string(L.pages) + "   D-pad \xe2\x96\xb2 \xe2\x96\xbc more";
    omniHints({ { omniHintShoulders, "Section" }, { 1, "Back" } }, { { omniHintMenu, "Close" } }, more);
}

// Ticks: remembers the last panel with a section (for a guide opened right after it) and shows the first-launch hint.
static void omniChTick(uint32_t now)
{
    if (!omniChShown) {
        const int from = omniChFromState();
        if (OCH::rememberable(from)) { omniChRecent = from; omniChRecentAt = now; }
    }
    if (omniChHintDone) return;
    if (!omniChStartedAt) omniChStartedAt = now ? now : 1;
    const bool busy = !active() || editing || settingsOpen || pageFullscreen || omniOverlayOpen() || !omniFxStack.empty();
    if (!OCH::hintDue(omniTestMode(), busy, now - omniChStartedAt)) return;
    omniChHintDone = true;   // one look at the flag per run
    if (access(OCH::kFlagPath, F_OK) == 0) return;
    if (FILE* f = fopen(OCH::kFlagPath, "w")) { fputs("1\n", f); fclose(f); }
    notice(OCH::hintText(playStationIcons));
    statusUntil = now + OCH::kHintShowMs;
    fprintf(stderr, "OMNI_CONTROLS_HELP_V1: first-launch hint shown\n");
}

// --- entry points ----------------------------------------------------------------------------------------------------
static void omniChQuickRow(OmniFxPanel& p)   // Options, top level
{
    OmniFxRow r; r.id = OCH::kQuickTileId; r.label = "Controls"; r.value = "All shortcuts";
    p.rows.push_back(r);
}
static bool omniChQuickInput(const OmniFxRow& r, int b)
{
    if (r.id != OCH::kQuickTileId) return false;
    if (b == SDL_CONTROLLER_BUTTON_A) omniChOpen();
    return true;
}
static void omniChSettingsRow(OmniFxPanel& p)   // Browser settings
{
    OmniFxRow r; r.id = OCH::kSettingsRowId; r.label = "Show controls guide"; r.value = "All shortcuts";
    p.rows.push_back(r);
}
static bool omniChSettingsInput(int b)
{
    if (b != SDL_CONTROLLER_BUTTON_A) return false;
    omniChOpen();
    return true;
}

[[maybe_unused]] static const bool omniChLayers = [] {
    auto& layers = omniOverlayLayers();
    layers.insert(layers.begin(), { omniChOpenNow, omniChButton, omniChClick, omniChScroll, nullptr, true });   // asked first
    layers.push_back({ omniChOpenNow, nullptr, nullptr, nullptr, omniChDraw, false });                          // drawn last
    return true;
}();
'''

EDITS = {
    'OmniBrowser.cpp': [
        ('#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n',
         '#include "OmniMediaControls.h" // OMNI_MEDIA_CONTROLS_V1: Now playing (pure)\n'
         '#include "OmniControlsHelp.h" // OMNI_CONTROLS_HELP_V1: the Controls guide: shortcut table, order, layout (pure)\n'),
    ],
    'OmniFeatures3.h': [
        ('#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n',
         '#include "OmniMediaControlsShell.h" // OMNI_MEDIA_CONTROLS_V1\n'
         '#include "OmniControlsHelpShell.h" // OMNI_CONTROLS_HELP_V1 (after the other shells: it recognises their panels)\n'),
        ('    omniSecTick(now);   // OMNI_SEC_LOCALHOST_V1\n',
         '    omniSecTick(now);   // OMNI_SEC_LOCALHOST_V1\n'
         '    omniChTick(now);    // OMNI_CONTROLS_HELP_V1: last panel seen, first-launch hint\n'),
    ],
    'OmniQuickMenu.h': [
        ('static void omniControlsShow()\n{\n    OmniFxPanel p;\n',
         'static void omniChOpen(); // OMNI_CONTROLS_HELP_V1 (OmniControlsHelpShell.h): the full-screen Controls guide\n'
         'static void omniChQuickRow(OmniFxPanel& p);\n'
         'static bool omniChQuickInput(const OmniFxRow& r, int b);\n'
         'static void omniControlsShow()\n{\n'
         '    omniChOpen(); return; // OMNI_CONTROLS_HELP_V1: the guide replaces this list (kept below, unused)\n'
         '    OmniFxPanel p;\n'),
        ('        omniNpQuickRow(p); // OMNI_MEDIA_CONTROLS_V1: Now playing, while a tab plays\n',
         '        omniChQuickRow(p); // OMNI_CONTROLS_HELP_V1: Controls (before Now playing, which comes and goes)\n'
         '        omniNpQuickRow(p); // OMNI_MEDIA_CONTROLS_V1: Now playing, while a tab plays\n'),
        ('    if (omniNpQuickInput(r, b)) return true; // OMNI_MEDIA_CONTROLS_V1 (before the >= 900 rows)\n',
         '    if (omniChQuickInput(r, b)) return true; // OMNI_CONTROLS_HELP_V1 (before the >= 900 rows)\n'
         '    if (omniNpQuickInput(r, b)) return true; // OMNI_MEDIA_CONTROLS_V1 (before the >= 900 rows)\n'),
    ],
    'OmniBrowserSettings.h': [
        ('static std::string omniFxHomeEdit;\n',
         'static void omniChSettingsRow(OmniFxPanel& p); // OMNI_CONTROLS_HELP_V1 (OmniControlsHelpShell.h)\n'
         'static bool omniChSettingsInput(int b);\n'
         'static std::string omniFxHomeEdit;\n'),
        ('    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);\n',
         '    add(omniFxSetHintBar, "Bottom button bar", omniBarsHidden(false) ? "Hidden" : "Shown", true);\n'
         '    omniChSettingsRow(p); // OMNI_CONTROLS_HELP_V1: Show controls guide\n'),
        ('    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n',
         '    if (r.id == OmniControlsHelp::kSettingsRowId) return omniChSettingsInput(b); // OMNI_CONTROLS_HELP_V1\n'
         '    if (r.id == omniSlRowId) return omniSlSettingsInput(b); // OMNI_SEND_LINK_V1\n'),
    ],
}


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
    data = text.replace('\n', nl).encode('utf-8')
    h = root / name
    if h.exists() and h.read_bytes() == data:
        return name + ': already'
    h.write_bytes(data)
    return name + ': written'


def main():
    f3 = (root / 'OmniFeatures3.h').read_bytes().decode('utf-8')
    if 'OMNI_MEDIA_CONTROLS_V1' not in f3 or 'OMNI_SLEEP_TIMER_V1' not in f3:
        sys.exit('OmniFeatures3.h: apply_media_controls.py and apply_sleep_timer.py first (their panels are recognised)')
    for name, edits in EDITS.items():   # every anchor is checked before anything is written
        check(name, edits)
    msgs = [write_new('OmniControlsHelp.h', PURE, 'OmniMediaControls.h'),
            write_new('OmniControlsHelpShell.h', SHELL, 'OmniMediaControlsShell.h')]
    msgs += [patch(name, edits) for name, edits in EDITS.items()]
    for m in msgs:
        print(m)
    print(('already ' if all(m.endswith(': already') for m in msgs) else 'applied ') + MARK)


main()
