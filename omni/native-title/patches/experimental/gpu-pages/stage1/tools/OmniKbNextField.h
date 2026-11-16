// OMNI_KB_NEXTFIELD_V1: the pure part of "previous / next text box" on the on-screen keyboard (no SDL, no WebKit):
// the page script, its result, what the shell does with it, the hint label and the Shift undo of the L3 chord.
// Shell side and reasons: tools/apply_kb_nextfield.py. Tested on the host with g++ (tools/test_kb_nextfield.cpp).
#pragma once
#include <string>
#include <string_view>

namespace OmniKbNextField {

// The page script. __M__ is c (count: where the focused text box is), n (next) or p (previous). It works in the
// document that holds the focused field, found the way OMNI_KEYBOARD_V2's probe finds it (activeElement through at
// most 4 same-origin iframes), and only there: text boxes in other frames are not visited.
// Text boxes: <input> that types text (not hidden / button / submit / reset / checkbox / radio / file / image /
// range / color / date / time / month / week), <textarea>, contenteditable roots. Skipped: disabled (also by a
// disabled fieldset), read-only, tabindex -1 (Tab skips them too), inside [inert], not rendered, visibility hidden,
// collapsed to nothing, or parked above / left of the page (spam traps). Document order, as Tab.
// Returns "count,<index>,<total>", "moved,<index>,<total>" (focused, caret at the end), "edge,<index>,<total>" (no
// text box that way) or "none" (no field / the page refused the focus). index -1: the focused element is not one of them.
inline constexpr const char* kScript = R"JS((function(){try{
var M='__M__',d=document,e=d.activeElement,n=0;
while(e&&e.tagName==='IFRAME'&&n<4){try{var cd=e.contentDocument;if(!cd)break;d=cd;e=d.activeElement;n++;}catch(x){break;}}
if(!e||!d.querySelectorAll)return 'none';
var w=d.defaultView||window,bad=/^(hidden|button|submit|reset|checkbox|radio|file|image|range|color|date|datetime-local|month|week|time)$/;
var ok=function(f){try{
 var tn=f.tagName;
 if(tn==='INPUT'){if(bad.test(String(f.type||'text').toLowerCase()))return false;}
 else if(tn!=='TEXTAREA'){if(!f.isContentEditable||(f.parentElement&&f.parentElement.isContentEditable))return false;}
 if(f.disabled||f.readOnly)return false;
 if(f.matches&&f.matches(':disabled'))return false;
 if(f.getAttribute&&f.getAttribute('tabindex')!==null&&f.tabIndex<0)return false;
 if(f.closest&&f.closest('[inert]'))return false;
 if(!f.getClientRects||!f.getClientRects().length)return false;
 var s=w.getComputedStyle?w.getComputedStyle(f):null;if(s&&(s.visibility==='hidden'||s.visibility==='collapse'||s.display==='none'))return false;
 var r=f.getBoundingClientRect();if(r.width<1&&r.height<1)return false;
 if(r.right+(w.pageXOffset||0)<=0||r.bottom+(w.pageYOffset||0)<=0)return false;
 return true;}catch(x){return false;}};
var all=d.querySelectorAll('input,textarea,[contenteditable]'),L=[],i,j;
for(i=0;i<all.length;i++)if(ok(all[i]))L.push(all[i]);
var cur=e;if(cur.tagName!=='INPUT'&&cur.tagName!=='TEXTAREA'&&cur.isContentEditable)while(cur.parentElement&&cur.parentElement.isContentEditable)cur=cur.parentElement;
i=L.indexOf(cur);
if(M==='c')return 'count,'+i+','+L.length;
var dir=M==='n'?1:-1,t=-1;
if(i>=0)t=i+dir;
else for(j=0;j<L.length;j++){var p=cur.compareDocumentPosition(L[j]);if(dir>0&&(p&4)){t=j;break;}if(dir<0&&(p&2))t=j;}
if(t<0||t>=L.length)return 'edge,'+i+','+L.length;
var f=L[t];f.focus();
if(d.activeElement!==f)return 'none';
if(f.tagName==='INPUT'||f.tagName==='TEXTAREA'){try{var v=String(f.value==null?'':f.value);f.setSelectionRange(v.length,v.length);}catch(x){}}
else{try{var sel=d.getSelection(),g=d.createRange();g.selectNodeContents(f);g.collapse(false);sel.removeAllRanges();sel.addRange(g);}catch(x){}}
return 'moved,'+t+','+L.length;
}catch(x){return 'none';}})())JS";

// The script for one mode ('c', 'n' or 'p'; anything else counts).
inline std::string script(char mode)
{
    std::string s = kScript;
    const size_t at = s.find("__M__");
    if (at != std::string::npos) s.replace(at, 5, std::string(1, mode == 'n' || mode == 'p' ? mode : 'c'));
    return s;
}

enum Kind : int { kBad = 0, kCount, kMoved, kEdge, kNone };
struct Result { int kind = kBad; int index = -1, total = 0; };

namespace detail {
inline bool number(std::string_view s, int& out)
{
    bool neg = false;
    if (!s.empty() && s[0] == '-') { neg = true; s.remove_prefix(1); }
    if (s.empty() || s.size() > 7) return false;
    int v = 0;
    for (char c : s) { if (c < '0' || c > '9') return false; v = v * 10 + (c - '0'); }
    out = neg ? -v : v;
    return true;
}
}

// The script's answer; anything malformed is kBad (an error, a page that replaced the result ...).
inline Result parse(std::string_view s)
{
    Result r;
    if (s == "none") { r.kind = kNone; return r; }
    const size_t a = s.find(','), b = a == std::string_view::npos ? a : s.find(',', a + 1);
    if (b == std::string_view::npos || s.find(',', b + 1) != std::string_view::npos) return r;
    const std::string_view word = s.substr(0, a);
    int index = 0, total = 0;
    if (!detail::number(s.substr(a + 1, b - a - 1), index) || !detail::number(s.substr(b + 1), total)) return r;
    if (total < 0 || index < -1 || index >= total) return r;   // index -1: not one of them (any total)
    const int kind = word == "count" ? kCount : word == "moved" ? kMoved : word == "edge" ? kEdge : kBad;
    if (kind == kBad || (kind == kMoved && index < 0)) return r;
    r.kind = kind; r.index = index; r.total = total;
    return r;
}

// What the shell does with a move's answer (dir +1 next, -1 previous).
enum Step : int { sStay = 0, sReopen, sDone, sFirst, sNoField };
inline int step(const Result& r, int dir)
{
    switch (r.kind) {
    case kMoved: return sReopen;                     // the keyboard restarts on the new field
    case kEdge: return dir > 0 ? sDone : sFirst;     // last text box: Done closes the keyboard; first: a notice
    case kCount: return sStay;
    default: return sNoField;
    }
}

// The focused text box is the last one (known: a count / move answer for this keyboard session).
inline bool isLast(bool known, int index, int total) { return known && total > 0 && index >= 0 && index == total - 1; }
inline const char* nextLabel(bool known, int index, int total) { return isLast(known, index, total) ? "Done" : "Next text box"; }
inline constexpr const char* kFirstNotice = "This is the first text box";
inline constexpr const char* kNoneNotice = "No other text box here";

// L3 (Shift) goes down before L1 / R1: the chord puts the Shift state back to what it was before that press when it
// came in the same keyboard session (a move restarts the session anyway: letters, Shift off).
inline int capsAfterChord(int capsNow, int capsBefore, bool sameSession) { return sameSession ? capsBefore : capsNow; }

// A move answer older than this no longer blocks the next chord (a page that never answered).
inline constexpr unsigned kBusyMs = 1500;
inline bool busy(bool waiting, unsigned since, unsigned now) { return waiting && unsigned(now - since) < kBusyMs; }

} // namespace OmniKbNextField
