(function(){
var original=window.omniPadController,ps=false,footer=document.querySelector('footer');
var glyph=document.createElement('button');glyph.id='glyph-toggle';glyph.type='button';glyph.textContent='Xbox glyphs';
footer.before(glyph);
function render(){glyph.textContent=ps?'PlayStation glyphs':'Xbox glyphs';document.documentElement.dataset.glyphs=ps?'playstation':'xbox';footer.textContent='↑ ↓ Move · ← → Change value · '+(ps?'× Select · ○ Back':'A Select · B Back')}
glyph.onclick=function(){ps=!ps;render()};render();
window.omniPadController=window.omniMediaController=function(action){
action=String(action).toLowerCase();action=({accept:'cross',cancel:'circle',lb:'l1',rb:'r1'})[action]||action;
var active=document.activeElement;if(active&&active.tagName==='SELECT'&&['left','right'].includes(action)){active.selectedIndex=Math.max(0,Math.min(active.options.length-1,active.selectedIndex+(action==='right'?1:-1)));active.dispatchEvent(new Event('change',{bubbles:true}));return true}
return original(action);
};
})();
