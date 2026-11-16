/* OMNI_PAD_TEST_V1: Controller test page, pure logic (no DOM). Tested by tools/test_pad_test_page.cjs in node.
   Input comes from two places, the same state shape out of both:
   - the shell (OmniPadTestShell.h) calls window.omniPadTest(msg) at most 30 times a second while this page is shown:
     raw SDL values (sticks -32768..32767, triggers 0..32767), every button incl. the touchpad press, touch points,
     battery, and the dead-zone radii Omni uses (OmniPointerFeel.h, setting "Stick dead zone");
   - otherwise (no push for 2.5 s: a desktop browser, an older Omni) the web Gamepad API (standard mapping). */
(function (root) {
  'use strict';

  // id, SDL_GameControllerButton index, standard Gamepad API index, PlayStation label, Xbox label
  var BUTTONS = [
    ['cross', 0, 0, 'Cross', 'A'], ['circle', 1, 1, 'Circle', 'B'], ['square', 2, 2, 'Square', 'X'],
    ['triangle', 3, 3, 'Triangle', 'Y'], ['create', 4, 8, 'Create', 'View'], ['ps', 5, 16, 'PS', 'Xbox'],
    ['options', 6, 9, 'Options', 'Menu'], ['l3', 7, 10, 'L3', 'LS'], ['r3', 8, 11, 'R3', 'RS'],
    ['l1', 9, 4, 'L1', 'LB'], ['r1', 10, 5, 'R1', 'RB'], ['up', 11, 12, 'Up', 'Up'], ['down', 12, 13, 'Down', 'Down'],
    ['left', 13, 14, 'Left', 'Left'], ['right', 14, 15, 'Right', 'Right'], ['mute', 15, -1, 'Mic', 'Share'],
    ['touchpad', 20, -1, 'Touchpad', 'Touchpad']
  ];
  var DZ_NAMES = ['Small', 'Medium', 'Large', 'Extra large'];
  // OmniPointerFeel.h omniStickDzLeft / omniStickDzRight (used when the shell sends nothing)
  var DZ_DEFAULT = { index: 1, left: [0.14, 0.20, 0.28, 0.38], right: [0.15, 7000 / 32768, 0.28, 0.38] };
  var DRIFT_WINDOW_MS = 3000;  // the stick must rest this long before a drift figure is shown
  var IDLE_LIMIT = 0.5;        // a stick past half travel is being moved: the drift window starts again
  var MARGIN = 0.03;           // a suggested dead zone clears the measured drift by 3 % of full travel
  var PUSH_STALE_MS = 2500;    // no push for this long: the Gamepad API is read instead
  var TRAIL = 24;

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function num(v, d) { return typeof v === 'number' && isFinite(v) ? v : d; }
  function axisRaw(v) { v = num(v, 0); return v < 0 ? clamp(v / 32768, -1, 0) : clamp(v / 32767, 0, 1); }
  function trigRaw(v) { return clamp(num(v, 0) / 32767, 0, 1); }

  function empty(source) {
    var b = {};
    BUTTONS.forEach(function (x) { b[x[0]] = false; });
    return { source: source, pad: false, buttons: b, lx: 0, ly: 0, rx: 0, ry: 0, l2: 0, r2: 0,
      raw: { lx: 0, ly: 0, rx: 0, ry: 0, l2: 0, r2: 0 }, touch: [], battery: null, dz: DZ_DEFAULT, holdMs: 0, name: '' };
  }

  function dzFrom(msg) {
    var ok = function (a) { return Array.isArray(a) && a.length === 4 && a.every(function (v) { return typeof v === 'number' && v > 0 && v < 10000; }); };
    if (!ok(msg.dzl) || !ok(msg.dzr)) return DZ_DEFAULT;
    return { index: clamp(Math.round(num(msg.dz, 1)), 0, 3),
      left: msg.dzl.map(function (v) { return v / 10000; }), right: msg.dzr.map(function (v) { return v / 10000; }) };
  }

  // The shell's push: {"v":1,"pad":1,"b":<bits>,"ax":[lx,ly,rx,ry,l2,r2],"tp":[[on,x,y],[on,x,y]],"bat":-1..4,"dz":i,"dzl":[..],"dzr":[..],"hold":ms}
  function fromPush(msg) {
    var s = empty('shell');
    if (!msg || typeof msg !== 'object' || msg.v !== 1) return null;
    s.dz = dzFrom(msg);
    s.holdMs = clamp(num(msg.hold, 0), 0, 5000);
    s.battery = batteryText(msg.bat);
    if (!msg.pad) return s;
    s.pad = true;
    var bits = num(msg.b, 0) >>> 0;
    BUTTONS.forEach(function (x) { s.buttons[x[0]] = ((bits >>> x[1]) & 1) === 1; });
    var ax = Array.isArray(msg.ax) ? msg.ax : [];
    s.raw = { lx: num(ax[0], 0), ly: num(ax[1], 0), rx: num(ax[2], 0), ry: num(ax[3], 0), l2: num(ax[4], 0), r2: num(ax[5], 0) };
    s.lx = axisRaw(ax[0]); s.ly = axisRaw(ax[1]); s.rx = axisRaw(ax[2]); s.ry = axisRaw(ax[3]);
    s.l2 = trigRaw(ax[4]); s.r2 = trigRaw(ax[5]);
    (Array.isArray(msg.tp) ? msg.tp : []).slice(0, 2).forEach(function (f) {
      if (Array.isArray(f) && f[0]) s.touch.push({ x: clamp(num(f[1], 0) / 1000, 0, 1), y: clamp(num(f[2], 0) / 1000, 0, 1) });
    });
    return s;
  }

  // A Gamepad API pad (standard mapping). Raw values are shown on the shell's scale so both sources read alike.
  function fromGamepad(gp) {
    var s = empty('gamepad');
    if (!gp || !gp.connected) return s;
    s.pad = true;
    s.name = String(gp.id || '').slice(0, 80);
    var bt = gp.buttons || [], ax = gp.axes || [];
    var pressed = function (i) { var b = bt[i]; return !!(b && (b.pressed || num(b.value, 0) > 0.5)); };
    BUTTONS.forEach(function (x) { if (x[2] >= 0) s.buttons[x[0]] = pressed(x[2]); });
    s.lx = clamp(num(ax[0], 0), -1, 1); s.ly = clamp(num(ax[1], 0), -1, 1);
    s.rx = clamp(num(ax[2], 0), -1, 1); s.ry = clamp(num(ax[3], 0), -1, 1);
    s.l2 = clamp(num(bt[6] && bt[6].value, 0), 0, 1); s.r2 = clamp(num(bt[7] && bt[7].value, 0), 0, 1);
    var toRaw = function (v) { return Math.round(v < 0 ? v * 32768 : v * 32767); };
    s.raw = { lx: toRaw(s.lx), ly: toRaw(s.ly), rx: toRaw(s.rx), ry: toRaw(s.ry), l2: toRaw(s.l2), r2: toRaw(s.r2) };
    return s;
  }

  function batteryText(level) {
    switch (level) {
      case 0: return 'Empty'; case 1: return 'Low'; case 2: return 'Medium'; case 3: return 'Full'; case 4: return 'Charging (wired)';
      default: return null;   // -1 / missing: the console does not report it
    }
  }

  // Which source to show: a recent push wins; else the first connected Gamepad API pad; else the last push (the shell
  // pauses while Omni's menu is open over the page); else "no controller".
  function pick(now, lastPushAt, pushState, pads) {
    if (pushState && now - lastPushAt <= PUSH_STALE_MS) return pushState;
    var list = pads ? Array.prototype.slice.call(pads) : [];
    for (var i = 0; i < list.length; ++i) if (list[i] && list[i].connected) return fromGamepad(list[i]);
    return pushState || empty('none');
  }

  // Drift: the largest distance from the centre while the stick rests (never past IDLE_LIMIT) for DRIFT_WINDOW_MS.
  function DriftMeter() { this.reset(); }
  DriftMeter.prototype.reset = function () { this.samples = []; this.since = null; this.ready = false; this.max = 0; this.maxX = 0; this.maxY = 0; };
  DriftMeter.prototype.feed = function (t, x, y) {
    var r = Math.hypot(x, y);
    if (r > IDLE_LIMIT) { this.reset(); return; }
    if (this.since === null) this.since = t;
    this.samples.push({ t: t, r: r, x: Math.abs(x), y: Math.abs(y) });
    while (this.samples.length && t - this.samples[0].t > DRIFT_WINDOW_MS) this.samples.shift();
    var m = 0, mx = 0, my = 0;
    this.samples.forEach(function (s) { if (s.r > m) m = s.r; if (s.x > mx) mx = s.x; if (s.y > my) my = s.y; });
    this.max = m; this.maxX = mx; this.maxY = my;
    this.ready = t - this.since >= DRIFT_WINDOW_MS;
  };
  DriftMeter.prototype.progress = function (t) { return this.since === null ? 0 : clamp((t - this.since) / DRIFT_WINDOW_MS, 0, 1); };

  function pct(v) { return (Math.round(v * 1000) / 10).toFixed(1) + '%'; }

  // Text only: which "Stick dead zone" size covers both sticks' measured drift (never changes the setting).
  function suggest(driftL, driftR, dz) {
    dz = dz || DZ_DEFAULT;
    var need = -1;
    for (var i = 0; i < 4; ++i) if (dz.left[i] >= driftL + MARGIN && dz.right[i] >= driftR + MARGIN) { need = i; break; }
    var cur = clamp(dz.index, 0, 3), where = 'Browser settings > Stick dead zone';
    if (need < 0) return { index: -1, level: 'bad',
      text: 'Drift is past even Extra large (' + pct(dz.left[3]) + '). The stick needs cleaning or repair; ' + where + ' > Extra large helps most meanwhile.' };
    if (need === cur) return { index: need, level: 'ok', text: 'Your setting fits: ' + DZ_NAMES[cur] + ' covers this drift.' };
    if (need > cur) return { index: need, level: 'warn',
      text: 'Suggested: ' + DZ_NAMES[need] + ' (now ' + DZ_NAMES[cur] + '). Change it in ' + where + '.' };
    return { index: need, level: 'ok',
      text: 'Your setting (' + DZ_NAMES[cur] + ') covers this drift; ' + DZ_NAMES[need] + ' would too and feels more precise (' + where + ').' };
  }

  function Trail(n) { this.n = n || TRAIL; this.points = []; }
  Trail.prototype.add = function (x, y) {
    var last = this.points[this.points.length - 1];
    if (last && Math.abs(last.x - x) < 0.004 && Math.abs(last.y - y) < 0.004) return false;
    this.points.push({ x: x, y: y });
    if (this.points.length > this.n) this.points.shift();
    return true;
  };

  function label(id, glyphs) {
    for (var i = 0; i < BUTTONS.length; ++i) if (BUTTONS[i][0] === id) return glyphs === 'xbox' ? BUTTONS[i][4] : BUTTONS[i][3];
    return id;
  }
  function leaveHint(glyphs) {
    return glyphs === 'xbox' ? 'Hold B for 1 second to leave · Menu: Omni\'s menu' : 'Hold Circle for 1 second to leave · Options: Omni\'s menu';
  }

  var M = { BUTTONS: BUTTONS, DZ_NAMES: DZ_NAMES, DZ_DEFAULT: DZ_DEFAULT, DRIFT_WINDOW_MS: DRIFT_WINDOW_MS, IDLE_LIMIT: IDLE_LIMIT,
    PUSH_STALE_MS: PUSH_STALE_MS, fromPush: fromPush, fromGamepad: fromGamepad, pick: pick, DriftMeter: DriftMeter, suggest: suggest,
    Trail: Trail, label: label, leaveHint: leaveHint, pct: pct, batteryText: batteryText, empty: empty };
  if (typeof module === 'object' && module.exports) module.exports = M; else root.OmniPadModel = M;
})(this);
