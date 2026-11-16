// OMNI_VIDEO_KEYS_V1: the pure part of the full-screen video keys (no SDL, no WebKit). The shell side is
// OmniVideoKeysShell.h (written by tools/apply_video_keys.py, which also has the reasons). Tested with g++
// (tools/test_video_keys.cpp) and node (tools/test_video_keys.cjs runs the page script against a fake DOM).
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace OmniVideoKeys {

constexpr int kR2Held = 20000;     // R2 counts as held from this axis value (L2's chord threshold too)
constexpr unsigned kOsdMs = 2000;  // the OSD shows this long after each press
constexpr int kArrowSeconds = 5;   // D-pad left / right: YouTube's own arrow keys step 5 s, so does every other player
constexpr int kShoulderSeconds = 10; // L1 / R1 (YouTube's j / l)
constexpr int kBigSeconds = 60;    // R2 + L1 / R1
constexpr int kFrameFps = 30;      // R2 + D-pad: one step = 1/30 s (a frame at 30 fps; the page can't tell the real rate)
constexpr size_t kLabelMax = 60;

// The controller buttons this feature looks at (the shell maps SDL's to these).
enum Pad { pOther = 0, pCross, pSquare, pTriangle, pL1, pR1, pLeft, pRight, pL3, pR3, pTouchpad };
// What the page script does. kNone: not ours (button() goes on as before).
enum Act { kNone = -1, kInfo = 0, kToggle, kSeek, kFrame, kCaptions, kCapTrack, kAudio, kMute, kConfirm };
// Script flags: fYtKey: on YouTube the press stays YouTube's own key (the script only reads); fBoxKey: while the resume
// add-on's "Resume from" prompt is up the press is an arrow key for it (the script only reads).
enum Flag { fYtKey = 1, fBoxKey = 2 };
enum Fallback { fbNone = 0, fbKey, fbClick };

struct Key { const char* text = nullptr; const char* identifier = nullptr; int keysym = 0; };
// The keys button() sent before (OMNI_FULLSCREEN_KEYS_V1), plus YouTube's frame keys.
inline Key keyK() { return { "k", "U+004B", 0x6b }; }
inline Key keyJ() { return { "j", "U+004A", 0x6a }; }
inline Key keyL() { return { "l", "U+004C", 0x6c }; }
inline Key keyC() { return { "c", "U+0043", 0x63 }; }
inline Key keyM() { return { "m", "U+004D", 0x6d }; }
inline Key keyLeft() { return { nullptr, "Left", 0xff51 }; }
inline Key keyRight() { return { nullptr, "Right", 0xff53 }; }
inline Key keyComma() { return { ",", "U+002C", 0x2c }; }
inline Key keyPeriod() { return { ".", "U+002E", 0x2e }; }

struct Press {
    Act act = kNone;
    int amount = 0;            // seconds (kSeek) or frames (kFrame)
    int flags = 0;
    Fallback fallback = fbNone;
    Key key;                   // fallback == fbKey
    bool speedFirst = false;   // touchpad: the playback-speed shortcut runs first, this press only reads
};

// Which press is which. r2: R2 held. Buttons not listed (Circle, Options, Create, D-pad up / down, R2 alone) are kNone:
// button()'s full-screen branch handles them exactly as before.
inline Press plan(Pad pad, bool r2)
{
    Press p;
    auto set = [&p](Act a, int amount, int flags, Fallback fb, Key k = Key()) {
        p.act = a; p.amount = amount; p.flags = flags; p.fallback = fb; p.key = k;
    };
    if (r2) {
        switch (pad) {
        case pL1: set(kSeek, -kBigSeconds, 0, fbNone); return p;
        case pR1: set(kSeek, kBigSeconds, 0, fbNone); return p;
        case pLeft: set(kFrame, -1, fYtKey, fbKey, keyComma()); return p;
        case pRight: set(kFrame, 1, fYtKey, fbKey, keyPeriod()); return p;
        case pTriangle: set(kCapTrack, 0, 0, fbKey, keyC()); return p;
        case pSquare: set(kAudio, 0, 0, fbNone); return p;
        default: break;   // R2 + anything else: as without R2
        }
    }
    switch (pad) {
    case pCross: set(kConfirm, 0, 0, fbClick); break;
    case pSquare: set(kToggle, 0, fYtKey, fbKey, keyK()); break;
    case pL1: set(kSeek, -kShoulderSeconds, fYtKey, fbKey, keyJ()); break;
    case pR1: set(kSeek, kShoulderSeconds, fYtKey, fbKey, keyL()); break;
    case pLeft: set(kSeek, -kArrowSeconds, fYtKey | fBoxKey, fbKey, keyLeft()); break;
    case pRight: set(kSeek, kArrowSeconds, fYtKey | fBoxKey, fbKey, keyRight()); break;
    case pTriangle: set(kCaptions, 0, fYtKey, fbKey, keyC()); break;
    case pL3: set(kMute, 0, fYtKey, fbKey, keyM()); break;
    case pR3: set(kInfo, 0, 0, fbNone); break;
    case pTouchpad: set(kInfo, 0, 0, fbNone); p.speedFirst = true; break;
    default: break;
    }
    return p;
}

// --- the page script --------------------------------------------------------------------------------------------
// One evaluate per press, main frame (same-origin frames walked, as Now playing does). A: the act, N: seconds / frames,
// F: flags. The video: the full-screen element when it is one, else the playing / largest one inside it (or inside its
// same-origin frame), else (no full-screen element in this document) the playing / largest one in the page.
// Answer: "omni-vk1\n<acted|key|none>\n<playing|paused|none>\n<pos>\n<dur|live>\n<rate>\n<muted 0|1>\n<captions>\n
// <audio>\n<resume>\n<note>\n<yt 0|1>" (captions: "" none known, "off", "on" or the track's label; audio: the enabled
// track's label when there are two or more; resume: the add-on prompt's time and focused button, "12:05\tyes").
constexpr const char* kScriptBody = R"JS((function(A,N,F){
var d=document,o=[],el=null,i,a,P=null,yt=false,box=null,out='none',note='',cap='',aud='',fs=null;
function walk(x,k){if(!x||k>3)return;try{var m=x.querySelectorAll('video');for(var q=0;q<m.length;q++)o.push(m[q]);
var f=x.querySelectorAll('iframe,frame');for(var j=0;j<f.length;j++){var c=null;try{c=f[j].contentDocument;}catch(e){}walk(c,k+1);}}catch(e){}}
try{fs=d.fullscreenElement||d.webkitFullscreenElement||null;}catch(e){}
if(fs&&fs.tagName==='VIDEO')o.push(fs);
else if(fs&&(fs.tagName==='IFRAME'||fs.tagName==='FRAME')){var cd=null;try{cd=fs.contentDocument;}catch(e){}walk(cd,1);}
else if(fs)walk(fs,0);
else walk(d,0);
function has(v){try{return !!(v.currentSrc||v.srcObject);}catch(e){return false;}}
for(i=0;i<o.length;i++)if(has(o[i])&&!o[i].paused&&!o[i].ended&&o[i].readyState>0){el=o[i];break;}
if(!el){var best=-1;for(i=0;i<o.length;i++){if(!has(o[i]))continue;var r=null,ar=0;try{r=o[i].getBoundingClientRect();ar=r.width*r.height;}catch(e){}
if(ar>best){best=ar;el=o[i];}}}
try{yt=/(^|\.)youtube(-nocookie)?\.com$/i.test(location.hostname||'');}catch(e){}
try{P=d.getElementById('movie_player');if(P&&typeof P.getPlayerState!=='function')P=null;}catch(e){P=null;}
if(P)yt=true;
function findBox(){try{return d.querySelector('.omni-resume[data-omni-addon]');}catch(e){return null;}}
box=findBox();
function lab(t,n){var s='';try{s=t.label||t.displayName||t.name||t.language||t.languageCode||'';}catch(e){}return s?String(s):'Track '+n;}
function subs(){var l=[];try{var tt=el&&el.textTracks;if(tt)for(var q=0;q<tt.length;q++){var t=tt[q];if(t&&(t.kind==='subtitles'||t.kind==='captions'))l.push(t);}}catch(e){}return l;}
function showing(l){for(var q=0;q<l.length;q++)if(l[q].mode==='showing')return q;return -1;}
function clampTo(t){var du=el.duration,sk=null;try{sk=el.seekable;}catch(e){}
if(isFinite(du)&&du>0)t=Math.min(t,Math.max(0,du-0.5));else if(sk&&sk.length)t=Math.min(Math.max(t,sk.start(0)),sk.end(sk.length-1));return Math.max(0,t);}
function seek(n){if(yt&&P&&typeof P.seekTo==='function'&&typeof P.getCurrentTime==='function'){var c=+P.getCurrentTime(),du=typeof P.getDuration==='function'?+P.getDuration():NaN,t=c+n;
if(isFinite(du)&&du>0)t=Math.min(t,Math.max(0,du-0.5));P.seekTo(Math.max(0,t),true);return true;}
if(!el)return false;el.currentTime=clampTo(el.currentTime+n);return true;}
function ytCap(){try{if(!P||typeof P.getOption!=='function'||typeof P.setOption!=='function')return false;
try{if(typeof P.loadModule==='function')P.loadModule('captions');}catch(e){}
var l=P.getOption('captions','tracklist')||[];if(!l.length)return false;var cur=P.getOption('captions','track')||{},k=-1;
for(var q=0;q<l.length;q++)if(cur&&cur.languageCode&&l[q].languageCode===cur.languageCode&&(!cur.vss_id||l[q].vss_id===cur.vss_id))k=q;
if(k+1>=l.length){if(typeof P.unloadModule==='function')P.unloadModule('captions');else P.setOption('captions','track',{});cap='off';}
else{P.setOption('captions','track',l[k+1]);cap=lab(l[k+1],k+2);}return true;}catch(e){return false;}}
function ytAudio(){try{if(!P||typeof P.getAvailableAudioTracks!=='function'||typeof P.setAudioTrack!=='function')return 0;
var l=P.getAvailableAudioTracks()||[];if(l.length<2)return -1;var cur=typeof P.getAudioTrack==='function'?P.getAudioTrack():null,k=-1;
for(var q=0;q<l.length;q++)if(l[q]===cur||(cur&&l[q].id!==undefined&&l[q].id===cur.id))k=q;
var nx=l[(k+1)%l.length],s='';P.setAudioTrack(nx);try{s=nx.getLanguageInfo().getName();}catch(e){}
try{if(!s&&nx.audioTrack)s=nx.audioTrack.displayName;}catch(e){}aud=s?String(s):lab(nx,(k+1)%l.length+1);return 1;}catch(e){return 0;}}
try{
if(A===8){if(box){var b=null,ae=d.activeElement;if(ae&&box.contains(ae)&&ae.tagName==='BUTTON')b=ae;
if(!b)b=box.querySelector('.omni-resume-yes');if(b){note=b.classList&&b.classList.contains('omni-resume-no')?'over':'resume';b.click();out='acted';}}
if(out!=='acted')out='key';}
else if((F&2)&&box&&box.contains(d.activeElement))out='key';
else if((F&1)&&yt){out='key';if(A===3&&el&&!el.paused)el.pause();}
else if(A===0){out=el?'acted':'none';}
else if(A===1){if(el){if(el.paused||el.ended){var p=el.play();if(p&&p.catch)p.catch(function(){});}else el.pause();out='acted';}else out='key';}
else if(A===2){if(seek(N))out='acted';else out='key';}
else if(A===3){if(el){if(!el.paused)el.pause();el.currentTime=clampTo(el.currentTime+N/30);out='acted';}else out='key';}
else if(A===4){var l4=subs();if(!el||!l4.length)out='key';else{var s4=showing(l4);
if(s4>=0){el.__omniVkCap=s4;for(a=0;a<l4.length;a++)if(l4[a].mode==='showing')l4[a].mode='disabled';}
else{var w=el.__omniVkCap;if(!(w>=0&&w<l4.length)){w=0;var nl='';try{nl=String(navigator.language||'').slice(0,2).toLowerCase();}catch(e){}
for(a=0;a<l4.length;a++)if(nl&&String(l4[a].language||'').toLowerCase().indexOf(nl)===0){w=a;break;}}
for(a=0;a<l4.length;a++)l4[a].mode=a===w?'showing':'disabled';}out='acted';}}
else if(A===5){if(yt){if(ytCap())out='acted';else out='key';}
else{var l5=subs();if(!el||!l5.length)out='key';else{var s5=showing(l5),nx5=s5+1;
for(a=0;a<l5.length;a++)l5[a].mode=a===nx5?'showing':'disabled';if(nx5<l5.length)el.__omniVkCap=nx5;out='acted';}}}
else if(A===6){var y6=yt?ytAudio():0;if(y6===1)out='acted';
else if(y6===-1){out='none';note='noaudio';}
else{var at=null;try{at=el&&el.audioTracks;}catch(e){}
if(at&&at.length>1){var e6=-1;for(a=0;a<at.length;a++)if(at[a].enabled){e6=a;break;}var n6=(e6+1)%at.length;
for(a=0;a<at.length;a++)at[a].enabled=a===n6;aud=lab(at[n6],n6+1);out='acted';}
else{out='none';note=el?'noaudio':'';}}}
else if(A===7){if(el){el.muted=!el.muted;out='acted';}else out='key';}
}catch(e){out=out==='none'?'key':out;note=note||'error';}
if(!cap){if(yt){var yb=null;try{yb=d.querySelector('.ytp-subtitles-button');}catch(e){}
var pr=yb&&yb.getAttribute?yb.getAttribute('aria-pressed'):null;if(pr==='true')cap='on';else if(pr==='false')cap='off';}
else if(!yt){var l=subs();if(l.length){var s=showing(l);cap=s<0?'off':lab(l[s],s+1);}}}
if(!aud){try{var at2=el&&el.audioTracks;if(at2&&at2.length>1)for(a=0;a<at2.length;a++)if(at2[a].enabled){aud=lab(at2[a],a+1);break;}}catch(e){}}
box=findBox();var rs='';
if(box){var qq=null;try{qq=box.querySelector('.omni-resume-q');}catch(e){}var mt=/(\d+(?::\d{2}){1,2})/.exec(qq?String(qq.textContent||''):'');
var fe=d.activeElement,fi=false;try{fi=!!fe&&box.contains(fe);}catch(e){}
rs=(mt?mt[1]:'?')+'\t'+(!fi?'-':fe.classList&&fe.classList.contains('omni-resume-no')?'no':'yes');}
function c(x,l){return String(x==null?'':x).replace(/[\r\n\t]+/g,' ').slice(0,l);}
function n(x){return typeof x==='number'&&isFinite(x)?x.toFixed(2):(x===Infinity?'live':'');}
var rate='';try{rate=el?n(el.playbackRate):'';}catch(e){}
return ['omni-vk1',out,el?(el.paused||el.ended?'paused':'playing'):'none',el?n(el.currentTime):'',el?n(el.duration):'',rate,
el?(el.muted?'1':'0'):'',c(cap,60),c(aud,60),rs,note,yt?'1':'0'].join('\n');
}))JS";

inline std::string script(const Press& p)
{
    return std::string(kScriptBody) + "(" + std::to_string(int(p.act)) + "," + std::to_string(p.amount) + ","
        + std::to_string(p.flags) + ")";
}

// --- the answer -------------------------------------------------------------------------------------------------
enum Outcome { oBad = 0, oActed, oKey, oNone };
enum State { sNone = 0, sPlaying, sPaused };
constexpr double kLive = -2;
struct Info {
    bool ok = false;
    Outcome outcome = oBad;
    State state = sNone;
    double position = -1, duration = -1, rate = -1;   // -1 unknown; duration kLive for streams
    int muted = -1;                                   // -1 unknown
    std::string captions, audio, resumeAt, note;
    bool resumeFocused = false;                       // the focus is in the prompt (arrows move it there)
    bool resumeNo = false;                            // ... on "Start over"
    bool youtube = false;
};
inline double parseNumber(const std::string& s, bool allowLive)
{
    if (allowLive && s == "live") return kLive;
    if (s.empty() || s.size() > 24) return -1;
    char* end = nullptr;
    const double v = std::strtod(s.c_str(), &end);
    return end && *end == 0 && std::isfinite(v) && v >= 0 ? v : -1;
}
// Printable text only, at most kLabelMax bytes, never cutting a UTF-8 sequence.
inline std::string cleanLabel(const std::string& s)
{
    std::string o;
    for (unsigned char c : s) o += (c < 0x20 || c == 0x7f) ? ' ' : char(c);
    if (o.size() > kLabelMax) {
        size_t n = kLabelMax;
        while (n > 0 && (static_cast<unsigned char>(o[n]) & 0xC0) == 0x80) --n;
        o = o.substr(0, n);
    }
    return o;
}
inline Info parse(const std::string& text)
{
    std::vector<std::string> f;
    size_t pos = 0;
    while (f.size() < 13) {
        const size_t nl = text.find('\n', pos);
        f.push_back(text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos));
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    Info i;
    if (f.size() != 12 || f[0] != "omni-vk1") return i;
    i.outcome = f[1] == "acted" ? oActed : f[1] == "key" ? oKey : f[1] == "none" ? oNone : oBad;
    if (i.outcome == oBad) return i;
    i.state = f[2] == "playing" ? sPlaying : f[2] == "paused" ? sPaused : sNone;
    i.position = parseNumber(f[3], false);
    i.duration = parseNumber(f[4], true);
    i.rate = parseNumber(f[5], false);
    i.muted = f[6] == "1" ? 1 : f[6] == "0" ? 0 : -1;
    i.captions = cleanLabel(f[7]);
    i.audio = cleanLabel(f[8]);
    const size_t tab = f[9].find('\t');
    if (tab != std::string::npos) {
        i.resumeAt = cleanLabel(f[9].substr(0, tab));
        const std::string focus = f[9].substr(tab + 1);
        i.resumeFocused = focus == "yes" || focus == "no";
        i.resumeNo = focus == "no";
    }
    i.note = cleanLabel(f[10]);
    i.youtube = f[11] == "1";
    if (i.state == sNone) { i.position = i.duration = i.rate = -1; i.muted = -1; }
    i.ok = true;
    return i;
}

// What the shell does with the answer. A press whose page did not answer (or answered "key") gets the action it had
// before this feature: its key, or Cross's click at the pointer.
inline Fallback fallbackFor(const Press& p, const Info& i)
{
    if (p.fallback == fbNone) return fbNone;
    if (!i.ok || i.outcome == oKey) return p.fallback;
    return fbNone;
}

// --- the OSD ----------------------------------------------------------------------------------------------------
// 65 -> "1:05", 3723 -> "1:02:03"; "" when unknown.
inline std::string clock(double seconds)
{
    if (!(seconds >= 0) || !std::isfinite(seconds)) return std::string();
    const long long s = static_cast<long long>(seconds);
    char buf[32];
    if (s >= 3600) std::snprintf(buf, sizeof buf, "%lld:%02lld:%02lld", s / 3600, (s / 60) % 60, s % 60);
    else std::snprintf(buf, sizeof buf, "%lld:%02lld", s / 60, s % 60);
    return buf;
}
// "1x", "1.25x", "0.5x" (x = U+00D7, as the playback-speed labels); "" unknown.
inline std::string rateLabel(double r)
{
    if (!(r > 0) || !std::isfinite(r)) return std::string();
    char buf[16];
    std::snprintf(buf, sizeof buf, "%.2f", r);
    std::string s = buf;
    while (!s.empty() && s.back() == '0') s.pop_back();
    if (!s.empty() && s.back() == '.') s.pop_back();
    return s + "\xC3\x97";
}
inline std::string seekLabel(int seconds)
{
    const int a = seconds < 0 ? -seconds : seconds;
    const std::string sign = seconds < 0 ? "-" : "+";
    return a % 60 == 0 ? sign + std::to_string(a / 60) + " min" : sign + std::to_string(a) + " s";
}

struct Osd {
    std::string title;      // what the press did
    std::string clock;      // "12:05 / 45:10", "12:05 (live)", ""
    std::string right;      // "1.25x   CC English"
    std::string resume;     // "Resume from 12:05?   Cross: Resume" while the add-on's prompt is up
    double fraction = -1;   // the bar, -1: no bar
    bool operator==(const Osd& o) const
    {
        return title == o.title && clock == o.clock && right == o.right && resume == o.resume && fraction == o.fraction;
    }
};

// The state after the press. A key the shell is about to send (YouTube's own keys) is predicted from the answer read
// just before it: play / pause flips, the position moves, mute and captions flip.
inline Info predicted(const Press& p, Info i, Fallback fb)
{
    if (fb != fbKey || !i.ok || i.state == sNone) return i;
    switch (p.act) {
    case kToggle: i.state = i.state == sPlaying ? sPaused : sPlaying; break;
    case kSeek:
    case kFrame:
        if (!i.resumeFocused || !(p.flags & fBoxKey)) {
            if (p.act == kFrame) i.state = sPaused;
            if (i.position >= 0) {
                double t = i.position + (p.act == kFrame ? double(p.amount) / kFrameFps : double(p.amount));
                if (i.duration > 0 && t > i.duration) t = i.duration;
                i.position = t < 0 ? 0 : t;
            }
        }
        break;
    case kMute: if (i.muted >= 0) i.muted = !i.muted; break;
    case kCaptions: if (i.captions == "on") i.captions = "off"; else if (i.captions == "off") i.captions = "on"; break;
    default: break;
    }
    return i;
}

inline std::string captionsWord(const std::string& c)
{
    if (c.empty()) return std::string();
    if (c == "off") return "Captions off";
    if (c == "on") return "Captions on";
    return "Captions: " + c;
}

// The OSD for one answer. fb: what the shell does next (fallbackFor).
inline Osd osd(const Press& p, const Info& raw, Fallback fb)
{
    Osd o;
    if (!raw.ok) {
        if (fb == fbNone && p.act != kConfirm) o.title = "The page didn't answer";
        return o;
    }
    const Info i = predicted(p, raw, fb);
    const bool keyed = fb == fbKey;
    const bool boxArrow = keyed && (p.flags & fBoxKey) && raw.resumeFocused;
    const bool noVideo = i.state == sNone;
    std::string resumeFocus = i.resumeNo ? "Start over" : "Resume";
    if (boxArrow) resumeFocus = i.resumeNo ? "Resume" : "Start over";   // the arrow moves the prompt's focus
    if (boxArrow) o.title = "Resume from " + i.resumeAt + "?";
    else if (p.speedFirst) o.title = noVideo ? "" : "Speed: " + rateLabel(i.rate);
    else switch (p.act) {
    case kInfo: o.title = noVideo ? "No video found on this page" : i.state == sPlaying ? "Playing" : "Paused"; break;
    case kToggle: o.title = noVideo ? "" : i.state == sPlaying ? "Playing" : "Paused"; break;
    // No video in reach (a player in another site's frame) with a key sent: that player decides, the OSD says nothing.
    case kSeek: o.title = noVideo ? (keyed ? "" : "No video found on this page") : seekLabel(p.amount); break;
    case kFrame: o.title = noVideo ? (keyed ? "" : "No video found on this page") : std::string("Frame ") + (p.amount < 0 ? "-1" : "+1"); break;
    case kCaptions:
    case kCapTrack:
        if (keyed && i.youtube && (i.captions.empty() || p.act == kCapTrack)) o.title = "Captions";
        else if (keyed && !i.youtube) o.title = noVideo ? "" : "Captions";
        else o.title = captionsWord(i.captions);
        break;
    case kAudio:
        o.title = i.outcome == oActed ? "Audio: " + (i.audio.empty() ? std::string("next track") : i.audio)
            : noVideo ? "No video found on this page" : "No other audio tracks";
        break;
    case kMute: o.title = i.muted == 1 ? "Muted" : i.muted == 0 ? "Sound on" : ""; break;
    case kConfirm:
        o.title = i.note == "resume" ? "Resumed" : i.note == "over" ? "Starting over" : "";
        break;
    default: break;
    }
    if (!noVideo) {
        if (i.duration == kLive) o.clock = i.position >= 0 ? clock(i.position) + " (live)" : std::string("Live");
        else if (i.duration > 0) {
            o.clock = (i.position >= 0 ? clock(i.position) : std::string("0:00")) + " / " + clock(i.duration);
            const double f = i.position >= 0 ? i.position / i.duration : 0;
            o.fraction = f < 0 ? 0 : f > 1 ? 1 : f;
        } else o.clock = clock(i.position);
        o.right = rateLabel(i.rate);
        if (!i.captions.empty() && p.act != kCaptions && p.act != kCapTrack)
            o.right += std::string(o.right.empty() ? "" : "   ") + (i.captions == "off" ? "CC off" : i.captions == "on" ? "CC on" : "CC " + i.captions);
    }
    if (!i.resumeAt.empty() && !(p.act == kConfirm && raw.outcome == oActed)) {
        if (o.title.empty() || p.act == kConfirm) o.title = "Resume from " + i.resumeAt + "?";
        o.resume = "Cross: " + resumeFocus + "   D-pad left / right: choose";
    }
    // A press that changed nothing visible and says nothing (Cross clicking the page) shows no OSD.
    if (o.title.empty() && p.act == kConfirm) return Osd();
    return o;
}
inline bool shown(const Osd& o) { return !o.title.empty() || !o.clock.empty(); }

} // namespace OmniVideoKeys
