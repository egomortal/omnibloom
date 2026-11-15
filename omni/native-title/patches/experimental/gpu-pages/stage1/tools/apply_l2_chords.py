"""OMNI_L2_CHORDS_V1 (2026-11-13, owner request): controller shortcuts while browsing, plus a Quick bar row in Settings.

  L2 (tap)        saved links, as before. It now fires when L2 is RELEASED, so L2 can also be held for the shortcuts.
                  In fullscreen video, L2 still acts on press (it asks to leave fullscreen).
  L2 + Square     Copy. The selected text (page or text box, never a password box); else the link under the pointer;
                  else the page's address. Goes to Omni's clipboard, the one the keyboard's Paste key uses.
  L2 + Triangle   Paste Omni's clipboard into the page's focused text box (also inside same-origin frames).
  L2 + Cross      the Quick bar (the Options menu with the Apps row).
  L2 + Circle     Browser settings (added 2026-11-13: an Xbox pad through Master Control may never deliver Create/View).
  Settings        a new "Quick bar and apps..." row that opens the same Quick bar.

The shortcuts only run while browsing: not in the keyboard, Settings, a panel or fullscreen video. A face button pressed
while L2 is held runs only its shortcut, and both its press and its release are kept from the page and the browser.

usage: apply_l2_chords.py <engine tree>   (edits engine/entry/OmniBrowser.cpp and OmniBrowserSettings.h; anchored,
exactly once each, idempotent)
"""
import sys
from pathlib import Path

MARK = 'OMNI_L2_CHORDS_V1'
root = Path(sys.argv[1]) / 'engine' / 'entry'


def patch(name, edits):
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
    p.write_bytes(s.encode('utf-8'))
    return 'applied'


DECL = '''static void omniSavedAxis(const SDL_ControllerAxisEvent& event)
{'''
DECL_NEW = '''// OMNI_L2_CHORDS_V1: L2 held + Square / Triangle / Cross while browsing (definitions after OmniAddons.h).
static bool omniL2Held = false, omniL2Pending = false, omniL2ChordUsed = false;
static unsigned omniL2Swallow = 0;   // face buttons whose release is kept from the page (their press ran a shortcut)
static bool omniL2Chord(const SDL_ControllerButtonEvent& event);
static void omniSavedL2();
static void omniL2Track(const SDL_ControllerAxisEvent& event)
{
    if (event.axis != SDL_CONTROLLER_AXIS_TRIGGERLEFT) return;
    if (event.value >= 20000) { if (!omniL2Held) omniL2ChordUsed = false; omniL2Held = true; }
    else if (event.value <= 8000 && omniL2Held) {
        omniL2Held = false;
        if (omniL2Pending && !omniL2ChordUsed) omniSavedL2();   // a plain tap: saved links, on release
        omniL2Pending = false;
    }
}
static void omniSavedAxis(const SDL_ControllerAxisEvent& event)
{'''

SAVED = '''    case OmniSavedLinks::Action::Saved: omniSavedL2(); break;'''
SAVED_NEW = '''    case OmniSavedLinks::Action::Saved: if (pageFullscreen) omniSavedL2(); else omniL2Pending = true; break; // OMNI_L2_CHORDS_V1: on release'''

AXIS = '''            if (event.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || event.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT)
                omniSavedAxis(event.caxis);'''
AXIS_NEW = '''            if (event.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || event.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT) {
                omniSavedAxis(event.caxis);
                omniL2Track(event.caxis); // OMNI_L2_CHORDS_V1 (after: a press arms the pending tap, a release fires it)
            }'''

BUTTON = '''        } else if (event.type == SDL_CONTROLLERBUTTONDOWN || event.type == SDL_CONTROLLERBUTTONUP) { if (!omniFxButtonEvent(event.cbutton)) omniShoulderButton(event.cbutton); } // OMNI_FEATURES_V1: hold Cross'''
BUTTON_NEW = '''        } else if (event.type == SDL_CONTROLLERBUTTONDOWN || event.type == SDL_CONTROLLERBUTTONUP) { if (!omniL2Chord(event.cbutton) && !omniFxButtonEvent(event.cbutton)) omniShoulderButton(event.cbutton); } // OMNI_FEATURES_V1: hold Cross; OMNI_L2_CHORDS_V1 first'''

IMPL = '''#include "OmniAddons.h" // OMNI_ADDONS_V1'''
IMPL_NEW = IMPL + r'''
// OMNI_L2_CHORDS_V1 -----------------------------------------------------------------------------------------------
static void omniL2Copied(const std::string& text, const char* what)
{
    omniKbClipboard = text.substr(0, 8192);
    notice(std::string(what) + " copied. L2 + Triangle pastes it");
}
static const char* const omniL2CopyScript = R"JS((function(x,y){try{var d=document,r={},s='';
var ae=d.activeElement;for(var k=0;k<3&&ae&&ae.tagName==='IFRAME';k++){try{ae=ae.contentDocument.activeElement;}catch(_){break;}}
if(ae&&(ae.tagName==='TEXTAREA'||(ae.tagName==='INPUT'&&/^(text|search|url|email|tel|number)$/i.test(ae.type||'text')))&&ae.selectionEnd>ae.selectionStart)
s=ae.value.slice(ae.selectionStart,ae.selectionEnd);
if(!s){var w=ae&&ae.ownerDocument?ae.ownerDocument.defaultView:window;try{s=String(w.getSelection()||'');}catch(_){}if(!s)s=String(window.getSelection()||'');}
if(s)r.sel=s.slice(0,8192);
var es=d.elementsFromPoint?d.elementsFromPoint(x,y):[d.elementFromPoint(x,y)],e=es[0];
for(var j=0;j<3&&e&&e.tagName==='IFRAME';j++){try{var fd=e.contentDocument;if(!fd)break;var b=e.getBoundingClientRect();x-=b.left;y-=b.top;e=fd.elementFromPoint(x,y);}catch(_){break;}}
var a=e&&e.closest?e.closest('a[href]'):null;if(a&&a.href&&!/^javascript:/i.test(a.href))r.link=a.href;
return JSON.stringify(r);}catch(err){return'{}';}})()JS";
static void omniL2Copy()
{
    Tab* t = active();
    if (!t || t->crashed) return;
    const double k = omniFxCssPerLayout(t);
    char head[96];
    snprintf(head, sizeof(head), "(function(){var X=%.1f,Y=%.1f;return ", pointerX * k, (pointerY - omniPageTop()) * k);
    std::string js = omniL2CopyScript;
    js.replace(js.size() - 2, 2, "(X,Y);})()");
    js = std::string(head) + js;
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), const_cast<void*>(static_cast<const void*>(t)), [](WKTypeRef result, WKErrorRef error, void* context) {
        if (!omniTabAlive(context) || active() != context) return;
        const std::string json = omniFxResultString(result, error);
        std::string sel, link;
        omniFxJsonString(json, "sel", sel);
        omniFxJsonString(json, "link", link);
        if (!sel.empty()) omniL2Copied(sel, "Text");
        else if (!link.empty()) omniL2Copied(link, "Link");
        else if (active() && !active()->url.empty()) omniL2Copied(active()->url, "Page address");
        else notice("Nothing to copy here");
    });
}
static std::string omniL2JsString(const std::string& v)
{
    std::string o = "\"";
    for (unsigned char c : v) {
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20) { char b[8]; snprintf(b, sizeof(b), "\\u%04x", c); o += b; }
        else o += char(c);
    }
    o += "\"";
    // U+2028 / U+2029 end a line inside a JavaScript string literal: escape them too.
    static const char* const seps[2][2] = { { "\xe2\x80\xa8", "\\u2028" }, { "\xe2\x80\xa9", "\\u2029" } };
    for (const auto& sep : seps)
        for (size_t at = 0; (at = o.find(sep[0], at)) != std::string::npos; at += 6) o.replace(at, 3, sep[1]);
    return o;
}
static void omniL2Paste()
{
    Tab* t = active();
    if (!t || t->crashed) return;
    if (omniKbClipboard.empty()) { notice("Nothing copied yet. L2 + Square copies"); return; }
    const std::string js = "(function(t){try{var e=document.activeElement;"
        "for(var k=0;k<3&&e&&e.tagName==='IFRAME';k++){try{e=e.contentDocument.activeElement;}catch(_){break;}}"
        "if(!e)return'0';var d=e.ownerDocument||document;"
        "var ok=e.isContentEditable||e.tagName==='TEXTAREA'||(e.tagName==='INPUT'&&!/^(button|checkbox|radio|submit|reset|file|image|range|color|hidden)$/i.test(e.type||'text'));"
        "if(!ok||e.disabled||e.readOnly)return'0';"
        "if(d.execCommand&&d.execCommand('insertText',false,t))return'1';"
        "if('value' in e){var a=e.selectionStart==null?e.value.length:e.selectionStart,b=e.selectionEnd==null?a:e.selectionEnd;"
        "e.value=e.value.slice(0,a)+t+e.value.slice(b);try{e.setSelectionRange(a+t.length,a+t.length);}catch(_){}"
        "e.dispatchEvent(new Event('input',{bubbles:true}));return'1';}return'0';}catch(err){return'0';}})(" + omniL2JsString(omniKbClipboard) + ")";
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), const_cast<void*>(static_cast<const void*>(t)), [](WKTypeRef result, WKErrorRef error, void* context) {
        if (!omniTabAlive(context) || active() != context) return;
        if (omniFxResultString(result, error) == "1") notice("Pasted");
        else notice("Pick a text box first (Cross), then L2 + Triangle pastes");
    });
}
static bool omniL2Chord(const SDL_ControllerButtonEvent& event)
{
    const unsigned bit = event.button < 32 ? 1u << event.button : 0;
    if (event.type == SDL_CONTROLLERBUTTONUP) {
        if (!(omniL2Swallow & bit)) return false;
        omniL2Swallow &= ~bit;
        return true;
    }
    if (!omniL2Held || !bit) return false;
    if (event.button != SDL_CONTROLLER_BUTTON_X && event.button != SDL_CONTROLLER_BUTTON_Y && event.button != SDL_CONTROLLER_BUTTON_A
        && event.button != SDL_CONTROLLER_BUTTON_B) return false;
    if (!active() || editing || settingsOpen || pageFullscreen || omniOverlayOpen()) return false;
    omniL2ChordUsed = true;
    omniL2Swallow |= bit;
    if (event.button == SDL_CONTROLLER_BUTTON_X) omniL2Copy();            // Square
    else if (event.button == SDL_CONTROLLER_BUTTON_Y) omniL2Paste();      // Triangle
    else if (event.button == SDL_CONTROLLER_BUTTON_B) omniFxSettingsShow(); // Circle: Browser settings
    else omniFxQuickMenuShow();                                           // Cross
    return true;
}'''

ENUM = '''    omniFxSetJit /* OMNI_JSC_JIT_V1 */, omniFxSetGamepad /* OMNI_GAMEPAD_V1 */ };'''
ENUM_NEW = '''    omniFxSetJit /* OMNI_JSC_JIT_V1 */, omniFxSetGamepad /* OMNI_GAMEPAD_V1 */, omniFxSetQuick /* OMNI_L2_CHORDS_V1 */ };'''
ROW = '''    add(omniFxSetDisplay, "Controller, theme and display...", "", false);'''
ROW_NEW = '''    add(omniFxSetQuick, "Quick bar and apps...", "L2 + Cross", false); // OMNI_L2_CHORDS_V1
    add(omniFxSetDisplay, "Controller, theme and display...", "", false);'''
CASE = '''    case omniFxSetDisplay: if (!a) return false; omniFxCloseAll(); settingsOpen = true; omniSettingsRow = 0; return true;'''
CASE_NEW = '''    case omniFxSetQuick: if (!a) return false; omniFxCloseAll(); omniFxQuickMenuShow(); return true; // OMNI_L2_CHORDS_V1
    case omniFxSetDisplay: if (!a) return false; omniFxCloseAll(); settingsOpen = true; omniSettingsRow = 0; return true;'''

print('OmniBrowser.cpp', patch('OmniBrowser.cpp', [(DECL, DECL_NEW), (SAVED, SAVED_NEW), (AXIS, AXIS_NEW), (BUTTON, BUTTON_NEW), (IMPL, IMPL_NEW)]))
print('OmniBrowserSettings.h', patch('OmniBrowserSettings.h', [(ENUM, ENUM_NEW), (ROW, ROW_NEW), (CASE, CASE_NEW)]))
