// Omni add-on "Reader view": page glue. MIT, Omnibloom contributors.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniReaderCore,P=OmniReaderPrefs;
let enabled=false,view=null,fab=null,found=null,idle=0,saved=null,pushed=false,panelPushed=false;
// Reading options: the toolbar's choices live in the add-on's own storage (one key, every page). Private tabs may not
// write there (the shell answers "error: private tab"), so there a change lasts only until the page goes away.
let choices=null,prefs=null,lastBase=null,panel=null,optsBtn=null,timeEl=null,minutes=1,tick=0;
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
const html=()=>document.documentElement;
const base=()=>({size:api.settings.get('size'),theme:api.settings.get('theme')});
function loadPrefs(){lastBase=base();({choices,prefs}=P.load(api.storage.get(P.STORAGE_KEY),lastBase))}
const savePrefs=()=>api.storage.set(P.STORAGE_KEY,P.pack(choices,lastBase)).catch(()=>{});
// Omni's dark pages switch sets the page's dark appearance (prefers-color-scheme) and marks inverted pages data-omnidark.
function darkPages(){try{return html().hasAttribute('data-omnidark')||matchMedia('(prefers-color-scheme: dark)').matches}catch(_){return false}}
// The clean tree from core.js becomes DOM through createElement/textContent only (no page HTML is parsed).
function build(items,parent){for(const it of items){if(typeof it==='string'){parent.append(it);continue}const e=document.createElement(it.tag);
if(it.tag==='a'){e.href=it.attrs.href;e.rel='noopener noreferrer'}
else if(it.tag==='img'){e.src=it.attrs.src;e.alt=it.attrs.alt||'';e.loading='lazy';e.decoding='async';e.referrerPolicy='no-referrer-when-downgrade'}
build(it.kids,e);parent.append(e)}}
function analyse(){idle=0;if(!enabled)return;try{found=core.extract(document,{base:document.baseURI})}catch(e){found=null}showFab()}
function later(){if(idle||!enabled)return;idle=window.requestIdleCallback?requestIdleCallback(analyse,{timeout:3000}):setTimeout(analyse,800)}
function showFab(){const want=enabled&&!view&&found&&found.isArticle&&api.settings.get('button')!==false;if(!want){if(fab){fab.remove();fab=null}return}if(fab)return;
fab=node('button','omni-reader-fab','Reader view');fab.type='button';fab.dataset.omniAddon=api.id;fab.title='Open this article in large text (Alt+Shift+R)';fab.onclick=()=>open();(document.body||html()).append(fab)}
const button=(cls,text,label,fn)=>{const b=node('button','omni-reader-btn '+cls,text);b.type='button';if(label)b.setAttribute('aria-label',label);b.onclick=fn;return b};
// The options panel: one row per option, one big button per choice. Omni's D-pad scrolls and goes back/forward rather
// than reaching the page, so these are pointer targets (left stick + Cross); a keyboard's arrows move between them too.
function buildPanel(){const p=node('div','omni-reader-panel');p.id='omni-reader-panel';p.setAttribute('role','group');p.setAttribute('aria-label','Reading options');p.hidden=true;
for(const o of P.OPTIONS){const row=node('div','omni-reader-row'),name=node('span','omni-reader-label',o.label);name.id='omni-reader-l-'+o.key;row.append(name);
const set=node('div','omni-reader-choices');set.setAttribute('role','group');set.setAttribute('aria-labelledby',name.id);
o.values.forEach((v,i)=>{const b=button('omni-reader-choice omni-reader-c-'+o.key+'-'+v,o.labels[i],'',()=>choose(o.key,v));b.dataset.key=o.key;b.dataset.value=v;set.append(b)});row.append(set);p.append(row)}
const row=node('div','omni-reader-row omni-reader-row-done');row.append(button('omni-reader-done','Done','Close reading options',()=>togglePanel(false)));p.append(row);return p}
function refreshPanel(){if(!view)return;const theme=P.themeFor(prefs.theme,darkPages());
for(const b of view.querySelectorAll('.omni-reader-choice')){const v=b.dataset.key==='theme'?theme:prefs[b.dataset.key];b.setAttribute('aria-pressed',String(v===b.dataset.value))}
const s=view.querySelector('.omni-reader-smaller'),l=view.querySelector('.omni-reader-larger');if(s)s.disabled=P.atEnd('size',prefs.size,-1);if(l)l.disabled=P.atEnd('size',prefs.size,1)}
// The open panel has its own history entry, so Back (Circle) closes the panel first and the reader on the next press.
function togglePanel(want,fromPop){if(!panel)return;const show=want===undefined?panel.hidden:want;if(show===!panel.hidden)return;panel.hidden=!show;optsBtn.setAttribute('aria-expanded',String(show));
if(show&&!panelPushed&&pushed){try{history.pushState(Object.assign({},history.state,{omniReaderPanel:1}),'');panelPushed=true}catch(_){}}
else if(!show&&panelPushed){panelPushed=false;if(!fromPop)try{if(history.state&&history.state.omniReaderPanel)history.back()}catch(_){}}
if(show){const on=panel.querySelector('[aria-pressed="true"]')||panel.querySelector('button');if(on)on.focus({preventScroll:true})}else optsBtn.focus({preventScroll:true})}
// Restyle in place, keeping the reading position (bigger text makes the article longer).
function apply(){if(!view)return;const at=view.scrollHeight>view.clientHeight?view.scrollTop/view.scrollHeight:0;view.className=P.classes(prefs,darkPages());
if(at)view.scrollTop=at*view.scrollHeight;refreshPanel();updateTime()}
function choose(key,value){if(!P.valid(key,value)||!prefs)return;choices=Object.assign({},choices,{[key]:value});prefs=P.resolve(choices,lastBase);apply();savePrefs()}
function resize(dir){const v=P.step('size',prefs.size,dir);if(v!==prefs.size)choose('size',v)}
function updateTime(){tick=0;if(!view||!timeEl)return;const room=view.scrollHeight-view.clientHeight;timeEl.textContent=P.timeLabel(minutes,room>0?view.scrollTop/room:0)}
function onScroll(){if(!tick)tick=requestAnimationFrame(updateTime)}
function open(){if(view||!enabled)return;let r=null;try{r=core.extract(document,{base:document.baseURI})}catch(_){}
if(!r||r.length<300||!r.content.length){api.toast('No article found on this page').catch(()=>{});return}found=r;
if(!prefs)loadPrefs();minutes=r.minutes;
view=node('div',P.classes(prefs,darkPages()));view.id='omni-reader-view';view.dataset.omniAddon=api.id;view.tabIndex=-1;
view.setAttribute('role','dialog');view.setAttribute('aria-modal','true');view.setAttribute('aria-label','Reader view');
const bar=node('div','omni-reader-bar'),where=node('span','omni-reader-where');where.append(node('span','omni-reader-site',r.site||location.hostname.replace(/^www\./,'')),' · ');
timeEl=node('span','omni-reader-left',P.timeLabel(minutes,0));where.append(timeEl);
optsBtn=button('omni-reader-opts','Aa Options','Reading options: text size, line width, font, colours, line spacing',()=>togglePanel());optsBtn.setAttribute('aria-expanded','false');
bar.append(where,button('omni-reader-smaller','A−','Smaller text',()=>resize(-1)),button('omni-reader-larger','A+','Larger text',()=>resize(1)),optsBtn,button('omni-reader-close','Close reader','',()=>close()));
panel=buildPanel();optsBtn.setAttribute('aria-controls',panel.id);bar.append(panel);
const art=node('article','omni-reader-article');if(r.lang)art.lang=r.lang;if(r.dir==='rtl'||r.dir==='ltr')art.dir=r.dir;
art.append(node('p','omni-reader-time','About '+r.minutes+' min read'+(r.words?' · '+r.words.toLocaleString()+' words':'')));
art.append(node('h1','omni-reader-title',r.title||document.title));if(r.byline)art.append(node('p','omni-reader-byline',r.byline));
const body=node('div','omni-reader-body');build(r.content,body);art.append(body);
const foot=node('p','omni-reader-end');foot.append(button('omni-reader-close','Close reader','',()=>close()));art.append(foot);
view.append(bar,art);view.addEventListener('scroll',onScroll,{passive:true});refreshPanel();
// Keep Omni's dark-pages invert filter off while open (it would invert this panel); put the page back on close.
const h=html();saved={dark:h.getAttribute('data-omni-dark'),overflow:h.style.getPropertyValue('overflow'),prio:h.style.getPropertyPriority('overflow'),focus:document.activeElement,y:scrollY};
h.setAttribute('data-omni-dark','off');h.style.setProperty('overflow','hidden','important');
if(fab){fab.remove();fab=null}h.append(view);view.focus({preventScroll:true});
// Back (Circle / browser back) closes the reader instead of leaving the article.
try{const st=history.state&&typeof history.state==='object'?Object.assign({},history.state):{};st.omniReaderView=1;history.pushState(st,'');pushed=true}catch(_){pushed=false}
addEventListener('popstate',onPop);addEventListener('keydown',onViewKey,true)}
function close(fromPop){if(!view)return;removeEventListener('popstate',onPop);removeEventListener('keydown',onViewKey,true);if(tick){cancelAnimationFrame(tick);tick=0}
view.remove();view=null;panel=optsBtn=timeEl=null;const h=html();
if(saved){if(saved.dark===null)h.removeAttribute('data-omni-dark');else h.setAttribute('data-omni-dark',saved.dark);
if(saved.overflow)h.style.setProperty('overflow',saved.overflow,saved.prio);else h.style.removeProperty('overflow');
scrollTo(0,saved.y);if(saved.focus&&saved.focus.isConnected)try{saved.focus.focus({preventScroll:true})}catch(_){}saved=null}
if(pushed&&!fromPop){const n=panelPushed?2:1;try{if(history.state&&history.state.omniReaderView)history.go(-n)}catch(_){}}pushed=panelPushed=false;showFab()}
function onPop(){if(!view)return;const st=history.state;if(!(st&&st.omniReaderView)){panelPushed=false;close(true)}else if(panelPushed&&!st.omniReaderPanel){panelPushed=false;togglePanel(false,true)}}
function editable(t){return t&&(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))}
// Arrow keys inside the toolbar move between its buttons: left/right along a row, up/down to the nearest one in the next row.
function moveFocus(e){const bar=view.querySelector('.omni-reader-bar');if(!bar||!bar.contains(e.target)||e.target.tagName!=='BUTTON')return false;
const rows=[[...bar.children].filter(c=>c.tagName==='BUTTON')];if(panel&&!panel.hidden)for(const r of panel.children)rows.push([...r.querySelectorAll('button')]);
const live=rows.map(r=>r.filter(b=>!b.disabled)).filter(r=>r.length);let ri=live.findIndex(r=>r.includes(e.target));if(ri<0)return false;let ci=live[ri].indexOf(e.target);
if(e.key==='ArrowLeft'||e.key==='ArrowRight')ci=Math.max(0,Math.min(live[ri].length-1,ci+(e.key==='ArrowRight'?1:-1)));
else{const rect=e.target.getBoundingClientRect(),mid=rect.left+rect.width/2;ri=Math.max(0,Math.min(live.length-1,ri+(e.key==='ArrowDown'?1:-1)));
let best=0,d=Infinity;live[ri].forEach((b,i)=>{const q=b.getBoundingClientRect(),dd=Math.abs(q.left+q.width/2-mid);if(dd<d){d=dd;best=i}});ci=best}
live[ri][ci].focus({preventScroll:true});return true}
function onViewKey(e){if(!view)return;if(e.key==='Escape'||e.key==='GoBack'||(e.key==='Backspace'&&!editable(e.target))){e.preventDefault();e.stopImmediatePropagation();
if(panel&&!panel.hidden)togglePanel(false);else close();return}
if(/^Arrow(Left|Right|Up|Down)$/.test(e.key)&&!e.altKey&&!e.ctrlKey&&!e.metaKey&&moveFocus(e)){e.preventDefault();e.stopImmediatePropagation();return}
// While open the page's own shortcuts stay quiet; scrolling keys reach the reader (the default action still runs).
if(!e.ctrlKey&&!e.metaKey&&!(e.altKey&&e.shiftKey)){if(!view.contains(e.target))view.focus({preventScroll:true});e.stopImmediatePropagation()}}
function onKey(e){if(!enabled||!e.isTrusted||!e.altKey||!e.shiftKey||e.code!=='KeyR'||e.repeat)return;e.preventDefault();e.stopImmediatePropagation();view?close():open()}
function onLoad(){later()}
function start(live){if(enabled)return;enabled=true;addEventListener('keydown',onKey,true);
if(document.readyState==='complete')later();else addEventListener('load',onLoad,{once:true});
if(live&&document.visibilityState!=='hidden')open()}
function stop(){if(!enabled)return;enabled=false;removeEventListener('keydown',onKey,true);removeEventListener('load',onLoad);if(idle){(window.cancelIdleCallback||clearTimeout)(idle);idle=0}close();if(fab){fab.remove();fab=null}found=null}
// Switched on from the quick switch while this page is open: the switch itself is the request to read it.
function injectedLate(){try{const nav=performance.getEntriesByType('navigation')[0];return document.readyState==='complete'&&nav&&nav.loadEventEnd>0&&performance.now()-nav.loadEventEnd>1500}catch(_){return false}}
api.onEnable(()=>start(true));api.onDisable(stop);
// A change on the add-on settings page wins over the toolbar's saved choice for that option.
api.onSettings(()=>{if(!enabled)return;if(prefs){const now=base(),had=Object.keys(choices).length;({choices,prefs}=P.load(P.pack(choices,lastBase),now));lastBase=now;
if(Object.keys(choices).length!==had)savePrefs()}
if(view)apply();else showFab()});
window.OmniReaderDiagnostics=()=>({enabled,open:!!view,article:!!(found&&found.isArticle),length:found?found.length:0,paragraphs:found?found.paragraphs:0,prefs:prefs&&Object.assign({},prefs)});
if(api.active)start(injectedLate())})();
