// OMNI_OLED_CARE_V1: the pure part of "OLED care" (no SDL, no WebKit): the settings file, the idle timer (bars and
// pointer fade after 20 s, the dim after N min with nothing playing), the slow +-2 px shift cycle of the static UI, the
// canvas row helpers (shift inside a band, blend over the saved rows), the clock's spot, and the wake rules (any button
// wakes the dim screen and is swallowed, with its release). Shell side: OmniOledCareShell.h; reasons:
// tools/apply_oled_care.py. Tested on the host with g++ (tools/test_oled_care.cpp).
#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>

namespace OmniOledCare {

constexpr const char* kFileName = "oled-care.txt";
constexpr long kMaxFileBytes = 1024;
constexpr uint32_t kFadeAfterMs = 20000;        // bars and pointer fade after 20 s without input
constexpr uint32_t kFadeMs = 1200;              // the fade itself (Reduce motion: at once)
constexpr uint32_t kFadedK = 38;                // ~15 % opacity, of 256
constexpr uint32_t kKStep = 8;                  // opacity steps (each step is one whole draw while fading)
constexpr uint32_t kShiftEveryMs = 3 * 60 * 1000;   // the static UI moves every 3 min
constexpr int kShiftMax = 2;                    // +-2 px (layout px; the shell scales them to canvas pixels)
constexpr int kShiftCycle = 24;                 // steps before the path repeats (72 min)
constexpr int kDimChoices[] = { 5, 10, 20 };    // "Dim screen after" minutes
constexpr int kDefaultDim = 10;
constexpr int kTriggerPress = 8000, kTriggerRelease = 4000;   // trigger axis values (0..32767)
constexpr uint32_t kTextAfterKeyMs = 250;       // a text event this soon after a waking key is that key's text

struct Settings {
    bool on = false;
    int dimMinutes = kDefaultDim;               // 5 / 10 / 20
};

inline bool validDim(int m) { for (int c : kDimChoices) if (c == m) return true; return false; }
inline int stepDim(int m, int dir)
{
    int i = 1;
    for (int k = 0; k < 3; ++k) if (kDimChoices[k] == m) i = k;
    i = (i + (dir < 0 ? 2 : 1)) % 3;            // wraps: 5 -> 10 -> 20 -> 5
    return kDimChoices[i];
}
inline std::string serialize(const Settings& s)
{
    return std::string("# Omni OLED care (OMNI_OLED_CARE_V1)\non\t") + (s.on ? "1" : "0") + "\ndim\t"
        + std::to_string(validDim(s.dimMinutes) ? s.dimMinutes : kDefaultDim) + "\n";
}
// Unknown keys, bad values and comments are ignored (each bad value keeps its default).
inline Settings parse(const std::string& text)
{
    Settings s;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t e = text.find('\n', pos);
        if (e == std::string::npos) e = text.size();
        std::string line = text.substr(pos, e - pos);
        pos = e + 1;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#') continue;
        const size_t tab = line.find('\t');
        if (tab == std::string::npos) continue;
        const std::string k = line.substr(0, tab), v = line.substr(tab + 1);
        if (k == "on" && (v == "0" || v == "1")) s.on = v == "1";
        else if (k == "dim" && (v == "5" || v == "10" || v == "20")) s.dimMinutes = std::stoi(v);
    }
    return s;
}

// --- idle timer -------------------------------------------------------------------------------------------------
// Times are SDL_GetTicks() milliseconds (wrap-safe differences).
inline float ease(float t) { t = std::clamp(t, 0.0f, 1.0f); return t * t * (3 - 2 * t); }
class Idle {
public:
    void input(uint32_t now) { input_ = now; }
    void block(uint32_t now) { block_ = now; }          // something plays (or a full-screen video / game mode): no dim
    uint32_t sinceInput(uint32_t now) const { return now - input_; }
    // Bars / pointer opacity of 256: 256 until 20 s without input, then down to kFadedK (in kKStep steps).
    uint32_t fadeK(uint32_t now, bool reduceMotion) const
    {
        const uint32_t idle = now - input_;
        if (idle < kFadeAfterMs) return 256;
        if (reduceMotion || idle - kFadeAfterMs >= kFadeMs) return kFadedK;
        const float t = ease(float(idle - kFadeAfterMs) / float(kFadeMs));
        const uint32_t k = uint32_t(256.0f - float(256 - kFadedK) * t + 0.5f);
        return std::max(kFadedK, std::min<uint32_t>(256, (k + kKStep / 2) / kKStep * kKStep));
    }
    // The dim: N minutes without input AND without anything playing (the later of the two starts the wait).
    bool dimDue(uint32_t now, int minutes) const
    {
        const uint32_t need = uint32_t(std::max(1, minutes)) * 60000u;
        return now - input_ >= need && now - block_ >= need;
    }
private:
    uint32_t input_ = 0, block_ = 0;
};

// --- shift cycle ------------------------------------------------------------------------------------------------
struct Offset { int dx = 0, dy = 0; };
// A triangle wave 0, 1, 2, 1, 0, -1, -2, -1 (period 8, never more than 1 px per step).
inline int tri(int i) { static const int T[8] = { 0, 1, 2, 1, 0, -1, -2, -1 }; return T[((i % 8) + 8) % 8]; }
// Step s of the 24-step path: x moves every step, y every third step (each move is 1 px on one or both axes).
inline Offset shiftAt(int step)
{
    const int s = ((step % kShiftCycle) + kShiftCycle) % kShiftCycle;
    return Offset { tri(s), tri(s / 3) };
}
inline int shiftStep(uint32_t now) { return int((now / kShiftEveryMs) % uint32_t(kShiftCycle)); }
// Layout px -> canvas px, symmetric around 0 (2 px at 3x: 6; -2 px: -6).
inline int toCanvas(int px, double scale) { const int a = int(std::abs(px) * scale + 0.5); return px < 0 ? -a : a; }

// --- canvas rows --------------------------------------------------------------------------------------------------
// Moves the pixels of rows [inset, rows - inset) of a band by (dx, dy), each source clamped into that inner band
// (the exposed edge repeats the band's own edge pixels: the bar's background). Rows outside the inner band (a bar's
// hairline edges) stay. stride is in pixels.
inline void shiftBand(uint32_t* px, size_t stride, int w, int rows, int dx, int dy, int inset)
{
    const int a = std::max(0, inset), b = rows - std::max(0, inset);
    if (b - a < 1 || w < 1 || (!dx && !dy)) return;
    dx = std::clamp(dx, -(w - 1), w - 1);
    if (dy > 0) {
        for (int y = b - 1; y >= a; --y) { const int s = std::max(a, y - dy); if (s != y) memcpy(px + size_t(y) * stride, px + size_t(s) * stride, size_t(w) * 4); }
    } else if (dy < 0) {
        for (int y = a; y < b; ++y) { const int s = std::min(b - 1, y - dy); if (s != y) memcpy(px + size_t(y) * stride, px + size_t(s) * stride, size_t(w) * 4); }
    }
    if (!dx) return;
    for (int y = a; y < b; ++y) {
        uint32_t* r = px + size_t(y) * stride;
        if (dx > 0) { const uint32_t edge = r[0]; memmove(r + dx, r, size_t(w - dx) * 4); for (int i = 0; i < dx; ++i) r[i] = edge; }
        else { const int d = -dx; const uint32_t edge = r[w - 1]; memmove(r, r + d, size_t(w - d) * 4); for (int i = w - d; i < w; ++i) r[i] = edge; }
    }
}
// d = d * k / 256 + under * (256 - k) / 256 on all four bytes (as omniFadeEnd: any channel order; with the zero-copy
// page's transparent rows under a bar this leaves premultiplied colour, which omni_zc_page.comp expects).
inline void blendRow(uint32_t* d, const uint32_t* under, int n, uint32_t k)
{
    if (k >= 256) return;
    const uint32_t q = 256 - k;
    for (int i = 0; i < n; ++i) {
        const uint32_t a = d[i], b = under[i];
        d[i] = ((((a & 0x00ff00ffu) * k + (b & 0x00ff00ffu) * q) >> 8) & 0x00ff00ffu) | ((((a >> 8) & 0x00ff00ffu) * k + ((b >> 8) & 0x00ff00ffu) * q) & 0xff00ff00u);
    }
}
inline uint8_t pointerAlpha(uint8_t alpha, uint32_t k) { return uint8_t((uint32_t(alpha) * std::min<uint32_t>(k, 256) + 128) >> 8); }

// --- the dim screen's clock ----------------------------------------------------------------------------------------
// Centre of the clock for minute m of the day: a new spot every minute (the clock itself never stays in one place),
// inside the screen with the box (bw x bh) and a margin of 40 px. Deterministic (a small integer hash).
struct Spot { int x = 0, y = 0; };
inline Spot clockSpot(int minute, int w, int h, int bw, int bh)
{
    uint32_t v = uint32_t(minute) * 2654435761u;
    v ^= v >> 15; v *= 2246822519u; v ^= v >> 13;
    const int mx = 40 + bw / 2, my = 40 + bh / 2;
    const int rx = std::max(1, w - 2 * mx), ry = std::max(1, h - 2 * my);
    return Spot { mx + int(v % uint32_t(rx)), my + int((v >> 16) % uint32_t(ry)) };
}
constexpr uint8_t kClockGrey = 96, kHintGrey = 56;   // dim greys on black

// --- wake rules ---------------------------------------------------------------------------------------------------
enum class Kind { Button, ButtonUp, Key, KeyUp, Text, MouseDown, MouseUp, Motion, Wheel, TouchDown, TouchUp, TouchMotion,
                  Stick, Trigger, Raw, Other };
// a: device / pad (which), b: button, scancode, mouse button, finger or axis; value: trigger axis value.
struct Ev { Kind kind = Kind::Other; int a = 0, b = 0, value = 0; };
struct Result { bool swallow = false, wake = false, input = false; };
inline bool isInput(const Ev& e)
{
    switch (e.kind) {
    case Kind::Raw: case Kind::Other: return false;
    case Kind::Trigger: return e.value >= kTriggerPress;
    default: return true;
    }
}
inline bool wakes(const Ev& e)
{
    switch (e.kind) {
    case Kind::Button: case Kind::Key: case Kind::MouseDown: case Kind::TouchDown: case Kind::Wheel: case Kind::Motion:
    case Kind::Stick: return true;
    case Kind::Trigger: return e.value >= kTriggerPress;
    default: return false;
    }
}
// While dimmed every input event is swallowed; the first that wakes ends the dim, and its release (button / key /
// mouse button / finger up, the trigger falling back, the key's text) is swallowed afterwards too.
class WakeGate {
public:
    bool dimmed() const { return dimmed_; }
    void setDimmed(bool d) { dimmed_ = d; }
    int pending() const { return n_; }
    Result handle(const Ev& e, uint32_t now)
    {
        Result r;
        r.input = isInput(e);
        if (dimmed_) {
            if (e.kind == Kind::Other) return r;
            r.swallow = true;
            if (wakes(e)) { dimmed_ = false; r.wake = true; remember(e, now); }
            return r;
        }
        if (n_ && takePending(e, now)) r.swallow = true;
        return r;
    }
private:
    struct P { Kind up; int a, b; uint32_t at; };
    static constexpr int kMax = 8;
    P p_[kMax] {};
    int n_ = 0;
    bool dimmed_ = false;
    void add(Kind up, int a, int b, uint32_t now)
    {
        if (n_ == kMax) { for (int i = 1; i < kMax; ++i) p_[i - 1] = p_[i]; --n_; }
        p_[n_++] = P { up, a, b, now };
    }
    void drop(int i) { for (int j = i + 1; j < n_; ++j) p_[j - 1] = p_[j]; --n_; }
    void remember(const Ev& e, uint32_t now)
    {
        switch (e.kind) {
        case Kind::Button: add(Kind::ButtonUp, e.a, e.b, now); break;
        case Kind::Key: add(Kind::KeyUp, e.a, e.b, now); add(Kind::Text, 0, 0, now); break;
        case Kind::MouseDown: add(Kind::MouseUp, e.a, e.b, now); break;
        case Kind::TouchDown: add(Kind::TouchUp, e.a, e.b, now); break;
        case Kind::Trigger: add(Kind::Trigger, e.a, e.b, now); break;
        default: break;
        }
    }
    bool takePending(const Ev& e, uint32_t now)
    {
        for (int i = 0; i < n_; ++i) {
            P& q = p_[i];
            if (q.up == Kind::Text) {
                if (now - q.at > kTextAfterKeyMs) { drop(i--); continue; }
                if (e.kind == Kind::Text) { drop(i); return true; }
                continue;
            }
            if (q.a != e.a || q.b != e.b) continue;
            if (q.up == Kind::Trigger && e.kind == Kind::Trigger) {   // the waking trigger: swallowed until it is let go
                if (e.value <= kTriggerRelease) drop(i);
                return true;
            }
            if (e.kind == q.up) { drop(i); return true; }
            // The same button / key pressed again (its release was lost): it is a new press, not the waking one.
            if ((q.up == Kind::ButtonUp && e.kind == Kind::Button) || (q.up == Kind::KeyUp && e.kind == Kind::Key)
                || (q.up == Kind::MouseUp && e.kind == Kind::MouseDown) || (q.up == Kind::TouchUp && e.kind == Kind::TouchDown))
                { drop(i); return false; }
        }
        return false;
    }
};

// --- texts --------------------------------------------------------------------------------------------------------
inline const char* onValue(bool on) { return on ? "On" : "Off"; }
inline std::string onDetail(bool on)
{
    return on ? "Bars and pointer fade after 20 s idle; Omni's bars move a little every 3 min"
              : "Protects OLED TVs from burn-in: fades and moves Omni's bars, dims the screen when idle";
}
inline std::string dimValue(int m) { return std::to_string(validDim(m) ? m : kDefaultDim) + " min"; }
constexpr const char* kDimDetail = "Black screen with a clock when nothing plays. Any button wakes it (that press does nothing else)";
constexpr const char* kWakeHint = "Press any button";

} // namespace OmniOledCare
