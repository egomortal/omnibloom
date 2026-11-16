// Omni add-on "Reader view": page glue. MIT, Omnibloom contributors.
(()=>{'use strict';const api=window.omniAddon;if(!api||!api.top)return;const core=OmniReaderCore;
let enabled=false,view=null,fab=null,found=null,idle=0,saved=null,pushed=false;
const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e};
const html=()=>document.documentElement;
function dark(){const t=api.settings.get('theme');if(t==='dark'||t==='light'||t==='sepia')return t;
// Omni's dark pages switch sets the page's dark appearance (prefers-color-scheme) and marks inverted pages data-omnidark.
try{if(html().hasAttribute('data-omnidark')||matchMedia('(prefers-color-scheme: dark)').matches)return'dark'}catch(_){}return'light'}
// The clean tree from core.js becomes DOM through createElement/textContent only (no page HTML is parsed).
function build(items,parent){for(const it of items){if(typeof it==='string'){parent.append(it);continue}const e=document.createElement(it.tag);
if(it.tag==='a'){e.href=it.attrs.href;e.rel='noopener noreferrer'}
else if(it.tag==='img'){e.src=it.attrs.src;e.alt=it.attrs.alt||'';e.loading='lazy';e.decoding='async';e.referrerPolicy='no-referrer-when-downgrade'}
build(it.kids,e);parent.append(e)}}
function analyse(){idle=0;if(!enabled)return;try{found=core.extract(document,{base:document.baseURI})}catch(e){found=null}showFab()}
function later(){if(idle||!enabled)return;idle=window.requestIdleCallback?requestIdleCallback(analyse,{timeout:3000}):setTimeout(analyse,800)}
function showFab(){const want=enabled&&!view&&found&&found.isArticle&&api.settings.get('button')!==false;if(!want){if(fab){fab.remove();fab=null}return}if(fab)return;
fab=node('button','omni-reader-fab','Reader view');fab.type='button';fab.dataset.omniAddon=api.id;fab.title='Open this article in large text (Alt+Shift+R)';fab.onclick=()=>open();(document.body||html()).append(fab)}
function open(){if(view||!enabled)return;let r=null;try{r=core.extract(document,{base:document.baseURI})}catch(_){}
if(!r||r.length<300||!r.content.length){api.toast('No article found on this page').catch(()=>{});return}found=r;
const theme=dark(),size=api.settings.get('size')||'large';
view=node('div','omni-reader omni-reader-'+theme+' omni-reader-'+size);view.id='omni-reader-view';view.dataset.omniAddon=api.id;view.tabIndex=-1;
view.setAttribute('role','dialog');view.setAttribute('aria-modal','true');view.setAttribute('aria-label','Reader view');
const bar=node('div','omni-reader-bar'),where=node('span','omni-reader-where',[r.site||location.hostname.replace(/^www\./,''),r.minutes+' min read'].join(' · ')),x=node('button','omni-reader-close','Close reader');
x.type='button';x.onclick=()=>close();bar.append(where,x);
const art=node('article','omni-reader-article');if(r.lang)art.lang=r.lang;if(r.dir==='rtl'||r.dir==='ltr')art.dir=r.dir;
art.append(node('h1','omni-reader-title',r.title||document.title));if(r.byline)art.append(node('p','omni-reader-byline',r.byline));
const body=node('div','omni-reader-body');build(r.content,body);art.append(body);
const end=node('button','omni-reader-close','Close reader');end.type='button';end.onclick=()=>close();const foot=node('p','omni-reader-end');foot.append(end);art.append(foot);
view.append(bar,art);
// Keep Omni's dark-pages invert filter off while open (it would invert this panel); put the page back on close.
const h=html();saved={dark:h.getAttribute('data-omni-dark'),overflow:h.style.getPropertyValue('overflow'),prio:h.style.getPropertyPriority('overflow'),focus:document.activeElement,y:scrollY};
h.setAttribute('data-omni-dark','off');h.style.setProperty('overflow','hidden','important');
if(fab){fab.remove();fab=null}h.append(view);view.focus({preventScroll:true});
// Back (Circle / browser back) closes the reader instead of leaving the article.
try{const st=history.state&&typeof history.state==='object'?Object.assign({},history.state):{};st.omniReaderView=1;history.pushState(st,'');pushed=true}catch(_){pushed=false}
addEventListener('popstate',onPop);addEventListener('keydown',onViewKey,true)}
function close(fromPop){if(!view)return;removeEventListener('popstate',onPop);removeEventListener('keydown',onViewKey,true);view.remove();view=null;const h=html();
if(saved){if(saved.dark===null)h.removeAttribute('data-omni-dark');else h.setAttribute('data-omni-dark',saved.dark);
if(saved.overflow)h.style.setProperty('overflow',saved.overflow,saved.prio);else h.style.removeProperty('overflow');
scrollTo(0,saved.y);if(saved.focus&&saved.focus.isConnected)try{saved.focus.focus({preventScroll:true})}catch(_){}saved=null}
if(pushed&&!fromPop){pushed=false;try{if(history.state&&history.state.omniReaderView)history.back()}catch(_){}}pushed=false;showFab()}
function onPop(){if(view&&!(history.state&&history.state.omniReaderView))close(true)}
function editable(t){return t&&(t.isContentEditable||/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))}
function onViewKey(e){if(!view)return;if(e.key==='Escape'||e.key==='GoBack'||(e.key==='Backspace'&&!editable(e.target))){e.preventDefault();e.stopImmediatePropagation();close();return}
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
api.onSettings(()=>{if(!enabled)return;if(view)view.className='omni-reader omni-reader-'+dark()+' omni-reader-'+(api.settings.get('size')||'large');else showFab()});
window.OmniReaderDiagnostics=()=>({enabled,open:!!view,article:!!(found&&found.isArticle),length:found?found.length:0,paragraphs:found?found.paragraphs:0});
if(api.active)start(injectedLate())})();
