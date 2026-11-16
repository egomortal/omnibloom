/* OMNI_COUCH_TIMER_V1: Couch timer (backlog P05), pure logic (no DOM). Tested by tools/test_timer_page.cjs in node.
   Every running timer is stored as a wall-clock target (Date.now() based: end / start / alarm time), never as a
   counter, so a reload, a throttled background tab or a late setTimeout never makes it drift: the display is always
   computed from "now", and the next tick is scheduled for the next moment the display can change. */
(function (root) {
  'use strict';

  var SEC = 1000, MIN = 60 * SEC, HOUR = 60 * MIN;
  var KEY = 'omni.timer.v1';
  var MODES = ['countdown', 'stopwatch', 'alarm'];
  var PRESETS_MIN = [1, 3, 5, 10, 15, 30];
  var CD_LIMITS = [23, 59, 59];          // custom countdown h:mm:ss
  var AL_LIMITS = [23, 59];              // alarm hh:mm (24 h)
  var MAX_LAPS = 99;
  var RING_LATE_MS = 10 * MIN;           // a timer that ended longer ago than this (page closed) is "missed", not rung
  var RING_MAX_MS = 10 * MIN;            // ringing stops by itself after this long
  var SW_STEP_MS = 100;                  // the stopwatch shows tenths

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function int(v, lo, hi, d) { return typeof v === 'number' && isFinite(v) ? clamp(Math.floor(v), lo, hi) : d; }
  function time(v) { return typeof v === 'number' && isFinite(v) && v > 0 ? v : null; }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function mod(a, n) { return ((a % n) + n) % n; }

  // --- time math ---------------------------------------------------------------------------------------------------
  function hmsToMs(h, m, s) { return ((int(h, 0, 23, 0) * 60 + int(m, 0, 59, 0)) * 60 + int(s, 0, 59, 0)) * SEC; }
  function splitSec(totalSec) {
    totalSec = Math.max(0, Math.floor(totalSec));
    return { h: Math.floor(totalSec / 3600), m: Math.floor(totalSec / 60) % 60, s: totalSec % 60 };
  }
  // Countdown digits round UP: 4:59.2 left shows 5:00, and 0:00 appears only at the very end.
  function countdownParts(ms) { return splitSec(Math.ceil(Math.max(0, ms) / SEC)); }
  function formatCountdown(ms) {
    var p = countdownParts(ms);
    return p.h ? p.h + ':' + pad2(p.m) + ':' + pad2(p.s) : p.m + ':' + pad2(p.s);
  }
  // Stopwatch digits round DOWN, with tenths.
  function formatStopwatch(ms) {
    ms = Math.max(0, Math.floor(ms));
    var p = splitSec(ms / SEC);
    return { main: p.h ? p.h + ':' + pad2(p.m) + ':' + pad2(p.s) : p.m + ':' + pad2(p.s), frac: '.' + Math.floor(ms % SEC / 100) };
  }
  function formatClock(ms) { var d = new Date(ms); return pad2(d.getHours()) + ':' + pad2(d.getMinutes()); }
  function formatIn(ms) {
    var mins = Math.ceil(Math.max(0, ms) / MIN), h = Math.floor(mins / 60), m = mins % 60;
    if (ms < MIN) return 'under a minute';
    return h ? h + ' h' + (m ? ' ' + m + ' min' : '') : m + ' min';
  }
  function presetLabel(min) { return min + ' min'; }

  // --- countdown: { dur, end, left } -- end is the wall-clock end while running, left the time kept while paused ----
  function newCountdown(dur) { dur = int(dur, SEC, hmsToMs(23, 59, 59), 5 * MIN); return { dur: dur, end: null, left: dur }; }
  function cdRunning(cd) { return cd.end !== null; }
  function cdRemaining(cd, now) { return cd.end !== null ? Math.max(0, cd.end - now) : cd.left; }
  function cdStart(cd, now) { if (cd.end === null) { if (cd.left <= 0) cd.left = cd.dur; cd.end = now + cd.left; } return cd; }
  function cdPause(cd, now) { if (cd.end !== null) { cd.left = Math.max(0, cd.end - now); cd.end = null; } return cd; }
  function cdToggle(cd, now) { return cd.end !== null ? cdPause(cd, now) : cdStart(cd, now); }
  function cdReset(cd) { cd.end = null; cd.left = cd.dur; return cd; }
  function cdSet(cd, dur) { var n = newCountdown(dur); cd.dur = n.dur; return cdReset(cd); }

  // --- stopwatch: { start, acc, laps } -- start is the wall-clock start of the running stretch, acc the earlier total
  function newStopwatch() { return { start: null, acc: 0, laps: [] }; }
  function swElapsed(sw, now) { return sw.acc + (sw.start !== null ? Math.max(0, now - sw.start) : 0); }
  function swToggle(sw, now) {
    if (sw.start !== null) { sw.acc = swElapsed(sw, now); sw.start = null; } else sw.start = now;
    return sw;
  }
  function swLap(sw, now) {
    if (sw.start === null || sw.laps.length >= MAX_LAPS) return false;
    sw.laps.push(swElapsed(sw, now));
    return true;
  }
  function swReset(sw) { sw.start = null; sw.acc = 0; sw.laps = []; return sw; }
  // Newest first: { n, split, total } (split = this lap's own time).
  function lapRows(laps) {
    var rows = [];
    for (var i = laps.length - 1; i >= 0; --i) rows.push({ n: i + 1, split: laps[i] - (i ? laps[i - 1] : 0), total: laps[i] });
    return rows;
  }

  // --- alarm: { h, m, at } -- at is the wall-clock moment it rings (null: off) ---------------------------------------
  // The next h:m local time strictly after now: today if still ahead, otherwise tomorrow (built from the calendar
  // date, not "+24 h", so a DST change in between still lands on h:m).
  function nextAlarmAt(h, m, now) {
    var d = new Date(now);
    var t = new Date(d.getFullYear(), d.getMonth(), d.getDate(), int(h, 0, 23, 0), int(m, 0, 59, 0), 0, 0);
    if (t.getTime() <= now) t = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, int(h, 0, 23, 0), int(m, 0, 59, 0), 0, 0);
    return t.getTime();
  }
  function alArm(al, now) { al.at = nextAlarmAt(al.h, al.m, now); return al; }
  function alCancel(al) { al.at = null; return al; }

  // --- D-pad editing of h:mm:ss / hh:mm fields ---------------------------------------------------------------------
  function editStep(values, field, dir, limits) {
    var out = values.slice();
    if (dir === 'up' || dir === 'down') out[field] = mod(out[field] + (dir === 'up' ? 1 : -1), limits[field] + 1);
    return out;
  }
  function editField(field, dir, count) {
    if (dir === 'left') return Math.max(0, field - 1);
    if (dir === 'right') return Math.min(count - 1, field + 1);
    return field;
  }

  // --- whole state, firing, persistence ----------------------------------------------------------------------------
  function initial() {
    return { mode: 'countdown', cd: newCountdown(5 * MIN), sw: newStopwatch(), al: { h: 7, m: 0, at: null }, ring: null, missed: null };
  }
  // Fires whatever is due. Returns the kinds that started ringing ('countdown' / 'alarm'). A ring is { kind, since }.
  function check(st, now) {
    var fired = [];
    function due(kind, at) {
      if (now - at > RING_LATE_MS) { st.missed = { kind: kind, at: at }; return; }
      if (!st.ring || at > st.ring.since) st.ring = { kind: kind, since: at };
      fired.push(kind);
    }
    if (st.cd.end !== null && now >= st.cd.end) { var e = st.cd.end; st.cd.end = null; st.cd.left = 0; due('countdown', e); }
    if (st.al.at !== null && now >= st.al.at) { var a = st.al.at; st.al.at = null; due('alarm', a); }
    if (st.ring && now - st.ring.since > RING_MAX_MS) { st.missed = { kind: st.ring.kind, at: st.ring.since }; st.ring = null; }
    return fired;
  }
  function dismiss(st) {
    if (!st.ring) return false;
    if (st.ring.kind === 'countdown') cdReset(st.cd);
    st.ring = null;
    return true;
  }

  // Milliseconds until the screen can next change or something is due: the countdown's next whole second (and its
  // end), the stopwatch's next tenth (only while it is shown), the alarm, and the wall clock's next second. Always
  // measured from the targets, so a tick that fires late is followed by a shorter wait (no drift builds up).
  function nextDelay(st, now) {
    var c = [SEC - mod(now, SEC)];
    if (st.cd.end !== null) c.push(mod(st.cd.end - now, SEC) || SEC);
    if (st.al.at !== null) c.push(st.al.at - now);
    if (st.sw.start !== null && st.mode === 'stopwatch') c.push(SW_STEP_MS - mod(swElapsed(st.sw, now), SW_STEP_MS));
    if (st.ring) c.push(SEC - mod(now - st.ring.since, SEC));
    return clamp(Math.min.apply(null, c), 1, SEC) + 1;   // +1: land just after the boundary, not on it
  }

  function serialize(st) {
    return JSON.stringify({ v: 1, mode: st.mode, cd: st.cd, sw: { start: st.sw.start, acc: st.sw.acc, laps: st.sw.laps },
      al: st.al, ring: st.ring, missed: st.missed });
  }
  // Reads a stored string back (bad or missing data gives the defaults) and fires what fell due while it was closed.
  function restore(text, now) {
    var st = initial(), d = null;
    try { d = JSON.parse(text); } catch (e) { d = null; }
    if (!d || typeof d !== 'object' || d.v !== 1) return st;
    if (MODES.indexOf(d.mode) >= 0) st.mode = d.mode;
    if (d.cd && typeof d.cd === 'object') {
      st.cd = newCountdown(d.cd.dur);
      st.cd.end = time(d.cd.end);
      st.cd.left = st.cd.end !== null ? st.cd.dur : int(d.cd.left, 0, st.cd.dur, st.cd.dur);
    }
    if (d.sw && typeof d.sw === 'object') {
      st.sw.start = time(d.sw.start);
      if (st.sw.start !== null && st.sw.start > now) st.sw.start = now;   // clock went backwards: never negative
      st.sw.acc = int(d.sw.acc, 0, Number.MAX_SAFE_INTEGER, 0);
      st.sw.laps = Array.isArray(d.sw.laps) ? d.sw.laps.filter(function (x) { return typeof x === 'number' && isFinite(x) && x >= 0; }).slice(0, MAX_LAPS) : [];
    }
    if (d.al && typeof d.al === 'object') st.al = { h: int(d.al.h, 0, 23, 7), m: int(d.al.m, 0, 59, 0), at: time(d.al.at) };
    if (d.ring && (d.ring.kind === 'countdown' || d.ring.kind === 'alarm') && time(d.ring.since)) st.ring = { kind: d.ring.kind, since: d.ring.since };
    if (d.missed && (d.missed.kind === 'countdown' || d.missed.kind === 'alarm') && time(d.missed.at)) st.missed = { kind: d.missed.kind, at: d.missed.at };
    check(st, now);
    return st;
  }

  // --- controller layout: rows of focusable ids per mode; the D-pad moves between them -----------------------------
  var TABS = ['tab-countdown', 'tab-stopwatch', 'tab-alarm'];
  function rows(mode) {
    if (mode === 'stopwatch') return [TABS, ['sw-go', 'sw-lap', 'sw-reset']];
    if (mode === 'alarm') return [TABS, ['al-display'], ['al-go']];
    return [TABS, ['cd-display'], PRESETS_MIN.map(function (m) { return 'preset-' + m; }), ['cd-go', 'cd-reset']];
  }
  function navigate(rs, pos, dir) {
    var r = clamp(pos.r, 0, rs.length - 1), c = clamp(pos.c, 0, rs[r].length - 1);
    if (dir === 'left') c = Math.max(0, c - 1);
    else if (dir === 'right') c = Math.min(rs[r].length - 1, c + 1);
    else if (dir === 'up' || dir === 'down') {
      var nr = clamp(r + (dir === 'up' ? -1 : 1), 0, rs.length - 1);
      if (nr !== r) {   // keep roughly the same horizontal place
        c = rs[r].length > 1 ? Math.round(c / (rs[r].length - 1) * (rs[nr].length - 1)) : Math.floor((rs[nr].length - 1) / 2);
        r = nr;
      }
    }
    return { r: r, c: c };
  }

  // --- sound: an <audio> element with the bundled WAV, only when this build says it can play one ------------------
  function canPlayWav(audio) {
    try {
      return !!(audio && typeof audio.play === 'function' && typeof audio.canPlayType === 'function'
        && audio.canPlayType('audio/wav; codecs="1"').replace(/no/, ''));
    } catch (e) { return false; }
  }

  var GLYPHS = { playstation: { cross: 'Cross', circle: 'Circle', square: 'Square', triangle: 'Triangle', l1: 'L1', r1: 'R1' },
    xbox: { cross: 'A', circle: 'B', square: 'X', triangle: 'Y', l1: 'LB', r1: 'RB' } };
  function hint(kind, what) {
    var g = GLYPHS[kind === 'xbox' ? 'xbox' : 'playstation'];
    if (what === 'ring') return g.cross + ' or ' + g.circle + ': stop';
    if (what === 'edit') return 'Left / Right: pick   Up / Down: change   ' + g.cross + ': done   ' + g.circle + ': cancel';
    return 'D-pad: move   ' + g.cross + ': choose   ' + g.square + ': start / pause   ' + g.triangle + ': lap   '
      + g.l1 + ' / ' + g.r1 + ': mode   ' + g.circle + ': back';
  }

  var api = { KEY: KEY, MODES: MODES, PRESETS_MIN: PRESETS_MIN, CD_LIMITS: CD_LIMITS, AL_LIMITS: AL_LIMITS, MAX_LAPS: MAX_LAPS,
    RING_LATE_MS: RING_LATE_MS, RING_MAX_MS: RING_MAX_MS, SW_STEP_MS: SW_STEP_MS, TABS: TABS,
    pad2: pad2, hmsToMs: hmsToMs, splitSec: splitSec, countdownParts: countdownParts, formatCountdown: formatCountdown,
    formatStopwatch: formatStopwatch, formatClock: formatClock, formatIn: formatIn, presetLabel: presetLabel,
    newCountdown: newCountdown, cdRunning: cdRunning, cdRemaining: cdRemaining, cdStart: cdStart, cdPause: cdPause,
    cdToggle: cdToggle, cdReset: cdReset, cdSet: cdSet,
    newStopwatch: newStopwatch, swElapsed: swElapsed, swToggle: swToggle, swLap: swLap, swReset: swReset, lapRows: lapRows,
    nextAlarmAt: nextAlarmAt, alArm: alArm, alCancel: alCancel, editStep: editStep, editField: editField,
    initial: initial, check: check, dismiss: dismiss, nextDelay: nextDelay, serialize: serialize, restore: restore,
    rows: rows, navigate: navigate, canPlayWav: canPlayWav, hint: hint };
  if (typeof module === 'object' && module.exports) { module.exports = api; return; }
  root.OmniTimerModel = api;
})(typeof window !== 'undefined' ? window : this);
