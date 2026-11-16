/* OMNI_PAD_TEST_V1: Controller test page (DOM side). Pure logic: model.js. The shell feeds window.omniPadTest(msg)
   (OmniPadTestShell.h, <= 30 Hz, only while this page is shown and nothing of Omni's is open over it); without it the
   web Gamepad API is read. While the page is shown Omni's own shortcuts are off except Options (Omni's menu) and
   holding Circle for 1 s (leaves the page). createApp() takes its environment so tools/test_pad_test_page.cjs can drive
   it with a fake document and fake input. */
(function (root) {
  'use strict';

  function createApp(env) {
    var M = env.model, doc = env.document;
    var $ = function (id) { return doc.getElementById(id); };
    var glyphs = env.glyphs === 'xbox' ? 'xbox' : 'playstation';
    var pushState = null, lastPushAt = -1e9, state = M.empty('none');
    var drift = { l: new M.DriftMeter(), r: new M.DriftMeter() };
    var trail = { l: new M.Trail(), r: new M.Trail() };
    var chips = {}, shown = {};

    function set(id, key, value) {   // DOM writes only when the value changed (the page redraws every frame)
      var k = id + '.' + key;
      if (shown[k] === value) return;
      shown[k] = value;
      var el = $(id);
      if (!el) return;
      if (key === 'text') el.textContent = value;
      else if (key === 'class') el.className = value;
      else if (key === 'width') el.style.width = value;
    }

    function build() {
      var box = $('buttons');
      M.BUTTONS.forEach(function (b) {
        var el = doc.createElement('div');
        el.className = 'btn';
        el.textContent = M.label(b[0], glyphs);
        el.setAttribute('data-id', b[0]);
        box.appendChild(el);
        chips[b[0]] = el;
      });
      set('name-l2', 'text', glyphs === 'xbox' ? 'LT' : 'L2');
      set('name-r2', 'text', glyphs === 'xbox' ? 'RT' : 'R2');
      set('leave-hint', 'text', M.leaveHint(glyphs));
    }

    function drawStick(canvas, x, y, dzRadius, points, pressed) {
      var g = canvas && canvas.getContext && canvas.getContext('2d');
      if (!g) return;
      var w = canvas.width, c = w / 2, R = c - 14;
      g.clearRect(0, 0, w, w);
      g.lineWidth = 2;
      g.strokeStyle = '#365063';
      g.beginPath(); g.arc(c, c, R, 0, Math.PI * 2); g.stroke();
      g.beginPath(); g.moveTo(c - R, c); g.lineTo(c + R, c); g.moveTo(c, c - R); g.lineTo(c, c + R); g.stroke();
      g.fillStyle = 'rgba(108,203,255,0.18)'; g.strokeStyle = '#6ccbff';
      g.beginPath(); g.arc(c, c, R * dzRadius, 0, Math.PI * 2); g.fill(); g.stroke();
      for (var i = 0; i < points.length; ++i) {
        g.fillStyle = 'rgba(255,210,138,' + ((i + 1) / points.length * 0.7).toFixed(3) + ')';
        g.beginPath(); g.arc(c + points[i].x * R, c + points[i].y * R, 4, 0, Math.PI * 2); g.fill();
      }
      g.fillStyle = pressed ? '#ffffff' : '#ffd28a';
      g.beginPath(); g.arc(c + x * R, c + y * R, pressed ? 14 : 11, 0, Math.PI * 2); g.fill();
    }

    function driftLine(m, t) {
      if (m.ready) return { text: 'Drift at rest: ' + M.pct(m.max) + ' (x ' + M.pct(m.maxX) + ', y ' + M.pct(m.maxY) + ')', ready: true };
      if (m.since === null) return { text: 'Moving: let go to measure drift', ready: false };
      return { text: 'Measuring drift… ' + Math.ceil((1 - m.progress(t)) * M.DRIFT_WINDOW_MS / 1000) + ' s', ready: false };
    }

    function render(t) {
      var s = state, dz = s.dz, dzName = M.DZ_NAMES[dz.index];
      var src = s.source === 'shell' ? (s.pad ? 'Live from Omni' : 'No controller connected')
        : s.source === 'gamepad' ? 'Gamepad API' + (s.name ? ': ' + s.name : '') : 'Waiting for a controller… press any button';
      set('source', 'text', src);
      set('source', 'class', 'source' + (s.pad ? ' live' : ''));
      M.BUTTONS.forEach(function (b) { var on = !!s.buttons[b[0]]; if (shown['chip.' + b[0]] !== on) { shown['chip.' + b[0]] = on; chips[b[0]].className = on ? 'btn on' : 'btn'; } });
      set('raw-l', 'text', 'x ' + s.raw.lx + ' · y ' + s.raw.ly);
      set('raw-r', 'text', 'x ' + s.raw.rx + ' · y ' + s.raw.ry);
      drawStick($('stick-l'), s.lx, s.ly, dz.left[dz.index], trail.l.points, s.buttons.l3);
      drawStick($('stick-r'), s.rx, s.ry, dz.right[dz.index], trail.r.points, s.buttons.r3);
      set('bar-l2', 'width', (s.l2 * 100).toFixed(1) + '%');
      set('bar-r2', 'width', (s.r2 * 100).toFixed(1) + '%');
      set('val-l2', 'text', Math.round(s.l2 * 100) + '% · ' + s.raw.l2);
      set('val-r2', 'text', Math.round(s.r2 * 100) + '% · ' + s.raw.r2);
      set('touchpad', 'class', 'touchpad' + (s.buttons.touchpad ? ' on' : ''));
      set('tp-state', 'text', s.buttons.touchpad ? 'Pressed' : s.touch.length ? s.touch.length + ' finger' + (s.touch.length > 1 ? 's' : '') : 'Not pressed');
      set('tp-note', 'text', s.source === 'gamepad' ? 'The Gamepad API has no touchpad: open this page from Omni\'s Options menu.' : '');
      var key = s.touch.map(function (f) { return f.x.toFixed(3) + ',' + f.y.toFixed(3); }).join(';');
      if (shown.fingers !== key) {
        shown.fingers = key;
        var pad = $('touchpad');
        Array.prototype.slice.call(pad.querySelectorAll('.finger')).forEach(function (el) { pad.removeChild(el); });
        s.touch.forEach(function (f) {
          var d = doc.createElement('span'); d.className = 'finger';
          d.style.left = (f.x * 100).toFixed(1) + '%'; d.style.top = (f.y * 100).toFixed(1) + '%';
          pad.appendChild(d);
        });
      }
      set('dz-name', 'text', dzName);
      set('dz-now', 'text', dzName + ' (left ' + M.pct(dz.left[dz.index]) + ', right ' + M.pct(dz.right[dz.index]) + ')');
      set('battery', 'text', s.battery || (s.source === 'shell' ? 'Not reported by the console' : 'Not available here'));
      var dl = driftLine(drift.l, t), dr = driftLine(drift.r, t);
      var sug = dl.ready && dr.ready ? M.suggest(drift.l.max, drift.r.max, dz) : null;
      set('drift-l', 'text', dl.text);
      set('drift-r', 'text', dr.text);
      set('drift-l', 'class', 'drift' + (dl.ready ? (drift.l.max + 0.03 <= dz.left[dz.index] ? ' ok' : ' warn') : ''));
      set('drift-r', 'class', 'drift' + (dr.ready ? (drift.r.max + 0.03 <= dz.right[dz.index] ? ' ok' : ' warn') : ''));
      set('suggest', 'text', !s.pad ? 'Connect a controller to measure drift.'
        : sug ? sug.text : 'Put the controller down and leave both sticks alone for 3 seconds.');
      set('suggest', 'class', 'suggest' + (sug ? ' ' + sug.level : ''));
      set('leave-bar', 'class', 'leave' + (s.holdMs > 0 ? ' on' : ''));
      set('leave-fill', 'width', Math.min(100, s.holdMs / 10).toFixed(0) + '%');
    }

    function frame(t) {
      var pads = null;
      if (!(pushState && t - lastPushAt <= M.PUSH_STALE_MS) && env.getGamepads) { try { pads = env.getGamepads(); } catch (e) { pads = null; } }
      var next = M.pick(t, lastPushAt, pushState, pads);
      if (next.source !== state.source || next.pad !== state.pad) { drift.l.reset(); drift.r.reset(); }
      state = next;
      if (state.pad) {
        drift.l.feed(t, state.lx, state.ly); drift.r.feed(t, state.rx, state.ry);
        trail.l.add(state.lx, state.ly); trail.r.add(state.rx, state.ry);
      }
      render(t);
    }

    // The shell's push (numbers only). true tells the shell the page took it.
    function push(msg) {
      var s = M.fromPush(msg);
      if (!s) return false;
      pushState = s; lastPushAt = env.now();
      return true;
    }

    build();
    return { push: push, frame: frame, state: function () { return state; }, drift: drift, trail: trail };
  }

  if (typeof module === 'object' && module.exports) { module.exports = { createApp: createApp }; return; }

  var glyphs = 'playstation';
  try { glyphs = (root.omnibloomHost && root.omnibloomHost.getGlyphs && root.omnibloomHost.getGlyphs()) || root.localStorage.getItem('ob.glyphs') || 'playstation'; } catch (e) { /* storage off */ }
  var app = createApp({ model: root.OmniPadModel, document: root.document, glyphs: glyphs,
    now: function () { return root.performance.now(); },
    getGamepads: root.navigator && root.navigator.getGamepads ? function () { return root.navigator.getGamepads(); } : null });
  Object.defineProperty(root, 'omniPadTest', { value: function (msg) { return app.push(msg); }, writable: false, configurable: false });
  // Built-in pages get the D-pad / Cross / Circle first through omniMediaController; nothing here takes them (the
  // shell's take-over already keeps them from Omni) so every press is only shown.
  function loop(t) { app.frame(t); root.requestAnimationFrame(loop); }
  root.requestAnimationFrame(loop);
})(this);
