// Omni add-on "Same-tab links": page glue. MIT, Omnibloom contributors.
// Links that would open a new tab open in this one (Back returns), so tabs don't pile up on a TV. Hold Shift / Ctrl /
// Alt while choosing a link to still get a new tab.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniSameTabCore;let enabled=false;
function onClick(e){if(!enabled||e.defaultPrevented||e.button!==0)return;const a=e.target&&e.target.closest?e.target.closest('a[href]'):null;if(!a)return;
  const mode=api.settings.get('mode')||'all',mods=e.shiftKey||e.ctrlKey||e.altKey||e.metaKey;
  const named=a.target&&!/^_/.test(a.target)&&!!document.querySelector('iframe[name="'+CSS.escape(a.target)+'"],frame[name="'+CSS.escape(a.target)+'"]');
  if(!core.retarget({target:a.target,href:a.getAttribute('href'),download:a.hasAttribute('download'),namedFrame:named},location.href,mode,mods))return;
  e.preventDefault();e.stopPropagation();location.assign(new URL(a.getAttribute('href'),location.href).href)}
function start(){if(enabled)return;enabled=true;document.addEventListener('click',onClick,true)}
function stop(){enabled=false;document.removeEventListener('click',onClick,true)}
api.onEnable(start);api.onDisable(stop);if(api.active)start()})();
