// Omni add-on "Reader view": reading options (text size, line width, font, colours, line spacing). MIT, Omnibloom contributors.
// Pure data and small helpers, no DOM: runtime.js draws the toolbar from OPTIONS, the tests check the rules here.
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.OmniReaderPrefs=value})(globalThis,()=>{'use strict';
// One storage key in the add-on's own storage (/data/omni/addons/storage/omni-reader-view.txt), shared by every page.
const STORAGE_KEY='prefs';
// Order matters: it is the order on screen; the bar's A- / A+ buttons step through the sizes.
const OPTIONS=Object.freeze([
  {key:'size',label:'Text size',values:['small','medium','large','huge','giant'],labels:['Small','Medium','Large','Huge','Giant']},
  {key:'width',label:'Line width',values:['narrow','medium','wide'],labels:['Narrow','Medium','Wide']},
  {key:'font',label:'Font',values:['serif','sans','readable'],labels:['Serif','Sans','Easy read']},
  {key:'theme',label:'Colours',values:['light','sepia','dark','black'],labels:['Light','Sepia','Dark','Black']},
  {key:'spacing',label:'Line spacing',values:['compact','normal','relaxed'],labels:['Compact','Normal','Relaxed']}
].map(o=>Object.freeze(Object.assign(o,{values:Object.freeze(o.values),labels:Object.freeze(o.labels)}))));
const BY_KEY=Object.freeze(Object.fromEntries(OPTIONS.map(o=>[o.key,o])));
const DEFAULTS=Object.freeze({size:'large',width:'medium',font:'serif',theme:'auto',spacing:'normal'});
// Keys the add-on settings page also has (manifest settings). A change there wins over the toolbar's saved choice.
const MANIFEST_KEYS=Object.freeze(['size','theme']);
const valid=(key,v)=>key==='theme'&&v==='auto'||!!BY_KEY[key]&&BY_KEY[key].values.includes(v);
// choices (toolbar) over base (manifest settings) over DEFAULTS. Unknown keys and values are dropped.
function resolve(choices,base){const out={};for(const k of Object.keys(DEFAULTS)){const s=choices&&typeof choices==='object'?choices[k]:undefined,b=base&&typeof base==='object'?base[k]:undefined;
  out[k]=valid(k,s)?s:valid(k,b)?b:DEFAULTS[k]}return out}
// Only valid toolbar choices are kept (small JSON, far under the shell's 64 KB value limit).
function clean(choices){const out={};if(choices&&typeof choices==='object')for(const k of Object.keys(DEFAULTS))if(valid(k,choices[k]))out[k]=choices[k];return out}
// Stored value: {choices, base}. base is what the settings page said when the choices were saved, so a later change
// there (made from any tab, reader open or not) is seen on the next load and wins for that option.
function pack(choices,base){const b={};for(const k of MANIFEST_KEYS)if(base&&typeof base[k]==='string')b[k]=base[k];return{choices:clean(choices),base:b}}
function load(stored,base){const s=stored&&typeof stored==='object'?stored:{},choices=clean(s.choices),was=s.base&&typeof s.base==='object'?s.base:{};
  for(const k of MANIFEST_KEYS)if(k in choices&&typeof was[k]==='string'&&base&&was[k]!==base[k])delete choices[k];return{choices,prefs:resolve(choices,base)}}
// One step along an option (A- / A+ on the size); stays at the ends. Returns the new value.
function step(key,value,dir){const o=BY_KEY[key];if(!o)return value;const i=o.values.indexOf(value);if(i<0)return DEFAULTS[key]==='auto'?o.values[0]:DEFAULTS[key];return o.values[Math.max(0,Math.min(o.values.length-1,i+(dir<0?-1:1)))]}
const atEnd=(key,value,dir)=>{const o=BY_KEY[key];if(!o)return true;const i=o.values.indexOf(value);return dir<0?i<=0:i>=o.values.length-1};
// 'auto' follows Omni's dark pages switch (dark) or not (light); everything else is the choice itself.
const themeFor=(theme,darkPages)=>theme==='auto'?(darkPages?'dark':'light'):theme;
// Class names on the reader panel; addon.css keys every option off these.
function classes(p,darkPages){return['omni-reader','omni-reader-'+themeFor(p.theme,darkPages),'omni-reader-'+p.size,'omni-reader-w-'+p.width,'omni-reader-f-'+p.font,'omni-reader-l-'+p.spacing].join(' ')}
// The reading time in the bar: the whole estimate at the top, then what is left as the article scrolls (progress 0..1).
function timeLabel(minutes,progress){const m=Math.max(1,Math.round(Number(minutes)||1)),p=Math.max(0,Math.min(1,Number(progress)||0));
  if(p<.02)return m+' min read';if(p>=.98)return'Finished';return Math.max(1,Math.ceil(m*(1-p)))+' min left'}
// The line above the title: "~7 min read · 1,234 words" (CJK text is counted in characters: "· 3,200 characters").
const group=n=>String(Math.max(0,Math.round(Number(n)||0))).replace(/\B(?=(\d{3})+(?!\d))/g,',');
function headLabel(r){const x=r||{},m=Math.max(1,Math.round(Number(x.minutes)||1)),w=Number(x.words)||0,c=Number(x.chars)||0,parts=['~'+m+' min read'];
  if(w)parts.push(group(w)+(w===1?' word':' words'));if(c)parts.push(group(c)+(c===1?' character':' characters'));return parts.join(' · ')}
// Font presets: one press sets font, text size, line width and line spacing together. Each value is an ordinary toolbar
// choice, so it is saved like any other and a later single tweak just leaves the preset ("Custom"). Dyslexia-friendly is
// spacing-based (the "Easy read" face: DejaVu Sans with wider letter and word spacing, relaxed lines, narrow column); no
// font is bundled: OpenDyslexic (OFL) is ~300 KB a weight, and Omni's font folder ships none of it.
const PRESETS=Object.freeze([
  {key:'comfort',label:'Comfort',set:{font:'serif',size:'large',width:'medium',spacing:'relaxed'}},
  {key:'clean',label:'Clean',set:{font:'sans',size:'medium',width:'medium',spacing:'normal'}},
  {key:'big',label:'Big',set:{font:'sans',size:'giant',width:'wide',spacing:'normal'}},
  {key:'dyslexia',label:'Dyslexia',set:{font:'readable',size:'huge',width:'narrow',spacing:'relaxed'}}
].map(p=>Object.freeze(Object.assign(p,{set:Object.freeze(p.set)}))));
const PRESET_BY_KEY=Object.freeze(Object.fromEntries(PRESETS.map(p=>[p.key,p])));
// The preset the current options match exactly, or '' (Custom).
function presetOf(p){if(!p)return'';for(const x of PRESETS)if(Object.keys(x.set).every(k=>p[k]===x.set[k]))return x.key;return''}
// Comfort -> Clean -> Big -> Dyslexia -> Comfort; from Custom it starts at Comfort.
function nextPreset(p){const i=PRESETS.findIndex(x=>x.key===presetOf(p));return PRESETS[(i+1)%PRESETS.length].key}
// New toolbar choices with a preset's values on top (unknown preset: unchanged copy).
function applyPreset(choices,key){const x=PRESET_BY_KEY[key];return Object.assign({},clean(choices),x?x.set:{})}
const presetLabel=p=>{const k=presetOf(p);return k?PRESET_BY_KEY[k].label:'Custom'};
return Object.freeze({STORAGE_KEY,OPTIONS,BY_KEY,DEFAULTS,MANIFEST_KEYS,PRESETS,PRESET_BY_KEY,valid,resolve,clean,pack,load,step,atEnd,themeFor,classes,timeLabel,headLabel,presetOf,nextPreset,applyPreset,presetLabel})});
