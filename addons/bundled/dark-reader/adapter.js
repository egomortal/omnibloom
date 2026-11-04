/* Omnibloom: OMNI_ADDONS_V1 adapter for Dark Reader (GPL-3.0-or-later).
   Runs in the add-on's isolated world after vendor/darkreader.js and inject.js (Astra's createOmniDarkReader).
   Maps window.omniAddon settings onto inject.js; "cache" mode stores this origin's generated CSS (<= 60 KB,
   the add-on storage limit is 64 KB per value) and reuses it on the next visit. */
(function () {
  'use strict';
  if (typeof window.omniAddon !== 'object' || typeof window.createOmniDarkReader !== 'function') return;
  var A = window.omniAddon, dr = window.createOmniDarkReader(window, {}), key = 'css:' + location.origin, saveTimer = 0;
  function state() {
    var s = A.settings.all();
    return { enabled: true, mode: s.mode, brightness: s.brightness, contrast: s.contrast, sepia: s.sepia };
  }
  function run() {
    var st = state(), css = st.mode === 'cache' ? A.storage.get(key) : null;
    if (st.mode === 'cache' && typeof css !== 'string') {
      // first visit in cache mode: run the dynamic engine once, then keep its CSS for next time
      dr.apply({ enabled: true, mode: 'dynamic', brightness: st.brightness, contrast: st.contrast, sepia: st.sepia }, null);
      clearTimeout(saveTimer);
      saveTimer = setTimeout(function () {
        Promise.resolve(dr.exportCSS()).then(function (out) {
          if (typeof out === 'string' && out.length <= 60000) return A.storage.set(key, out);
        }).catch(function () {});
      }, 3000);
      return;
    }
    dr.apply(st, css);
  }
  A.onSettings(function () { if (A.active) run(); });
  A.onDisable(function () { clearTimeout(saveTimer); dr.disable(); });
  A.onEnable(run);
  run();
})();
