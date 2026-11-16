/* OMNI_HELP_V1: Help & troubleshooting (backlog P04), pure logic and the topic texts (no DOM). Tested by
   tools/test_help_page.cjs in node. Works offline: the texts are bundled here, written from the project's own
   KNOWN-ISSUES.md, FEATURES.md and README.md. Each topic can carry an "Open it" link to an Omni page (a path listed
   in routes.json) and a QR code for the matching section of the public docs, drawn on the console from the text
   below by the bundled QR encoder (../share/vendor/qrcodegen.js, MIT). Nothing is fetched. */
(function (root) {
  'use strict';

  var REPO = 'https://github.com/egomortal/omnibloom';
  var DOCS = REPO + '/blob/main/';

  // id, title, words (extra search words), steps, open ({ path: routes.json path, label }) or null, doc (file#anchor)
  var TOPICS = [
    { id: 'youtube', title: 'YouTube won\'t play, or stops after about a minute',
      words: 'video youtube play playing start stuck stops stopped minute buffering black spinner 720p hdr quality',
      steps: [
        'Wait a few seconds. Omni\'s YouTube guard notices a refused start and reloads the page at the same spot by itself, up to 5 times per video.',
        'Still not playing? Reload the page, or open the video again.',
        'If it keeps happening, close Omni and open it again.',
        'Video stopping after about a minute was fixed in v0.5.0. On an older Omni, update it with Omnibloom Setup.',
        'Only 720p, no HDR or no ad blocking on a fresh install: on your PC, open Omnibloom Setup > Installed apps, press Repair next to Omni, then restart Omni.'
      ],
      open: null, doc: 'KNOWN-ISSUES.md#youtube-sometimes-doesnt-start-playing' },

    { id: 'shield', title: 'Red shield: a page is blocked or not secure',
      words: 'shield red blocked block ublock ad blocker adblock filtering failed error 1 insecure secure certificate https http allow site',
      steps: [
        'The shield in the top bar is the ad blocker: green is on, grey is off, red means it hit an error.',
        '"uBlock blocked this page": choose Allow this site only if you trust it, otherwise Back.',
        '"Filtering failed ... (error 1)" on every page: the ad blocker\'s rule files are missing. Run Repair in Omnibloom Setup on your PC, then restart Omni.',
        '"This connection isn\'t secure": Omni could not check the site\'s certificate. Go back, and never type a password there.',
        'With HTTPS-only mode on, Omni asks before it opens an http site: Cross continues, Circle goes back.'
      ],
      open: { path: 'site-settings/index.html', label: 'Site settings' },
      doc: 'KNOWN-ISSUES.md#every-page-fails-filtering-failed-requests-blocked-restart-omni-to-retry-error-1' },

    { id: 'memory', title: 'Out of memory: "This page stopped working"',
      words: 'crash crashed crashes memory out of oom tab stopped working heavy lite mode data saver unload reader',
      steps: [
        'The page\'s process ended, usually because a heavy page ran out of memory. Your other tabs are fine.',
        'The crash panel offers: Reload, Open in Reader view (good for articles), Reload with Data saver, and Unload other tabs and reload.',
        'Crashed twice on the same site? Turn on Lite mode in Browser settings: only 3 tabs stay loaded and the caches get smaller.',
        'Data saver (Browser settings) plays video at up to 480p and blocks autoplay and web fonts, which saves memory too.',
        'Close tabs you no longer need in the Tabs panel. If one site keeps crashing, try Settings > JavaScript JIT off.'
      ],
      open: { path: 'tabs/index.html', label: 'Tabs' },
      doc: 'KNOWN-ISSUES.md#a-site-misbehaves-with-the-javascript-jit-on' },

    { id: 'slow', title: 'A site is slow or stuck loading',
      words: 'slow stuck loading load frozen freeze hang cache reload without cache old broken layout site data cookies',
      steps: [
        'Hold Cross on the page (or open Options > Browse) and pick Reload without cache. Every file is fetched fresh.',
        'Still broken? Options > Site settings > Clear data for this site. You may be signed out of that site.',
        'Some JavaScript-heavy sites are slower than on a PC or phone. Data saver or Lite mode can help.',
        'If a site acts oddly, try Settings > JavaScript JIT off.'
      ],
      open: { path: 'site-data/index.html', label: 'Cookies and site data' },
      doc: 'KNOWN-ISSUES.md#limits-by-design-or-not-possible-yet' },

    { id: 'sound', title: 'No sound',
      words: 'sound audio mute muted unmute volume silent quiet speaker autoplay headset',
      steps: [
        'A crossed speaker on the tab means it is muted. Press Triangle on its row in the Tabs panel, or pick Mute this tab in the hold-Cross menu, to unmute it.',
        'In fullscreen video, L3 (press the left stick) mutes and unmutes.',
        'Autoplay set to Block sound keeps videos that start by themselves silent. Change it in Browser settings, or in Site settings > Autoplay on this site.',
        'Check the TV or headset volume and the PS5\'s audio output.'
      ],
      open: { path: 'tabs/index.html', label: 'Tabs' },
      doc: 'FEATURES.md#video-and-sound' },

    { id: 'keyboard', title: 'Keyboard tips',
      words: 'keyboard typing type text cursor delete space shift symbols paste copy cut undo word suggestions login',
      steps: [
        'L1 / R1 (LB / RB) move the cursor; L2 / R2 (LT / RT) move it a whole word.',
        'Square (X) deletes, Triangle (Y) types a space, L3 is Shift and R3 opens the symbols.',
        'The touchpad opens the edit row: copy, cut, paste, undo, select all and Fill saved login.',
        'Options (Menu) is Go.',
        'Word suggestions: press D-pad up from the top row of keys, then left / right, and Cross to use one.'
      ],
      open: { path: 'keyboard/index.html', label: 'Controller keyboard' },
      doc: 'README.md#typing-on-screen-keyboard' },

    { id: 'controller', title: 'Controller basics',
      words: 'controller buttons button dualsense xbox shortcuts pointer stick scroll back tab tabs drift menu',
      steps: [
        'Left stick moves the pointer, right stick scrolls. Cross (A) clicks; hold it for the page menu.',
        'Circle (B) goes back. Square (X) opens a new tab, Triangle (Y) the address bar.',
        'L1 / R1 (LB / RB) switch tabs. Options (Menu) opens the quick menu.',
        'Create (View) opens Browser settings. If View does nothing on an Xbox controller, use LT + B.',
        'Pointer drifting by itself? Check the sticks on the controller test page.'
      ],
      open: { path: 'controller/index.html', label: 'Controller test' },
      doc: 'README.md#controller-shortcuts' },

    { id: 'downloads', title: 'Downloads don\'t start',
      words: 'download downloads downloading media unavailable worker bloom core file save saving start retry pause',
      steps: [
        'Media downloads has to be on, and the downloads worker installed by Omnibloom Setup.',
        '"Media downloads unavailable" means Bloom Core isn\'t running. Run Repair in Omnibloom Setup, reboot the PS5 and run your jailbreak.',
        'If Bloom Core is running, give the worker a few seconds to answer and try again.',
        'Private tabs never send downloads.',
        'A paused or failed download can be resumed or retried in the Downloads app.'
      ],
      open: { path: 'downloads/index.html', label: 'Downloads' },
      doc: 'KNOWN-ISSUES.md#media-downloads-unavailable-lt--double-bumper' },

    { id: 'translate', title: 'Translate: what is sent',
      words: 'translate translation translating language google privacy private touchpad sent send',
      steps: [
        'Press the touchpad to translate the page.',
        'Translation uses Google Translate\'s website: the page\'s address, query string included, goes to Google, which loads and translates the page.',
        'Nothing is sent until you press.',
        'Think twice on pages whose address holds personal details, such as account or order pages.'
      ],
      open: { path: 'translate/index.html', label: 'Translate page' },
      doc: 'FEATURES.md#-browsing' },

    { id: 'reset', title: 'Reset Omni\'s settings',
      words: 'reset defaults default settings restore backup undo setup factory repair broken',
      steps: [
        'On your PC, open Omnibloom Setup and press Reset Omni settings.',
        'Setup first saves a full backup on the PC. If that fails, nothing on the PS5 changes.',
        'Bookmarks, history, notes, reading list, saved passwords, cookies and sign-ins stay as they are.',
        'The old settings files are set aside, never deleted, and Undo puts them back. Omni opens with its defaults next time.',
        'Missing or damaged files rather than settings? Use Repair in Installed apps instead.'
      ],
      open: { path: 'settings/index.html', label: 'Settings' },
      doc: 'FEATURES.md#downloads-and-setup' }
  ];

  // --- search -------------------------------------------------------------------------------------------------------
  // Lower case, apostrophes dropped ("won't" finds "wont"), anything else that isn't a letter or digit is a space.
  function norm(s) {
    return String(s == null ? '' : s).toLowerCase().replace(/['’]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  }
  function haystack(t) { return ' ' + norm([t.title, t.words, t.steps.join(' '), t.open ? t.open.label : ''].join(' ')) + ' '; }
  // Every word of the query has to start a word in the topic ("mem" finds "memory"; "ory" does not).
  function matches(t, query) {
    var q = norm(query);
    if (!q) return true;
    var h = haystack(t), words = q.split(' ');
    for (var i = 0; i < words.length; ++i) if (h.indexOf(' ' + words[i]) < 0) return false;
    return true;
  }
  function filter(topics, query) {
    var out = [];
    for (var i = 0; i < (topics || []).length; ++i) if (matches(topics[i], query)) out.push(topics[i].id);
    return out;
  }

  // --- links ----------------------------------------------------------------------------------------------------------
  function href(t) { return t && t.open ? '../' + t.open.path : null; }
  function omniUrl(t) { return t && t.open ? 'omni://pages/' + t.open.path : null; }
  function docUrl(t) { return DOCS + t.doc; }
  function docLabel(t) { return t.doc.split('#')[0]; }

  // --- QR: a thin wrapper over the bundled encoder (Project Nayuki, MIT) ---------------------------------------------
  function qr(Q, text) {
    if (!Q || !Q.QrCode) return null;
    var code = Q.QrCode.encodeText(String(text), Q.QrCode.Ecc.LOW);   // boosts to a stronger level when it still fits
    var rows = [];
    for (var y = 0; y < code.size; ++y) { var r = []; for (var x = 0; x < code.size; ++x) r.push(code.getModule(x, y)); rows.push(r); }
    return { size: code.size, version: code.version, rows: rows };
  }
  // One SVG path for the dark modules, with a 4-module quiet zone.
  function qrPath(m) {
    var parts = [];
    for (var y = 0; y < m.size; ++y) for (var x = 0; x < m.size; ++x) if (m.rows[y][x]) parts.push('M' + (x + 4) + ',' + (y + 4) + 'h1v1h-1z');
    return parts.join('');
  }

  // --- controller: one column of focusable ids ------------------------------------------------------------------------
  // search, then each shown topic's header; the open topic's "Open it" link follows its header.
  function rows(topics, shown, open) {
    var byId = {}, out = ['search'];
    (topics || []).forEach(function (t) { byId[t.id] = t; });
    (shown || []).forEach(function (id) {
      if (!byId[id]) return;
      out.push('topic-' + id);
      if (open === id && byId[id].open) out.push('open-' + id);
    });
    return out;
  }
  function initial() { return { query: '', open: null, focus: 'search' }; }
  function topicOf(id) { var m = /^(?:topic|open)-(.+)$/.exec(id || ''); return m ? m[1] : null; }

  // Keep the state consistent after the query changed: a hidden open topic closes, a hidden focus moves.
  function refresh(st, topics) {
    var shown = filter(topics, st.query);
    if (st.open && shown.indexOf(st.open) < 0) st.open = null;
    var list = rows(topics, shown, st.open);
    if (list.indexOf(st.focus) < 0) {
      var t = topicOf(st.focus);
      st.focus = t && list.indexOf('topic-' + t) >= 0 ? 'topic-' + t : 'search';
    }
    return { shown: shown, list: list };
  }

  // One controller action. Returns { handled, go (href to open), edit (focus the search box for typing) }.
  function step(st, a, topics) {
    var v = refresh(st, topics), list = v.list, i = list.indexOf(st.focus), id = st.focus, t = topicOf(id), res = { handled: true, go: null, edit: false };
    var headers = list.filter(function (x) { return /^topic-/.test(x); });
    if (a === 'up' || a === 'down') st.focus = list[Math.max(0, Math.min(list.length - 1, i + (a === 'up' ? -1 : 1)))];
    else if (a === 'right') { if (/^topic-/.test(id)) st.open = t; }
    else if (a === 'left') { if (t && st.open === t) { st.open = null; st.focus = 'topic-' + t; } }
    else if (a === 'cross') {
      if (id === 'search') res.edit = true;
      else if (/^topic-/.test(id)) st.open = st.open === t ? null : t;
      else if (/^open-/.test(id)) res.go = href(byIdIn(topics, t));
    } else if (a === 'circle') {
      if (!st.open) return { handled: false, go: null, edit: false };   // Omni's own Back
      st.focus = 'topic-' + st.open; st.open = null;
    } else if (a === 'square') { if (!st.query) return { handled: false, go: null, edit: false }; st.query = ''; }
    else if (a === 'triangle') st.focus = 'search';
    else if (a === 'l1' || a === 'r1') {
      if (!headers.length) return res;
      var cur = headers.indexOf('topic-' + t);
      if (cur < 0) cur = a === 'r1' ? -1 : 0;
      st.focus = headers[Math.max(0, Math.min(headers.length - 1, cur + (a === 'l1' ? -1 : 1)))];
    } else return { handled: false, go: null, edit: false };
    refresh(st, topics);
    return res;
  }
  function byIdIn(topics, id) { for (var i = 0; i < topics.length; ++i) if (topics[i].id === id) return topics[i]; return null; }

  var GLYPHS = {
    playstation: { cross: 'Cross', circle: 'Circle', square: 'Square', triangle: 'Triangle', l1: 'L1', r1: 'R1' },
    xbox: { cross: 'A', circle: 'B', square: 'X', triangle: 'Y', l1: 'LB', r1: 'RB' }
  };
  function hint(kind) {
    var g = GLYPHS[kind === 'xbox' ? 'xbox' : 'playstation'];
    return 'D-pad: move   ' + g.cross + ': open / close   ' + g.triangle + ': search   ' + g.square + ': clear search   '
      + g.l1 + ' / ' + g.r1 + ': topic   ' + g.circle + ': back';
  }

  var api = { REPO: REPO, DOCS: DOCS, TOPICS: TOPICS, norm: norm, matches: matches, filter: filter,
    href: href, omniUrl: omniUrl, docUrl: docUrl, docLabel: docLabel, qr: qr, qrPath: qrPath,
    rows: rows, initial: initial, topicOf: topicOf, refresh: refresh, step: step, hint: hint };
  if (typeof module === 'object' && module.exports) { module.exports = api; return; }
  root.OmniHelpModel = api;
})(typeof window !== 'undefined' ? window : this);
