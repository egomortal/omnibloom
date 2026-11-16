// Omni add-on "Clear links": page glue. MIT, Omnibloom contributors.
// Every link underlined and a thick, high-contrast focus ring on whatever the D-pad is on. CSS only (addon.css),
// keyed on data-omni-links on the root element.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const R=document.documentElement;
function apply(){R.setAttribute('data-omni-links',api.settings.get('underline')===false?'ring':'all')}
function clear(){R.removeAttribute('data-omni-links')}
api.onEnable(apply);api.onDisable(clear);api.onSettings(()=>{if(R.hasAttribute('data-omni-links'))apply()});if(api.active)apply()})();
