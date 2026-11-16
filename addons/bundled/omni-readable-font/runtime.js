// Omni add-on "Readable font": page glue. MIT, Omnibloom contributors.
// Sets the chosen face and spacing on the page's text (not on icons, code or form controls). All the work is CSS:
// addon.css keyed on data-omni-font / data-omni-spacing on the root element.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const R=document.documentElement;
const FACES=['sans','serif','easy'],SPACE=['normal','wide','wider'];
function apply(){const f=api.settings.get('face'),s=api.settings.get('spacing');R.setAttribute('data-omni-font',FACES.includes(f)?f:'sans');
  R.setAttribute('data-omni-spacing',SPACE.includes(s)?s:'normal')}
function clear(){R.removeAttribute('data-omni-font');R.removeAttribute('data-omni-spacing')}
api.onEnable(apply);api.onDisable(clear);api.onSettings(()=>{if(R.hasAttribute('data-omni-font'))apply()});if(api.active)apply()})();
