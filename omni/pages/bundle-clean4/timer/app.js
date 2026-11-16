/* OMNI_COUCH_TIMER_V1: Couch timer page (DOM side). Pure logic: model.js (tools/test_timer_page.cjs).
   Controller: D-pad moves, Cross chooses, Square start / pause, Triangle lap, L1 / R1 change mode; Circle is Omni's own
   Back except while editing digits (cancel) or ringing (stop). State lives in localStorage as wall-clock targets, so
   a reload or another tab carries on exactly. No network; sound only if this build can play the bundled WAV,
   otherwise the full-screen flash alone. */
(function (root) {
  'use strict';
  if (typeof module === 'object' && module.exports) return;
  var M = root.OmniTimerModel, doc = root.document, host = root.omnibloomHost;
  var $ = function (id) { return doc.getElementById(id); };
  var MIN = 60000;
  var store = null;
  try { store = root.localStorage; } catch (e) { store = null; }
  var kind = 'playstation';
  try { kind = (host && typeof host.getGlyphs === 'function' && host.getGlyphs()) || (store && store.getItem('ob.glyphs')) || 'playstation'; } catch (e) { /* storage off */ }
  kind = kind === 'xbox' ? 'xbox' : 'playstation';

  function now() { return Date.now(); }
  function read() { try { return store ? store.getItem(M.KEY) : null; } catch (e) { return null; } }
  function save() { try { if (store) store.setItem(M.KEY, M.serialize(st)); } catch (e) { /* full or off: keeps running in memory */ } }

  var st = M.restore(read(), now());
  var focus = { r: 1, c: 0 }, edit = null, timer = 0, shown = {}, focusedId = null, lapsKey = '';
  save();

  // --- sound (feature-detected <audio>; Web Audio is off in this WebKit build) --------------------------------------
  var beep = $('beep');
  var sound = { ok: M.canPlayWav(beep), playing: false };
  if (beep) beep.addEventListener('error', function () { sound.ok = false; soundStop(); render(); });
  function soundStart() {
    if (!sound.ok || sound.playing) return;
    sound.playing = true;
    try {
      beep.currentTime = 0;
      var p = beep.play();
      if (p && typeof p.catch === 'function') p.catch(function () { sound.ok = false; sound.playing = false; render(); });
    } catch (e) { sound.ok = false; sound.playing = false; }
  }
  function soundStop() {
    if (!sound.playing) return;
    sound.playing = false;
    try { beep.pause(); beep.currentTime = 0; } catch (e) { /* nothing to stop */ }
  }

  // --- drawing (DOM writes only when a value changed) ---------------------------------------------------------------
  function set(id, key, value) {
    var k = id + '.' + key;
    if (shown[k] === value) return;
    shown[k] = value;
    var el = $(id);
    if (!el) return;
    if (key === 'text') el.textContent = value;
    else if (key === 'class') el.className = value;
    else if (key === 'hidden') el.hidden = value;
    else el.setAttribute(key, value);
  }
  function fields(prefix, vals, showAll) {
    var ids = vals.length === 3 ? ['h', 'm', 's'] : ['h', 'm'];
    var short = vals.length === 3 && !showAll && !vals[0];   // 5:00, not 0:05:00
    ids.forEach(function (f, i) {
      set(prefix + f, 'text', (i === 0 && vals.length === 3) || (i === 1 && short) ? String(vals[i]) : M.pad2(vals[i]));
      set(prefix + f, 'class', 'f' + (edit && edit.prefix === prefix && edit.field === i ? ' sel' : ''));
    });
    if (vals.length === 3) { set(prefix + 'h', 'hidden', short); set(prefix + 'c1', 'hidden', short); }
  }
  function g() { return kind === 'xbox' ? { cross: 'A' } : { cross: 'Cross' }; }

  function render() {
    var t = now(), cd = st.cd, sw = st.sw, al = st.al;
    set('clock', 'text', M.formatClock(t));
    M.MODES.forEach(function (m) {
      set('tab-' + m, 'aria-selected', String(st.mode === m));
      set('panel-' + m, 'hidden', st.mode !== m);
    });
    var left = M.cdRemaining(cd, t), running = M.cdRunning(cd), el = M.swElapsed(sw, t);
    set('badge-countdown', 'text', running ? M.formatCountdown(left) : '');
    set('badge-stopwatch', 'text', sw.start !== null ? M.formatStopwatch(el).main : '');
    set('badge-alarm', 'text', al.at !== null ? M.formatClock(al.at) : '');

    // countdown
    var editingCd = edit && edit.prefix === 'cd-', p = M.countdownParts(left);
    fields('cd-', editingCd ? edit.vals : [p.h, p.m, p.s], editingCd);
    set('cd-display', 'class', 'digits' + (running ? ' run' : '') + (running && left <= 10000 ? ' final' : '') + (editingCd ? ' editing' : ''));
    var paused = !running && left > 0 && left < cd.dur;
    set('cd-note', 'text', editingCd ? 'Set your own time (hours : minutes : seconds)'
      : running ? 'Ends at ' + M.formatClock(cd.end) : paused ? 'Paused' : g().cross + ' on the digits: set your own time');
    set('cd-go', 'text', running ? 'Pause' : paused ? 'Resume' : 'Start');
    M.PRESETS_MIN.forEach(function (m) { set('preset-' + m, 'class', 'chip' + (cd.dur === m * MIN ? ' sel' : '')); });

    // stopwatch
    var f = M.formatStopwatch(el);
    set('sw-main', 'text', f.main);
    set('sw-frac', 'text', f.frac);
    set('sw-go', 'text', sw.start !== null ? 'Stop' : el > 0 ? 'Resume' : 'Start');
    set('sw-lap', 'class', 'act' + (sw.start === null ? ' dim' : ''));
    set('sw-note', 'text', sw.start !== null ? 'Running' : el > 0 ? 'Stopped' : 'Ready');
    var key = sw.laps.join(',');
    if (key !== lapsKey) {
      lapsKey = key;
      var ol = $('sw-laps');
      ol.textContent = '';
      M.lapRows(sw.laps).slice(0, 8).forEach(function (row) {
        var li = doc.createElement('li'), a = doc.createElement('span'), b = doc.createElement('span'), c = doc.createElement('span');
        a.textContent = 'Lap ' + row.n; b.textContent = M.formatStopwatch(row.split).main + M.formatStopwatch(row.split).frac;
        c.textContent = M.formatStopwatch(row.total).main + M.formatStopwatch(row.total).frac;
        b.className = 'split'; c.className = 'total';
        li.appendChild(a); li.appendChild(b); li.appendChild(c); ol.appendChild(li);
      });
    }

    // alarm
    var editingAl = edit && edit.prefix === 'al-';
    fields('al-', editingAl ? edit.vals : [al.h, al.m], true);
    set('al-display', 'class', 'digits' + (al.at !== null ? ' run' : '') + (editingAl ? ' editing' : ''));
    var tomorrow = al.at !== null && new Date(al.at).getDate() !== new Date(t).getDate();
    set('al-note', 'text', editingAl ? 'Set the alarm time (24-hour clock)'
      : al.at !== null ? 'Rings ' + (tomorrow ? 'tomorrow ' : '') + 'at ' + M.formatClock(al.at) + ' · in ' + M.formatIn(al.at - t) : 'Off');
    set('al-go', 'text', al.at !== null ? 'Turn off' : 'Set alarm');

    // missed / ringing
    set('missed', 'hidden', !st.missed);
    if (st.missed) set('missed', 'text', 'Missed: the ' + st.missed.kind + ' ' + (st.missed.kind === 'alarm' ? 'rang' : 'ended') + ' at ' + M.formatClock(st.missed.at));
    set('ring', 'hidden', !st.ring);
    doc.body.className = st.ring ? 'ringing' : '';
    if (st.ring) {
      set('ring-title', 'text', st.ring.kind === 'alarm' ? 'Alarm · ' + M.formatClock(st.ring.since) : 'Time\'s up');
      set('ring-over', 'text', '+' + M.formatStopwatch(t - st.ring.since).main);
      set('ring-hint', 'text', M.hint(kind, 'ring'));
      soundStart();
    } else soundStop();
    set('hint', 'text', M.hint(kind, st.ring ? 'ring' : edit ? 'edit' : 'normal'));
    set('sound', 'text', sound.ok ? 'Sound on' : 'No sound on this console: the screen flashes instead');

    // focus
    var rs = M.rows(st.mode);
    focus = M.navigate(rs, focus, '');
    var id = rs[focus.r][focus.c];
    if (id !== focusedId) {
      if (focusedId && $(focusedId)) $(focusedId).classList.remove('focus');
      focusedId = id;
    }
    var fe = $(id);
    if (fe && !fe.classList.contains('focus')) fe.classList.add('focus');
    if (fe && doc.activeElement !== fe && !st.ring) { try { fe.focus({ preventScroll: true }); } catch (e) { fe.focus(); } }
  }

  // Drift-free loop: each wait is computed from the stored targets (model.nextDelay), never a fixed interval.
  function tick() {
    clearTimeout(timer);
    if (M.check(st, now()).length) save();
    render();
    timer = setTimeout(tick, M.nextDelay(st, now()));
  }

  // --- actions ------------------------------------------------------------------------------------------------------
  function setMode(m, toAction) {
    if (M.MODES.indexOf(m) < 0) return;
    st.mode = m; edit = null;
    var rs = M.rows(m);
    if (toAction) {
      for (var r = 0; r < rs.length; ++r) for (var c = 0; c < rs[r].length; ++c) if (/-go$/.test(rs[r][c])) focus = { r: r, c: c };
    } else focus = { r: 0, c: M.MODES.indexOf(m) };
  }
  function primary() {
    var t = now();
    if (st.mode === 'countdown') M.cdToggle(st.cd, t);
    else if (st.mode === 'stopwatch') M.swToggle(st.sw, t);
    else if (st.al.at !== null) M.alCancel(st.al); else M.alArm(st.al, t);
  }
  function activate(id) {
    var t = now(), m;
    if ((m = /^tab-(\w+)$/.exec(id))) setMode(m[1], false);
    else if ((m = /^preset-(\d+)$/.exec(id))) { M.cdSet(st.cd, +m[1] * MIN); M.cdStart(st.cd, t); }
    else if (id === 'cd-display') {
      M.cdPause(st.cd, t);
      var p = M.countdownParts(st.cd.dur);
      edit = { prefix: 'cd-', vals: [p.h, p.m, p.s], field: p.h ? 0 : 1, limits: M.CD_LIMITS };
    } else if (id === 'al-display') edit = { prefix: 'al-', vals: [st.al.h, st.al.m], field: 0, limits: M.AL_LIMITS };
    else if (id === 'cd-go' || id === 'sw-go' || id === 'al-go') primary();
    else if (id === 'cd-reset') M.cdReset(st.cd);
    else if (id === 'sw-lap') M.swLap(st.sw, t);
    else if (id === 'sw-reset') M.swReset(st.sw);
    else return false;
    return true;
  }
  function commitEdit() {
    var v = edit.vals;
    if (edit.prefix === 'cd-') { var ms = M.hmsToMs(v[0], v[1], v[2]); if (ms > 0) M.cdSet(st.cd, ms); }
    else { st.al.h = v[0]; st.al.m = v[1]; M.alArm(st.al, now()); }
    edit = null;
  }
  function after() { st.missed = null; save(); tick(); return true; }

  function controller(a) {
    if (st.ring) {   // every button is taken while ringing; Cross / Circle / Square stop it
      if (a === 'cross' || a === 'circle' || a === 'square') { M.dismiss(st); return after(); }
      return true;
    }
    var dir = a === 'up' || a === 'down' || a === 'left' || a === 'right';
    if (edit) {
      if (dir && (a === 'up' || a === 'down')) edit.vals = M.editStep(edit.vals, edit.field, a, edit.limits);
      else if (dir) edit.field = M.editField(edit.field, a, edit.vals.length);
      else if (a === 'cross') commitEdit();
      else if (a === 'circle') edit = null;
      else return true;
      return after();
    }
    if (dir) {
      if (focus.r === 0 && (a === 'left' || a === 'right')) {   // Xbox-style blades: moving along them switches mode
        var i = Math.max(0, Math.min(M.MODES.length - 1, M.MODES.indexOf(st.mode) + (a === 'left' ? -1 : 1)));
        setMode(M.MODES[i], false);
      } else focus = M.navigate(M.rows(st.mode), focus, a);
      render();
      return true;
    }
    if (a === 'l1' || a === 'r1') {
      var n = M.MODES.length, j = (M.MODES.indexOf(st.mode) + (a === 'l1' ? n - 1 : 1)) % n;
      setMode(M.MODES[j], true);
      return after();
    }
    if (a === 'cross') { var rs = M.rows(st.mode); return activate(rs[focus.r][focus.c]) ? after() : false; }
    if (a === 'square') { primary(); return after(); }
    if (a === 'triangle') { if (st.mode !== 'stopwatch') return false; M.swLap(st.sw, now()); return after(); }
    return false;   // circle: Omni's own Back
  }
  root.omniMediaController = controller;
  root.omniPadController = controller;

  doc.addEventListener('keydown', function (e) {
    var a = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'cross', Escape: 'circle',
      PageUp: 'l1', PageDown: 'r1' }[e.key];
    if (a && controller(a)) e.preventDefault();
  });
  // Pointer / touch: the clicked control takes focus, then does what Cross would.
  doc.addEventListener('click', function (e) {
    if (st.ring) { controller('cross'); return; }
    var b = e.target && e.target.closest ? e.target.closest('button') : null;
    if (!b || !b.id) return;
    if (edit) { edit = null; }
    var rs = M.rows(st.mode);
    for (var r = 0; r < rs.length; ++r) { var c = rs[r].indexOf(b.id); if (c >= 0) focus = { r: r, c: c }; }
    if (activate(b.id)) after();
  });
  root.addEventListener('storage', function (e) {
    if (e.key !== M.KEY) return;
    var mode = st.mode;
    st = M.restore(e.newValue, now());
    st.mode = mode;   // each tab keeps its own view
    edit = null; lapsKey = '';
    tick();
  });
  doc.addEventListener('visibilitychange', function () { if (!doc.hidden) tick(); });

  setMode(st.mode, true);
  tick();
})(typeof window !== 'undefined' ? window : this);
