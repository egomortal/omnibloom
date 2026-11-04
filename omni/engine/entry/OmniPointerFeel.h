// OMNI_FEATURES_V1: pointer feel. Left stick: radial dead zone and an acceleration curve (slow and
// precise near the centre, fast at full tilt; speed setting in Browser settings), frame-time based.
// When the stick is released the pointer eases onto the nearest link / button / field within ~36 px
// (one small read-only hit-test script per release, so it is always current after scrolling).
// Right stick: vertical scroll as before, horizontal scroll added.
#pragma once

static const char* const omniFxSnapScript = R"JS((function(x,y,R){try{var d=document,S='a[href],button,input:not([type=hidden]),select,textarea,summary,label[for],[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=option],[onclick],[tabindex]:not([tabindex="-1"])';
var W=innerWidth*innerHeight;function ok(t){if(!t||t===d.body||t===d.documentElement)return false;var b=t.getBoundingClientRect();return b.width>=2&&b.height>=2&&b.width*b.height<W*0.25;}
var h=d.elementFromPoint(x,y),hc=h&&h.closest?h.closest(S):null;if(ok(hc))return'in';
var best=null,bd=1e12,seen=[];
for(var ring=1;ring<=4&&!best;ring++){var rr=R*ring/4;for(var k=0;k<12;k++){var a=k*Math.PI/6,e=d.elementFromPoint(x+rr*Math.cos(a),y+rr*Math.sin(a));
if(!e||!e.closest)continue;var t=e.closest(S);if(!ok(t)||seen.indexOf(t)>=0)continue;seen.push(t);
var b=t.getBoundingClientRect(),ix=Math.min(6,b.width/4),iy=Math.min(6,b.height/4);
var tx=Math.max(b.left+ix,Math.min(x,b.right-ix)),ty=Math.max(b.top+iy,Math.min(y,b.bottom-iy)),dd=(tx-x)*(tx-x)+(ty-y)*(ty-y);
if(dd<bd){var c=d.elementFromPoint(tx,ty);if(c&&(c===t||t.contains(c))){bd=dd;best=[tx,ty];}}}}
return best?JSON.stringify({x:best[0],y:best[1]}):'none';}catch(err){return'none';}})()JS";

struct OmniFxPointer {
    bool moving = false;
    uint32_t last = 0, seq = 0;
    bool anim = false; float fromX = 0, fromY = 0, toX = 0, toY = 0; uint32_t animStart = 0;
};
static OmniFxPointer omniFxPtr;
static bool omniFxPointerOnPage()
{
    return active() && !active()->crashed && !pageFullscreen && !settingsOpen && !editing && !omniOverlayOpen()
        && pointerY >= omniPageTop() && pointerY < omniPageBottom();
}
struct OmniFxSnapQuery { const void* tab; uint32_t seq; float px, py; double k; int top; };
static void omniFxSnapRequest()
{
    omniFxLoad();
    Tab* t = active();
    if (!omniFxSet.snap || omniTestMode() || !omniFxPointerOnPage() || !t) return;
    const double k = omniFxCssPerLayout(t);
    char head[128];
    snprintf(head, sizeof(head), "(function(){var X=%.1f,Y=%.1f,R=%.1f;return ", pointerX * k, (pointerY - omniPageTop()) * k, 36 * k);
    std::string js = omniFxSnapScript;
    js.replace(js.size() - 2, 2, "(X,Y,R);})()");
    js = std::string(head) + js;
    auto src = adoptWK(WKStringCreateWithUTF8CString(js.c_str()));
    auto* q = new OmniFxSnapQuery { t, omniFxPtr.seq, pointerX, pointerY, k, omniPageTop() };
    WKPageEvaluateJavaScriptInMainFrame(t->page, src.get(), q, [](WKTypeRef result, WKErrorRef error, void* context) {
        std::unique_ptr<OmniFxSnapQuery> q(static_cast<OmniFxSnapQuery*>(context));
        // Only if nothing moved since: same tab, stick still released, pointer and bars where they were.
        if (active() != q->tab || q->seq != omniFxPtr.seq || omniFxPtr.moving || pointerX != q->px || pointerY != q->py || omniPageTop() != q->top) return;
        const std::string json = omniFxResultString(result, error);
        double x = 0, y = 0;
        if (json.empty() || json[0] != '{' || !omniFxJsonNumber(json, "x", x) || !omniFxJsonNumber(json, "y", y)) return;
        const float tx = std::clamp(float(x / q->k), 0.f, float(width - 1)), ty = std::clamp(float(y / q->k + q->top), float(omniPageTop()), float(omniPageBottom() - 1));
        if (std::fabs(tx - pointerX) < 1 && std::fabs(ty - pointerY) < 1) return;
        omniFxPtr.anim = true; omniFxPtr.fromX = pointerX; omniFxPtr.fromY = pointerY; omniFxPtr.toX = tx; omniFxPtr.toY = ty; omniFxPtr.animStart = SDL_GetTicks();
    });
}
static void omniFxHorizontalScroll(double amount)
{
    Tab* t = active();
    if (!t || settingsOpen || pageFullscreen || omniOverlayOpen()) return;
    if (omniMediaDownloadsEnabled && omniSavedOwnedView() != OmniSavedView::None) return;
    WKPageHandleWheelEvent(t->page, WKWheelEventMake(kWKEventWheel,
        WKPointMake(pointerX * displayScale * omniPageScale, std::clamp<double>(pointerY - omniPageTop(), 0, omniPageBottom() - omniPageTop() - 1) * displayScale * omniPageScale),
        WKSizeMake(amount * displayScale * omniPageScale, 0), WKSizeMake(amount / 40, 0), 0));
}
// OMNI_STICK_DEADZONE_V1: one "Stick dead zone" setting (Browser settings) for every stick use: left-stick pointer, right-stick
// scrolling (both axes, menus and dialogs included), keyboard stick focus / caret / scroll, which pad is active, and the
// "stick activity" that keeps the auto-hiding bars shown (the fullscreen video's own controls only see pointer moves).
// Radii are fractions of full deflection. Medium is exactly what was used before: left stick 0.20 radial, right stick
// 7000/32768 (0.2136) per axis. Small is 30 % smaller; Large and Extra large are for drifting sticks. Test modes use Medium.
static const float omniStickDzLeft[]  = { 0.14f, 0.20f, 0.28f, 0.38f };
static const float omniStickDzRight[] = { 0.15f, 7000.f / 32768.f, 0.28f, 0.38f };
static int omniStickDzIndex() { if (omniTestMode()) return 1; omniFxLoad(); return std::clamp(omniFxSet.deadzone, 0, 3); }
static float omniStickDeadZone(bool right) { return (right ? omniStickDzRight : omniStickDzLeft)[omniStickDzIndex()]; }
static float omniStickRadius(SDL_GameController* c, bool right)
{
    if (!c) return 0;
    return std::hypot(SDL_GameControllerGetAxis(c, right ? SDL_CONTROLLER_AXIS_RIGHTX : SDL_CONTROLLER_AXIS_LEFTX) / 32768.f,
                      SDL_GameControllerGetAxis(c, right ? SDL_CONTROLLER_AXIS_RIGHTY : SDL_CONTROLLER_AXIS_LEFTY) / 32768.f);
}
// A threshold placed for the Medium dead zone (keyboard: left stick 14000, right stick 20000) keeps its position on the
// rescaled range above the chosen dead zone. Medium returns it unchanged.
static float omniStickGate(bool right, float medium)
{
    const int i = omniStickDzIndex();
    if (i == 1) return medium;
    const float* t = right ? omniStickDzRight : omniStickDzLeft;
    return t[i] + (1 - t[i]) * std::max(0.f, (medium - t[1]) / (1 - t[1]));
}
// Factor for raw stick values (right stick scrolling): 0 inside the radial dead zone; past it the radius is rescaled from 0 at
// the edge and laid onto the range scrolling always had (the Medium edge .. full tilt), so nothing jumps and full tilt is
// unchanged. Medium: exactly 1 (the raw values, as before).
static float omniStickScale(SDL_GameController* c, bool right)
{
    const int i = omniStickDzIndex();
    const float* t = right ? omniStickDzRight : omniStickDzLeft;
    const float r = omniStickRadius(c, right), d = t[i];
    if (r <= d) return 0;
    if (i == 1) return 1;
    const float m = std::min(1.f, (r - d) / (1 - d));
    return (t[1] + (1 - t[1]) * m) / r;
}
static bool omniStickRightAxis(int axis) { return axis == SDL_CONTROLLER_AXIS_RIGHTX || axis == SDL_CONTROLLER_AXIS_RIGHTY; }
// An axis event that counts as stick activity (bars, active pad). Medium: |value| > 7000, as before; other sizes also need the
// stick's radius outside its dead zone. Triggers keep 7000.
static bool omniStickAxisLive(const SDL_ControllerAxisEvent& e)
{
    if (e.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || e.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT) return abs(e.value) > 7000;
    if (abs(e.value) <= omniStickDzRight[omniStickDzIndex()] * 32768.f) return false;
    SDL_GameController* p = SDL_GameControllerFromInstanceID(e.which);
    const bool right = omniStickRightAxis(e.axis);
    return !p || omniStickRadius(p, right) > omniStickDeadZone(right);
}
// A stick event inside the dead zone (drift): nothing it could drive moves, so it asks for no redraw at all.
static bool omniStickQuietEvent(const SDL_Event& e)
{
    if (e.type != SDL_CONTROLLERAXISMOTION || e.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT || e.caxis.axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT) return false;
    if (omniStickAxisLive(e.caxis)) return false;
    SDL_GameController* p = SDL_GameControllerFromInstanceID(e.caxis.which);
    const bool right = omniStickRightAxis(e.caxis.axis);
    return !p || omniStickRadius(p, right) <= omniStickDeadZone(right);
}
// Called from tick() while a controller is connected and the keyboard is closed (replaces the
// constant 16 px per pass movement and the right-stick block).
static void omniFxStickTick()
{
    omniFxLoad();
    const uint32_t now = SDL_GetTicks();
    const float dt = std::clamp((now - omniFxPtr.last) / 1000.f, 0.004f, 0.05f);
    omniFxPtr.last = now;
    const float sx = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTX) / 32768.f;
    const float sy = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTY) / 32768.f;
    const float r = std::hypot(sx, sy), dead = omniStickDeadZone(false); // OMNI_STICK_DEADZONE_V1: was 0.2f (= Medium)
    if (r > dead) {
        const float m = std::min(1.f, (r - dead) / (1 - dead));
        const float speed = omniFxPointerSpeed[std::clamp(omniFxSet.pointer, 0, 3)] * (0.05f + 0.95f * std::pow(m, 2.3f));
        pointerX = std::clamp(pointerX + sx / r * speed * dt, 0.f, float(width - 1));
        pointerY = std::clamp(pointerY + sy / r * speed * dt, 0.f, float(height - 1));
        omniFxPtr.moving = true; omniFxPtr.anim = false; ++omniFxPtr.seq;
        omniShellDirty = true; omniChromeWake(true); mouse(kWKEventMouseMove); // OMNI_SHELL_DRAW_V1, OMNI_STYLE_V1
    } else if (omniFxPtr.moving) {
        omniFxPtr.moving = false;
        omniFxSnapRequest();
    }
    if (omniFxPtr.anim) {
        const float t = std::min(1.f, (now - omniFxPtr.animStart) / 110.f), e = 1 - (1 - t) * (1 - t) * (1 - t);
        pointerX = omniFxPtr.fromX + (omniFxPtr.toX - omniFxPtr.fromX) * e;
        pointerY = omniFxPtr.fromY + (omniFxPtr.toY - omniFxPtr.fromY) * e;
        if (t >= 1) omniFxPtr.anim = false;
        omniShellDirty = true; mouse(kWKEventMouseMove);
    }
    // OMNI_STICK_DEADZONE_V1: radial dead zone with rescaling (omniStickScale); an axis inside the dead zone by itself adds nothing, as before.
    const float dzRaw = omniStickDeadZone(true) * 32768.f, k = omniStickScale(controller, true);
    auto axis = [&](Sint16 v) { return k > 0 && abs(v) > dzRaw ? static_cast<float>(v) / 32768 * k : 0.f; };
    const float wheel = axis(SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_RIGHTY));
    if (wheel) { omniChromeScroll(); scroll(-wheel * 55); } // OMNI_STYLE_V1
    const float side = axis(SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_RIGHTX));
    if (side && std::fabs(side) > std::fabs(wheel) * 0.6f) { omniChromeScroll(); omniFxHorizontalScroll(-side * 55); }
}
