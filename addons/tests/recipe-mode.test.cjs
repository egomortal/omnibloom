// node --test addons/tests   (Recipe mode add-on: detection on small HTML fixtures, amounts, timers, page glue; no browser)
'use strict';
const test=require('node:test'),a=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const C=require('../bundled/omni-recipe-mode/core.js'),{parse}=require('./mini-dom.cjs');
const DIR=path.join(__dirname,'..','bundled','omni-recipe-mode');
const html=name=>fs.readFileSync(path.join(__dirname,'fixtures',name),'utf8');
const load=(name,base)=>parse(html(name),base);

test('JSON-LD @graph: Recipe with a @type array, sections, steps, tip, durations; broken and unrelated blocks are skipped',()=>{
  const r=C.find(load('recipe-graph.html','https://kitchen.example.com/lentil-soup/'));
  a.ok(r);a.equal(r.name,'Weeknight Lentil Soup & Lemon');a.deepEqual(r.yield,{text:'4 servings',count:4});
  a.equal(r.prep,900);a.equal(r.cook,2400);a.equal(r.total,3300);
  a.deepEqual(r.ingredients,['1 1/2 cups red lentils','½ tsp ground cumin','2 tbsp olive oil','1 (400 g) tin chopped tomatoes','2-3 garlic cloves, crushed','Salt to taste','1½ litres stock']);
  a.equal(r.steps.length,5);
  a.deepEqual(r.steps.map(s=>s.section),['Base','Base','Finish','Finish','Finish']);
  a.equal(r.steps[0].text,'Warm the oil and fry the garlic and cumin for 30 seconds.');
  a.doesNotMatch(r.steps[0].text,/<b>/);a.equal(r.steps[0].timers[0].seconds,30);
  a.deepEqual(r.steps[1].timers.map(t=>[t.seconds,t.max,t.label]),[[1200,1500,'20-25 minutes']]);
  a.equal(r.steps[2].timers.length,0);a.equal(r.steps[3].tip,true);a.equal(r.steps[3].timers.length,0,'"3 days" is not a timer');
  a.deepEqual(r.steps[4].timers.map(t=>t.seconds),[300],'performTime gives a timer when the text has none');
});
test('top-level JSON-LD array; newline-separated ingredients; text steps with <br>; ranges and two timers in one step',()=>{
  const r=C.find(load('recipe-array.html'));a.ok(r);a.equal(r.name,'No-knead bread');a.deepEqual(r.yield,{text:'1 loaf',count:1});a.equal(r.total,45000);
  a.deepEqual(r.ingredients,['3 cups flour','1,5 tsp salt','¼ tsp yeast']);
  a.deepEqual(r.steps.map(s=>s.text),['Mix everything in a bowl.','Cover and leave for 12 hours.','Shape the dough.','Bake 30 minutes covered, then 15 to 20 minutes uncovered.']);
  a.deepEqual(r.steps[1].timers.map(t=>t.seconds),[43200]);a.deepEqual(r.steps[3].timers.map(t=>[t.seconds,t.max]),[[1800,1800],[900,1200]]);
});
test('microdata: nested in a WebPage item, meta/time values, ol of steps; the other Recipe item and HowToStep item work too',()=>{
  const r=C.find(load('recipe-microdata.html'));a.ok(r);a.equal(r.name,'Fluffy pancakes');a.deepEqual(r.yield,{text:'8 pancakes',count:8});a.equal(r.prep,600);a.equal(r.cook,900);
  a.deepEqual(r.ingredients,['1 ½ cups milk','2 eggs','⅓ cup sugar']);a.ok(!r.ingredients.includes('Sam'),'the author item stays out');
  a.deepEqual(r.steps.map(s=>s.text),['Whisk the milk and eggs.','Rest the batter for 10 minutes.','Cook each pancake 2 minutes a side.']);
  a.equal(r.steps[1].timers[0].seconds,600);
  const src=html('recipe-microdata.html'),syrup=src.slice(0,src.indexOf('<div itemscope itemtype="https://schema.org/WebPage">'))+src.slice(src.lastIndexOf('<div itemscope itemtype="https://schema.org/Recipe">'));
  const s=C.find(parse(syrup));a.equal(s.name,'Syrup');a.deepEqual(s.ingredients,['1 cup sugar']);a.deepEqual(s.steps.map(x=>[x.text,x.timers[0].seconds]),[['Boil for 5 minutes.',300]]);
});
test('no schema.org Recipe, no recipe: recipe-looking classes, headings and an Article are not enough',()=>{
  a.equal(C.find(load('recipe-none.html')),null);a.equal(C.find(parse('<p>nothing</p>')),null);
  a.equal(C.find(parse('<script type="application/ld+json">{"@type":"Recipe","name":"Empty"}</script>')),null,'a Recipe with no ingredients and no steps is ignored');
});
test('JSON-LD shapes: nested objects, schema: prefixes, ItemList, HowToStep with directions, entities, comments, strings in sections',()=>{
  const r=C.normalize(C.collectRecipes(C.parseJson('<!-- {"mainEntity":{"@type":"schema:Recipe","name":"Tea","recipeIngredient":[{"name":"1 tea bag"},"250 ml water &amp; milk"],'+
    '"recipeInstructions":{"@type":"ItemList","itemListElement":[{"@type":"ListItem","item":{"@type":"HowToStep","text":"Boil the water."}},'+
    '{"@type":"HowToStep","itemListElement":[{"@type":"HowToDirection","text":"Pour."},{"@type":"HowToDirection","text":"Steep 4 minutes."}]},'+
    '{"@type":"HowToSection","name":"Serve","itemListElement":["Add milk.","Drink."]}]}}} -->'))[0]);
  a.equal(r.name,'Tea');a.deepEqual(r.ingredients,['1 tea bag','250 ml water & milk']);
  a.deepEqual(r.steps.map(s=>[s.text,s.section]),[['Boil the water.',''],['Pour. Steep 4 minutes.',''],['Add milk.','Serve'],['Drink.','Serve']]);
  a.equal(r.steps[1].timers[0].seconds,240);
  a.equal(C.parseJson('{"a":"x\ny"}').a,'x y','raw newlines inside strings are tolerated');a.equal(C.parseJson('{bad'),undefined);
});
test('ISO 8601 durations and their labels',()=>{
  for(const[v,s]of[['PT1H30M',5400],['P0DT0H20M',1200],['PT0.5H',1800],['PT90M',5400],['PT45S',45],['P1DT2H',93600],['pt10m',600],['PT',0],['P',0],['10 minutes',0],[undefined,0],['PT1,5H',5400]])a.equal(C.duration(v),s,String(v));
  a.equal(C.human(5400),'1 h 30 min');a.equal(C.human(45),'45 s');a.equal(C.human(93600),'1 d 2 h');a.equal(C.clock(605),'10:05');a.equal(C.clock(3723),'1:02:03');a.equal(C.clock(.2),'0:01');
});
test('amounts: leading quantities incl. ½, 1½, 1 ½, 1 1/2, 1/2, decimals, commas and ranges; the rest of the line stays',()=>{
  const x2=s=>C.scaleIngredient(s,2),half=s=>C.scaleIngredient(s,.5);
  a.equal(x2('1 1/2 cups flour'),'3 cups flour');a.equal(half('1 1/2 cups flour'),'¾ cups flour');
  a.equal(x2('½ tsp salt'),'1 tsp salt');a.equal(half('½ tsp salt'),'¼ tsp salt');
  a.equal(x2('1½ cups milk'),'3 cups milk');a.equal(x2('1 ½ cups milk'),'3 cups milk');a.equal(half('⅓ cup sugar'),'0.17 cup sugar');
  a.equal(x2('1/3 cup oil'),'⅔ cup oil');a.equal(x2('1⁄4 tsp'),'½ tsp');a.equal(x2('0.25 cup'),'½ cup');a.equal(half('1,5 kg potatoes'),'¾ kg potatoes');
  a.equal(x2('400g tomatoes'),'800g tomatoes');a.equal(x2('1 (400 g) tin tomatoes'),'2 (400 g) tin tomatoes');
  a.equal(x2('2-3 garlic cloves'),'4-6 garlic cloves');a.equal(half('3 to 4 apples'),'1½ to 2 apples');a.equal(half('3 eggs'),'1½ eggs');
  a.equal(x2('Salt to taste'),'Salt to taste');a.equal(x2('one onion'),'one onion');a.equal(x2('1,000 g flour'),'2000 g flour');a.equal(half('1,250 ml water'),'625 ml water');
  a.equal(C.scaleIngredient('1 1/2 cups',1),'1 1/2 cups','×1 leaves the text exactly as written');
  a.equal(C.formatNumber(2),'2');a.equal(C.formatNumber(.75),'¾');a.equal(C.formatNumber(2.5),'2½');a.equal(C.formatNumber(.4),'0.4');a.equal(C.formatNumber(1.999),'2');
  a.deepEqual(C.parseNumber('Serves 4-6'),{value:4,start:7,end:8});
});
test('timers: minutes, hours, seconds, ranges, words, compound and hyphenated forms; temperatures and days are not timers',()=>{
  const t=s=>C.timers(s).map(x=>[x.seconds,x.max,x.label]);
  a.deepEqual(t('Simmer for 10 minutes.'),[[600,600,'10 minutes']]);a.deepEqual(t('Bake 25–30 mins'),[[1500,1800,'25–30 mins']]);
  a.deepEqual(t('Roast 1 hour and 15 minutes, then rest 10 min.'),[[4500,4500,'1 hour and 15 minutes'],[600,600,'10 min']]);
  a.deepEqual(t('Chill 1 1/2 hours'),[[5400,5400,'1 1/2 hours']]);a.deepEqual(t('Chill 1½ hrs'),[[5400,5400,'1½ hrs']]);a.deepEqual(t('Leave an hour'),[[3600,3600,'an hour']]);
  a.deepEqual(t('Whisk thirty seconds, rest a 5-minute break'),[[30,30,'thirty seconds'],[300,300,'5-minute']]);
  a.deepEqual(t('Heat to 180°C (350°F). Keeps 3 days. Cut 2 cm pieces.'),[]);a.deepEqual(t('Cook 10 or 12 minutes'),[[600,720,'10 or 12 minutes']]);
  a.deepEqual(t('Use 2 tablespoons'),[],'"2 t..." is not a time');a.deepEqual(t('Mix 1.5 minutes'),[[90,90,'1.5 minutes']]);
});
test('per-page state: key without the address, tracking parameters ignored, restore checks the count, pruning keeps 150',()=>{
  const k=C.key('https://www.kitchen.example.com/soup/?utm_source=x&id=2#comments');a.equal(k,C.key('https://kitchen.example.com/soup?id=2&fbclid=z'));
  a.ok(k.startsWith(C.PREFIX)&&!k.includes('kitchen'));a.notEqual(k,C.key('https://kitchen.example.com/soup?id=3'));a.equal(C.key('ftp://x/y'),null);
  const e=C.entry({checked:new Set([3,0,9,-1]),n:7,scale:2,step:4},1700000000999);a.deepEqual(e,{c:[0,3],n:7,s:2,i:4,a:1700000000});
  const r=C.restore(e,7,5);a.deepEqual([...r.checked],[0,3]);a.equal(r.scale,2);a.equal(r.step,4);
  const changed=C.restore(e,8,3);a.equal(changed.checked.size,0,'other ingredient count: ticks dropped');a.equal(changed.step,0);a.equal(changed.scale,2);
  a.deepEqual(C.restore('junk',7,5),{checked:new Set(),scale:1,step:0});a.equal(C.restore({c:[],n:7,s:3,i:0},7,5).scale,1);
  const all={other:1};for(let i=0;i<160;i++)all[C.PREFIX+i]={c:[],n:1,s:1,i:0,a:1000+i};all[C.PREFIX+'bad']=[1];
  const drop=C.prune(all);a.equal(drop.length,11);a.ok(drop.includes(C.PREFIX+'bad'));a.ok(drop.includes(C.PREFIX+'9'));a.ok(!drop.includes(C.PREFIX+'10'));a.ok(!drop.includes('other'));
  let bytes=0;for(let i=0;i<150;i++)bytes+=C.key('https://e.com/'+i).length+JSON.stringify(C.entry({checked:new Set(Array.from({length:60},(_,j)=>j)),n:60,scale:.5,step:40},Date.now())).length;
  a.ok(bytes<64*1024,String(bytes));
  a.equal(C.nextScale(1),2);a.equal(C.nextScale(2),.5);a.equal(C.nextScale(.5),1);a.equal(C.scaleLabel(.5),'×½');
});
test('source rules: no network, no HTML parsing into the page, no audio, off by default',()=>{
  const m=JSON.parse(fs.readFileSync(path.join(DIR,'manifest.json'),'utf8'));a.equal(m.default_on,false);a.deepEqual(m.hosts,[]);a.equal(m.private_safe,true);
  for(const f of['core.js','runtime.js']){const s=fs.readFileSync(path.join(DIR,f),'utf8');
    a.doesNotMatch(s,/\bfetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|\beval\(|new Function/);
    a.doesNotMatch(s,/innerHTML|outerHTML|insertAdjacentHTML|document\.write|DOMParser/);a.doesNotMatch(s,/AudioContext|new Audio|speechSynthesis/);
    a.ok(![...s].some(ch=>ch.charCodeAt(0)===0x2028||ch.charCodeAt(0)===0x2029),'no raw line separators');}
  a.match(fs.readFileSync(path.join(__dirname,'..','..','omni','webkit','configure-cmd.json'),'utf8'),/ENABLE_WEB_AUDIO:BOOL=OFF/,'if Web Audio turns ON, a timer beep becomes possible');
});

// ---- The page glue against a small fake page ----
function harness(opts={}){
  const vm=require('node:vm');let T=1700000000000;const intervals=new Map();let iv=0;
  class El{constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;this.attrs={};this.dataset={};this.className='';this.id='';this.hidden=false;this.disabled=false;this._t='';this.listeners={};
    this.style={p:{},getPropertyValue:k=>this.style.p[k]||'',getPropertyPriority:()=>'',setProperty:(k,v)=>{this.style.p[k]=v},removeProperty:k=>{delete this.style.p[k]}};
    const self=this;this.classList={add(c){if(!self.className.split(' ').includes(c))self.className=(self.className+' '+c).trim()},contains:c=>self.className.split(' ').includes(c)}}
    get textContent(){return this._t+this.children.map(c=>c.textContent).join('')}set textContent(v){this._t=String(v);for(const c of this.children)c.parentNode=null;this.children=[]}
    get childNodes(){return this.children}
    append(...xs){for(const x of xs)if(typeof x!=='string'){x.parentNode=this;this.children.push(x)}else{const t=new El('#text');t._t=x;t.parentNode=this;this.children.push(t)}}
    remove(){if(this.parentNode){this.parentNode.children=this.parentNode.children.filter(c=>c!==this);this.parentNode=null}}
    get isConnected(){let n=this;while(n.parentNode)n=n.parentNode;return n===root}
    setAttribute(k,v){this.attrs[k]=String(v)}getAttribute(k){return k in this.attrs?this.attrs[k]:null}hasAttribute(k){return k in this.attrs}removeAttribute(k){delete this.attrs[k]}
    addEventListener(t,f){(this.listeners[t]||(this.listeners[t]=[])).push(f)}
    focus(){document.activeElement=this}scrollIntoView(){}
    all(){const out=[];for(const c of this.children)if(c.tagName!=='#TEXT')out.push(c,...c.all());return out}
    matches(sel){if(sel.startsWith('.'))return this.className.split(' ').includes(sel.slice(1));return this.tagName===sel.toUpperCase()}
    querySelectorAll(sel){return this.all().filter(e=>e.matches(sel))}querySelector(sel){return this.querySelectorAll(sel)[0]||null}
    contains(n){return n===this||this.all().includes(n)}
    click(){if(this.onclick)this.onclick()}
    requestFullscreen(){if(opts.noFullscreen)return Promise.reject(new Error('denied'));document.fullscreenElement=this;setImmediate(()=>fireDoc('fullscreenchange'));return Promise.resolve()}}
  const root=new El('html'),body=new El('body');root.append(body);
  const docL={};const fireDoc=t=>(docL[t]||[]).slice().forEach(f=>f({}));
  const document={documentElement:root,body,readyState:'complete',visibilityState:'visible',title:'Soup page',activeElement:body,fullscreenElement:null,createElement:t=>new El(t),
    addEventListener(t,f){(docL[t]||(docL[t]=[])).push(f)},removeEventListener(t,f){docL[t]=(docL[t]||[]).filter(x=>x!==f)},
    exitFullscreen(){document.fullscreenElement=null;setImmediate(()=>fireDoc('fullscreenchange'));return Promise.resolve()}};
  const store=new Map(opts.stored?Object.entries(opts.stored).map(([k,v])=>[k,JSON.stringify(v)]):[]),writes=[],toasts=[];
  const api={id:'omni-recipe-mode',top:true,active:true,onEnable(){},onDisable(){},onSettings(){},toast:m=>{toasts.push(m);return Promise.resolve(true)},
    settings:{get:k=>k==='button'?opts.button!==false:undefined},
    storage:{get:k=>store.has(k)?JSON.parse(store.get(k)):undefined,keys:()=>[...store.keys()],
      set(k,v){writes.push([k,JSON.parse(JSON.stringify(v))]);if(opts.private)return Promise.reject(new Error('error: private tab'));store.set(k,JSON.stringify(v));return Promise.resolve(true)},
      remove(k){store.delete(k);return Promise.resolve(true)}}};
  const win={listeners:{}},hist=[{}];let at=0;
  const go=n=>{at=Math.max(0,at+n);setImmediate(()=>(win.listeners.popstate||[]).slice().forEach(f=>f({})))};
  const history={get state(){return hist[at]},pushState(s){hist.length=at+1;hist.push(JSON.parse(JSON.stringify(s)));at++},back:()=>go(-1),go};
  const doc=load(opts.fixture||'recipe-graph.html'),Core=Object.assign({},C,{find:()=>C.find(doc)});
  Object.assign(win,{addEventListener(t,f){(win.listeners[t]||(win.listeners[t]=[])).push(f)},removeEventListener(t,f){win.listeners[t]=(win.listeners[t]||[]).filter(x=>x!==f)},
    document,history,location:{href:'https://www.kitchen.example.com/lentil-soup/?utm_source=feed'},scrollY:0,scrollTo(){},navigator:{},
    requestIdleCallback:f=>{setImmediate(f);return 1},cancelIdleCallback(){},setTimeout,clearTimeout,setImmediate,
    setInterval:f=>{intervals.set(++iv,f);return iv},clearInterval:i=>intervals.delete(i),Date:{now:()=>T},
    omniAddon:api,OmniRecipeCore:Core,Promise,Object,JSON,String,Number,Array,Math,RegExp,Error,Set,Map});
  win.window=win;win.globalThis=win;vm.createContext(win);vm.runInContext(fs.readFileSync(path.join(DIR,'runtime.js'),'utf8'),win);
  const key=k=>(win.listeners.keydown||[]).slice().forEach(f=>f(Object.assign({isTrusted:true,altKey:false,shiftKey:false,ctrlKey:false,metaKey:false,repeat:false,target:document.activeElement,preventDefault(){},stopImmediatePropagation(){}},k)));
  const view=()=>root.querySelector('.omni-recipe');const q=cls=>view().querySelector('.'+cls),qa=cls=>view().querySelectorAll('.'+cls);
  const tick=()=>new Promise(r=>setImmediate(()=>setImmediate(r)));
  return{store,writes,toasts,view,q,qa,key,tick,document,history,hist:()=>hist.slice(0,at+1),win,fab:()=>root.querySelector('.omni-recipe-fab'),
    advance(ms){T+=ms;for(const f of[...intervals.values()])f()},intervals};
}
test('page glue: button on a recipe page; opens full screen; L1/R1 (j/l) and arrows step; Circle (leaving full screen) closes',async()=>{
  const h=harness();await h.tick();a.ok(h.fab(),'Recipe mode button shown');h.fab().click();await h.tick();
  const v=h.view();a.ok(v);a.equal(h.document.fullscreenElement,v);a.equal(h.fab(),null);a.equal(h.hist().length,2);
  a.equal(h.q('omni-recipe-title').textContent,'Weeknight Lentil Soup & Lemon');a.equal(h.q('omni-recipe-meta').textContent,'Prep 15 min · Cook 40 min');
  a.match(h.q('omni-recipe-hint').textContent,/L1 \/ R1/);a.equal(h.q('omni-recipe-pos').textContent,'Step 1 of 5 · Base');a.equal(h.q('omni-recipe-prev').disabled,true);
  h.key({key:'l'});a.equal(h.q('omni-recipe-pos').textContent,'Step 2 of 5 · Base');a.match(h.q('omni-recipe-text').textContent,/Simmer for 20-25 minutes/);
  h.key({key:'ArrowRight'});h.key({key:'ArrowRight'});a.equal(h.q('omni-recipe-pos').textContent,'Step 4 of 5 · Finish · Tip');
  h.key({key:'j'});h.key({key:'ArrowLeft'});a.equal(h.q('omni-recipe-pos').textContent,'Step 2 of 5 · Base');
  for(let i=0;i<9;i++)h.key({key:'l'});a.equal(h.q('omni-recipe-pos').textContent,'Step 5 of 5 · Finish');a.equal(h.q('omni-recipe-next').disabled,true);
  await h.tick();const saved=[...h.store.entries()];a.equal(saved.length,1);a.ok(saved[0][0].startsWith('p:'));a.equal(JSON.parse(saved[0][1]).i,4);
  // Circle: Omni leaves full screen
  h.document.exitFullscreen();await h.tick();a.equal(h.view(),null,'closed');a.equal(h.hist().length,1,'history entry taken back');a.ok(h.fab(),'button back');
});
test('ingredients: Cross on one ticks it, D-pad down + Square ticks the next; ticks, amounts and step come back on reopen',async()=>{
  const h=harness();await h.tick();h.fab().click();await h.tick();
  const ing=()=>h.qa('omni-recipe-ing');a.equal(ing().length,7);a.equal(h.q('omni-recipe-count').textContent,'0 of 7 ready');
  ing()[1].click();a.equal(ing()[1].getAttribute('aria-checked'),'true');a.equal(h.q('omni-recipe-count').textContent,'1 of 7 ready');
  h.key({key:'ArrowDown'});h.key({key:'k'});a.equal(ing()[2].getAttribute('aria-checked'),'true');a.ok(ing()[2].classList.contains('omni-recipe-cursor'));
  h.key({key:'k'});a.equal(ing()[2].getAttribute('aria-checked'),'false','Square again unticks');h.key({key:'k'});
  h.qa('omni-recipe-sc')[2].click();a.deepEqual(ing().map(b=>b.textContent).slice(0,5),['3 cups red lentils','1 tsp ground cumin','4 tbsp olive oil','2 (400 g) tin chopped tomatoes','4-6 garlic cloves, crushed']);
  a.equal(ing()[5].textContent,'Salt to taste');a.equal(h.q('omni-recipe-yield').textContent,'4 servings → 8');a.equal(h.qa('omni-recipe-sc')[2].getAttribute('aria-pressed'),'true');
  h.key({key:'m'});a.equal(ing()[0].textContent,'¾ cups red lentils','L3 cycles to ×½');a.equal(h.q('omni-recipe-yield').textContent,'4 servings → 2');
  h.key({key:'l'});h.key({key:'Escape'});await h.tick();a.equal(h.view(),null);
  const st=JSON.parse([...h.store.values()][0]);a.deepEqual(st,{c:[1,2],n:7,s:.5,i:1,a:1700000000});
  h.fab().click();await h.tick();a.deepEqual(ing().map(b=>b.getAttribute('aria-checked')),['false','true','true','false','false','false','false']);
  a.equal(h.q('omni-recipe-pos').textContent,'Step 2 of 5 · Base');a.equal(ing()[0].textContent,'¾ cups red lentils');
});
test('timers: a press starts the countdown, a second press pauses, it keeps running on other steps and ends in an on-screen alert',async()=>{
  const h=harness();await h.tick();h.fab().click();await h.tick();h.key({key:'l'});
  const tb=()=>h.q('omni-recipe-timer');a.equal(tb().textContent,'Start 20 min timer');tb().click();a.equal(tb().textContent,'20:00 ❚❚');a.equal(h.intervals.size,1);
  h.advance(65000);a.equal(tb().textContent,'18:55 ❚❚');tb().click();a.equal(tb().textContent,'18:55 ▶');a.equal(h.intervals.size,0,'nothing ticks while paused');
  h.advance(600000);h.key({key:'c'});a.equal(tb().textContent,'18:55 ❚❚','Triangle resumes the step timer');
  h.key({key:'l'});const chip=h.q('omni-recipe-chip');a.ok(chip);a.equal(chip.textContent,'Step 2: 18:55');a.equal(h.q('omni-recipe-tray').hidden,false);
  h.advance(18*60000+55000);const al=h.q('omni-recipe-alert');a.equal(al.hidden,false);a.match(al.textContent,/Time is up: step 2 \(20-25 minutes\)/);
  a.equal(h.q('omni-recipe-chip').textContent,'Step 2: done');a.equal(h.intervals.size,0);
  h.key({key:'k'});a.equal(al.hidden,true,'Square clears the alert');a.equal(h.q('omni-recipe-chip'),null);
  a.equal(h.q('omni-recipe-pos').textContent,'Step 3 of 5 · Finish','the alert key did not tick or step');
  h.key({key:'j'});a.equal(tb().textContent,'Start 20 min timer');
  tb().click();h.key({key:'Escape'});await h.tick();a.equal(h.view(),null);h.advance(1200000);a.deepEqual(h.toasts,['Time is up: step 2 (20-25 minutes)'],'closed view: a toast instead');
});
test('private tab: storage refused once, ticks kept in memory for this page only; no full screen falls back to an overlay closed by Back',async()=>{
  const h=harness({private:true,noFullscreen:true});await h.tick();h.fab().click();await h.tick();
  a.equal(h.document.fullscreenElement,null);a.match(h.q('omni-recipe-hint').textContent,/Back closes/);
  h.qa('omni-recipe-ing')[0].click();await h.tick();h.qa('omni-recipe-ing')[3].click();await h.tick();a.equal(h.store.size,0);
  const n=h.writes.length;a.equal(n,1,'one refused write, then memory only');
  h.history.back();await h.tick();a.equal(h.view(),null,'Back closed it');
  h.fab().click();await h.tick();a.deepEqual(h.qa('omni-recipe-ing').filter(b=>b.getAttribute('aria-checked')==='true').length,2,'still ticked on this page');a.equal(h.writes.length,n);
});
test('no recipe markup: no button, and the shortcut only says so',async()=>{
  const h=harness({fixture:'recipe-none.html'});await h.tick();a.equal(h.fab(),null);
  h.key({key:'K',code:'KeyK',altKey:true,shiftKey:true});await h.tick();a.equal(h.view(),null);a.deepEqual(h.toasts,['No recipe found on this page']);
  const off=harness({button:false});await off.tick();a.equal(off.fab(),null,'button setting off');off.key({key:'K',code:'KeyK',altKey:true,shiftKey:true});a.ok(off.view(),'Alt+Shift+K still opens it');
});
