'use strict';

(() => {
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icon = (name, extra = '') => `<svg class="icon ${extra}" aria-hidden="true"><use href="/assets/icons.svg#${name}"></use></svg>`;
  const UNIVERSE_SYMBOLS=['bloom','relay','loom','kinetic','tide'];
  const emblem = name => `<svg aria-hidden="true" viewBox="0 0 160 160"><use href="/assets/${UNIVERSE_SYMBOLS.includes(name)?'universe-symbols':'nav-symbols'}.svg#${name}"></use></svg>`;
  // Controller labels: Xbox by default (the user's pad); PlayStation names in Settings. Labels only: buttons do not change.
  const GLYPHS={xbox:{cross:'A',circle:'B',triangle:'Y',square:'X',l1:'LB',r1:'RB'},playstation:{cross:'Cross',circle:'Circle',triangle:'Triangle',square:'Square',l1:'L1',r1:'R1'}};
  let uEnter=false;
  let glyphSet='xbox';try{if(localStorage.getItem('omni.glyphs')==='playstation')glyphSet='playstation';}catch(_){}
  const glyphText=text=>String(text).replace(/\{(cross|circle|triangle|square|l1|r1)\}/g,(_,key)=>GLYPHS[glyphSet][key]);
  const applyGlyphs=()=>document.querySelectorAll('[data-glyph]').forEach(node=>{const label=GLYPHS[glyphSet][node.dataset.glyph];if(label&&node.textContent!==label)node.textContent=label;});
  const routes = [
    {id:'launch', label:'Launch', icon:'launch', heading:'Make room for more.', subtitle:'Good things deserve a place of their own.'},
    {id:'queue', label:'Queue', icon:'queue', heading:'Your downloads.', subtitle:'Everything in motion, all in one place.'},
    {id:'library', label:'Saved links', icon:'library', heading:'Good finds, kept.', subtitle:'A little collection of things to come back to.'},
    {id:'activity', label:'Activity', icon:'activity', heading:'The whole picture.', subtitle:'A quiet little record of your discoveries.'},
    {id:'settings', label:'Settings', icon:'settings', heading:'Make it yours.', subtitle:'Small details. A space that feels like you.'}
  ];
  const themes = [
    {id:'bloom',name:'Bloom',symbol:'bloom',type:'UNFURLING PETALS',description:'Potential, opening into possibility.',detail:'Five destinations unfold from one living mark.',hint:'Move between petals<br>{cross} opens a destination',bg:'#11152a',color:'#f0afd0'},
    {id:'relay',name:'Relay',symbol:'relay',type:'PATCHBOARD',description:'Make the next connection.',detail:'Plug into a destination on a quiet signal board.',hint:'Choose a socket<br>{cross} makes the connection',bg:'#091a25',color:'#9ce2df'},
    {id:'loom',name:'Loom',symbol:'loom',type:'WOVEN THREADS',description:'Pull the right thread.',detail:'Each destination is a woven strand to follow.',hint:'Choose a strand<br>{cross} pulls it forward',bg:'#1d2234',color:'#eab8b5'},
    {id:'kinetic',name:'Kinetic',symbol:'kinetic',type:'COUNTERWEIGHT',description:'Find your balance.',detail:'Five hanging weights shift as you choose a destination.',hint:'Move between weights<br>{cross} sets one in motion',bg:'#101925',color:'#8dcfda'},
    {id:'tide',name:'Tide',symbol:'tide',type:'TIDE TABLE',description:'Catch the next current.',detail:'Read a band of the sea, then move with it.',hint:'Choose a current<br>{cross} rides to that view',bg:'#0a1b35',color:'#b5e8d9'},
    {id:'aurora',name:'Aurora',symbol:'flow',type:'GLASS SIDEBAR',description:'A softer flow. Everything within reach.',detail:'A floating glass rail, calm and effortless.',hint:'Pick a destination<br>Let everything else flow',bg:'#172136',color:'#b9d9ff'},
    {id:'cosmic',name:'Cosmic',symbol:'orbit',type:'ORBITAL MAP',description:'Your next discovery is just an orbit away.',detail:'Hop between planets in your own constellation.',hint:'Choose a planet<br>Make it your destination',bg:'#1a1631',color:'#c4b1ff'},
    {id:'arcade',name:'Arcade',symbol:'cabinet',type:'GAME CONTROLLER',description:'Pick your next level. Make your move.',detail:'D-pad selection and a big A to play.',hint:'Move with the D-pad<br>Press A to enter',bg:'#221635',color:'#f2a4ff'},
    {id:'solstice',name:'Solstice',symbol:'canvas',type:'CARD RIBBON',description:'A bright new perspective.',detail:'Swipe through warm, editorial destination cards.',hint:'Slide through the cards<br>Follow what catches your eye',bg:'#eee4d5',color:'#a66436'},
    {id:'metro',name:'Metro',symbol:'transit',type:'TRANSIT MAP',description:'Every destination, beautifully connected.',detail:'Follow the line. Take the next stop.',hint:'Follow the route<br>Next stop: something good',bg:'#192d26',color:'#d4e5a3'},
    {id:'sakura',name:'Sakura',symbol:'story',type:'BOOK CHAPTERS',description:'A new chapter for every good find.',detail:'A paper index with pages to turn.',hint:'Turn with Page Up / Down<br>Your place is always kept',bg:'#f5e7e8',color:'#a7657d'},
    {id:'abyss',name:'Abyss',symbol:'sonar',type:'DEPTH EXPLORER',description:'Dive a little deeper.',detail:'Navigate by depth or slide the sonar control.',hint:'Select a depth<br>Or use the dive control',bg:'#092630',color:'#73dad4'},
    {id:'prism',name:'Prism',symbol:'command',type:'COMMAND PALETTE',description:'A thought becomes a destination.',detail:'Type to find your way. A keyboard-first space.',hint:'Press / to search<br>Enter to go. Escape to clear.',bg:'#e9e9f6',color:'#7660ae'},
    {id:'atlas',name:'Atlas',symbol:'bento',type:'SPATIAL TILES',description:'A home for every little adventure.',detail:'A tactile grid of spaces, each one a doorway.',hint:'Pick a space<br>Everything has its own place',bg:'#e5e9d7',color:'#627340'},
    {id:'cassette',name:'Cassette',symbol:'deck',type:'TAPE DECK',description:'Put on your favorite way around.',detail:'Skip tracks, scrub, then press play.',hint:'Skip to a track<br>Press play to make it yours',bg:'#30251b',color:'#e6ba76'}
  ];
  const routeIds = routes.map(route => route.id);
  let state = {jobs:[], saved_links:[], preferences:{theme:'bloom',reduced_motion:false}, summary:{}};
  let currentRoute = new URLSearchParams(location.hash.slice(1)).get('view')==='saved'?'library':'launch';
  let theme = 'bloom';
  let previewIndex = routeIds.indexOf(currentRoute);
  let transformationTimer;
  let transformationEnd;
  let transformationSequence = 0;
  let transformationResolve = null;
  let jobFilter = 'all';
  let engine = 'ytdlp';
  try { if (localStorage.getItem('omni.themeLab.engine') === 'jdownloader') engine = 'jdownloader'; } catch (_) {}
  let preferenceStorage;try{preferenceStorage=localStorage;}catch(_){}
  const client = window.OmniProductionApi.create({token:$('meta[name="omni-session-token"]').content,storage:preferenceStorage});
  let requestChain = Promise.resolve();
  let sectionVisible=true;
  const sectionActive=()=>sectionVisible&&!document.hidden;
  let candidateLink='',candidateDetected=false,savingCandidate=false,candidateEpoch=0;
  let candidateSnapshot=null,candidateWireError='';
  // OMNI_DOWNLOADS_PAD_V2: the last input decides what Cross acts on. 'pointer' lets the
  // engine's native click land under the pointer; 'pad' acts on the focused control.
  let inputMode='pointer',pointerAt=null,padAnchor=null,keyboardArmedUntil=0,appliedCard='',padRestoreId='';
  document.documentElement.dataset.omniInput=inputMode;
  const setText=(node,value)=>{value=String(value);if(node&&node.textContent!==value)node.textContent=value;};
  const setAttr=(node,name,value)=>{value=String(value);if(node&&node.getAttribute(name)!==value)node.setAttribute(name,value);};
  let toastTimer;
  let ready = false;
  let online = true;
  let routeVersion = 0;
  const draft = {quick:'',saved:''};

  // Route compatibility is private to this copied GUI. No sandbox API is sent.
  function api(path, method = 'GET', body) {
    const request=requestChain.then(()=>{
      if(path==='/api/state'&&method==='GET')return client.state({saved:currentRoute==='library'});
      if(path==='/api/preferences'&&method==='PATCH')return client.setPreferences(body);
      if(path==='/api/saved-links'&&method==='POST')return client.saveLink(body.url);
      if(path.startsWith('/api/saved-links/')&&method==='DELETE')return client.deleteLink(path.slice('/api/saved-links/'.length));
      const action=/^\/api\/downloads\/([a-f0-9]{16})\/cancel$/.exec(path);
      if(action&&method==='POST')return client.cancel(action[1]);
      throw new Error('This action is not supported by the installed worker.');
    });
    requestChain=request.catch(()=>{});return request;
  }

  function toast(message, duration = 3400) {
    const node = $('#toast');
    node.textContent = message;
    node.classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove('visible'), duration);
  }

  function openDialog(id) {
    cancelTransformation();
    const dialog = $('#'+id);
    if (dialog.open) return;
    dialog._returnFocus = document.activeElement;
    dialog.showModal();
    if (id === 'theme-dialog') {
      // Start on the theme in use, so the D-pad begins inside the grid.
      renderThemeGallery();
      const cards=$$('#theme-grid [data-theme-choice]');
      const card=cards.find(node=>node.dataset.themeChoice===theme)||cards[0];
      if(card){card.focus({preventScroll:true});padReveal(card);}
    }
    if (id === 'quality-dialog') { // OMNI_DOWNLOADS_PROBE_V5: start on the chosen quality
      setTimeout(() => { const start=$('#quality-options [aria-pressed="true"]')||$('#quality-options button'); if(start){start.focus({preventScroll:true});padReveal(start);} }, 0);
    }
    if (id === 'add-dialog') {
      $('#download-engine').value = engine;
      $('#download-error').textContent = '';
      updateFormControls();
      renderPickLists(); // OMNI_DOWNLOADS_PICK_V3: with grabbed rows, start on the marked row
      setTimeout(() => { const start=pickStart($('#form-candidates')); (start||$('#download-url')).focus(); if(start)padReveal(start); }, 0);
    }
  }

  $$('dialog').forEach(dialog => {
    dialog.addEventListener('close', () => {
      if (dialog.id==='theme-dialog')appliedCard='';
      if ((dialog.id==='quality-dialog'||!document.querySelector('dialog[open]'))&&dialog._returnFocus?.isConnected) dialog._returnFocus.focus({preventScroll:true});
    });
    dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
  });

  // A card's state: selected (check + border).
  const themeCardState = item => `${item.id===theme?1:0}`;
  function themeCardInner(item, index) {
    return `<div class="theme-art"><span class="theme-type">${String(index+1).padStart(2,'0')} / ${item.type}</span>${emblem(item.symbol)}${item.id === theme ? `<span class="theme-check">${icon('check')}</span>` : ''}</div><div class="theme-label"><strong>${item.name}</strong><small>${item.detail}</small></div>`;
  }
  function themeCard(item, index) {
    return `<button type="button" class="theme-option" data-theme-choice="${item.id}" data-card-state="${themeCardState(item)}" aria-pressed="${item.id === theme}" style="--theme-bg:${item.bg};--theme-color:${item.color}">${themeCardInner(item,index)}</button>`;
  }

  function renderThemeGallery() {
    const grid=$('#theme-grid');
    const shown=themes;
    const cards=[...grid.children];
    if(cards.length===shown.length&&cards.every((node,index)=>node.dataset.themeChoice===shown[index].id)) {
      // Same cards: patch only the ones whose state changed. The button elements
      // stay, so D-pad focus and the pointer's hover are kept and nothing else repaints.
      shown.forEach((item,index)=>{
        const node=cards[index],next=themeCardState(item);
        if(node.dataset.cardState===next)return;
        node.dataset.cardState=next;
        node.setAttribute('aria-pressed',item.id===theme);
        node.classList.toggle('just-applied',item.id===theme&&appliedCard===item.id);
        node.innerHTML=themeCardInner(item,themes.indexOf(item));
      });
    } else {
      grid.innerHTML = shown.map(item=>themeCard(item,themes.indexOf(item))).join('');
    }
  }

  function applyThemeChoice(card) {
    const id=card.dataset.themeChoice;
    if(!themes.some(item=>item.id===id))return;
    appliedCard=id;
    // Applies at once; the picker stays open so the new look is visible right away.
    changeTheme(id);
    const same=$$('#theme-grid [data-theme-choice]').find(node=>node.dataset.themeChoice===id);
    if(same&&document.activeElement!==same&&$('#theme-dialog').open)same.focus({preventScroll:true});
  }

  async function changeTheme(id, save = true) {
    const selected = themes.find(item => item.id === id);
    if (!selected) return;
    cancelTransformation();
    uEnter = save && id === 'bloom' && theme !== 'bloom';
    theme = id;
    document.body.dataset.theme = id;
    $('meta[name=theme-color]').content = selected.bg;
    $('#universe-title').textContent = selected.name;
    $('#universe-number').textContent = `${String(themes.indexOf(selected)+1).padStart(2,'0')} / ${themes.length}`;
    $('#theme-total').textContent = `${themes.length} universes. One place for everything.`;
    $('#universe-description').textContent = selected.description;
    $('#universe-symbol').innerHTML = emblem(selected.symbol);
    if ($('#hero-theme-symbol')) $('#hero-theme-symbol').innerHTML = emblem(selected.symbol);
    $('#navigation-hint').innerHTML = glyphText(selected.hint);
    const eyebrow=$('.page-top .eyebrow');
    if(eyebrow)eyebrow.innerHTML=`<span class="status-dot"></span> YOUR DOWNLOAD STUDIO`;
    const dateLabel=$('.date-label');
    if(dateLabel)dateLabel.innerHTML=icon('spark')+'A good day to discover';
    previewIndex = routeIds.indexOf(currentRoute);
    renderNavigation();
    renderThemeGallery();
    if (save) {
      try { await api('/api/preferences','PATCH',{theme:id}); toast(`${selected.name}. A fresh way around.`,1600); }
      catch (error) { toast('Your theme is active. Saving it in this browser was unavailable.'); }
    }
  }

  function routeAttributes(route, index) {
    return `type="button" data-route="${route.id}" data-index="${index}" class="${route.id === currentRoute ? 'is-current' : ''}" ${route.id === currentRoute ? 'aria-current="page"' : ''}`;
  }

  function commandOptions(query) {
    const filtered = routes.filter(route => route.label.toLowerCase().includes(query.toLowerCase()));
    return filtered.length ? filtered.map(route=>`<button ${routeAttributes(route,routeIds.indexOf(route.id))}>${icon(route.icon)}<span>${route.label}</span><kbd>↵</kbd></button>`).join('') : '<p class="no-command">No destination yet. Try “Queue” or “Saved”.</p>';
  }

  function renderNavigation(query = '') {
    const nav = $('#navigation');
    nav.dataset.pattern = themes.find(item => item.id === theme).symbol;
    if (UNIVERSE_SYMBOLS.includes(theme)) {
      const band=['relay','loom','kinetic'].includes(theme),enter=theme==='bloom'&&uEnter;uEnter=false;
      nav.innerHTML=`<div class="u-nav u-${theme}${band?' u-band':''}${enter?' u-enter':''}">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}>${theme==='relay'?'<span class="u-socket" aria-hidden="true"></span>':''}${theme==='kinetic'?'<i class="u-cord" aria-hidden="true"></i>':''}${band?'':`<span class="u-num">0${index+1}</span>`}<span>${route.label}</span>${band?'':'<span class="u-arrow" aria-hidden="true">↗</span>'}</button>`).join('')}</div>`;
    } else if (theme === 'aurora') {
      nav.innerHTML = `<div class="stack-nav">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}>${icon(route.icon)}<span>${route.label}</span><span class="route-number">0${index+1}</span></button>`).join('')}</div>`;
    } else if (theme === 'cosmic') {
      nav.innerHTML = `<div class="orbit-map"><div class="orbit-path"></div>${routes.map((route,index)=>`<button ${routeAttributes(route,index).replace('class="','class="orbit-node ')}><span class="planet">${icon(route.icon)}</span><span>${route.label}</span></button>`).join('')}</div>`;
    } else if (theme === 'arcade') {
      nav.innerHTML = `<div class="arcade-controls"><div class="arcade-pad" aria-label="Direction pad"><button type="button" id="arcade-up" class="up" aria-label="Previous arcade selection">↑</button><button type="button" id="arcade-left" class="left" aria-label="Move arcade selection left">←</button><button type="button" id="arcade-activate" class="middle" aria-label="Enter selected arcade level">A</button><button type="button" id="arcade-right" class="right" aria-label="Move arcade selection right">→</button><button type="button" id="arcade-down" class="down" aria-label="Next arcade selection">↓</button></div><div class="arcade-menu">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}>${icon(route.icon)}<span>${route.label}</span></button>`).join('')}</div></div>`;
    } else if (theme === 'solstice') {
      nav.innerHTML = `<div class="ribbon-nav" aria-label="Scrollable destination cards">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}><small>CHAPTER 0${index+1}</small>${icon(route.icon)}<strong>${route.label} <span aria-hidden="true">↗</span></strong></button>`).join('')}</div>`;
    } else if (theme === 'metro') {
      nav.innerHTML = `<div class="transit-nav">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}><span class="station-dot">${icon(route.icon)}</span><span class="station-copy"><strong>${route.label}</strong><small>${['Where it all begins','Now arriving','The good-finds line','Your travel log','Make a connection'][index]}</small></span></button>`).join('')}</div><div class="transit-terminal"><span>OMNI LINE · 5 STOPS</span><button type="button" id="station-next" class="icon-button" aria-label="Go to next station">${icon('arrow-right')}</button></div>`;
    } else if (theme === 'sakura') {
      nav.innerHTML = `<div class="book-nav">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}><span>${['I','II','III','IV','V'][index]}</span><span>${route.label}</span>${icon('chevron-right')}</button>`).join('')}</div><div class="page-turner"><button type="button" id="book-prev" class="icon-button" aria-label="Previous chapter">${icon('arrow-left')}</button><span>Chapter ${routeIds.indexOf(currentRoute)+1} of 5</span><button type="button" id="book-next" class="icon-button" aria-label="Next chapter">${icon('arrow-right')}</button></div>`;
    } else if (theme === 'abyss') {
      nav.innerHTML = `<div class="depth-nav">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}><span class="depth-value">${String(index*200).padStart(3,'0')}m</span><span>${route.label}</span></button>`).join('')}</div><div class="depth-scrubber"><label for="depth-range"><span>DIVE CONTROL</span><span id="depth-value">${routeIds.indexOf(currentRoute)*200}m</span></label><input type="range" id="depth-range" min="0" max="4" step="1" value="${routeIds.indexOf(currentRoute)}" aria-label="Navigation depth"></div>`;
    } else if (theme === 'prism') {
      nav.innerHTML = `<div class="command-search">${icon('search')}<input id="command-query" type="search" placeholder="Where would you like to go?" aria-label="Find a destination" autocomplete="off" value="${esc(query)}"><kbd>/</kbd></div><div class="command-list">${commandOptions(query)}</div>`;
    } else if (theme === 'atlas') {
      nav.innerHTML = `<div class="bento-nav">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}>${icon(route.icon)}<small>0${index+1}</small><span>${route.label}</span></button>`).join('')}</div>`;
    } else if (theme === 'cassette') {
      nav.innerHTML = `<div class="tape-nav"><div class="tape-art" aria-hidden="true"><div class="tape-reels"><i></i><i></i></div></div><div class="tape-controls"><button type="button" class="icon-button" id="tape-prev" aria-label="Previous track">${icon('arrow-left')}</button><button type="button" class="icon-button" id="tape-activate" aria-label="Play selected destination">${icon('play')}</button><button type="button" class="icon-button" id="tape-next" aria-label="Next track">${icon('arrow-right')}</button></div><div class="tape-track"><div><span id="tape-selection">0${previewIndex+1} / ${routes[previewIndex].label.toUpperCase()}</span><span>SIDE A · YOUR SPACE</span></div><div class="tape-segments">${routes.map((route,index)=>`<button ${routeAttributes(route,index)}>${route.label}</button>`).join('')}</div><input id="tape-seek" type="range" min="0" max="4" step="1" value="${routeIds.indexOf(currentRoute)}" aria-label="Seek a destination"></div></div>`;
    }
  }

  function preview(delta) {
    previewIndex = (previewIndex+delta+routes.length)%routes.length;
    if (theme === 'arcade') {
      $$('#navigation [data-route]').forEach((node,index)=>node.classList.toggle('is-current',index === previewIndex));
      $('#arcade-activate').setAttribute('aria-label','Enter '+routes[previewIndex].label+' level');
    }
    if (theme === 'cassette') {
      $('#tape-selection').textContent = `0${previewIndex+1} / ${routes[previewIndex].label.toUpperCase()}`;
      $('#tape-activate').setAttribute('aria-label','Play '+routes[previewIndex].label);
      $('#tape-seek').value = previewIndex;
    }
  }

  function cancelTransformation() {
    transformationSequence++;
    clearTimeout(transformationTimer);clearTimeout(transformationEnd);
    if(transformationResolve){transformationResolve(false);transformationResolve=null;}
    document.body.classList.remove('is-transforming');
    $('#omni-transition').dataset.state='idle';
    $('#main-content').classList.remove('omni-page-enter');
  }

  function pageHeader(route, actions='') {
    return `<div class="page-top"><div><span class="eyebrow"><span class="status-dot"></span> YOUR DOWNLOAD STUDIO</span><h1>${route.heading}</h1><p>${route.subtitle}</p></div>${actions || `<span class="date-label">${icon('spark')} A good day to discover</span>`}</div>`;
  }

  function engineChoices() {
    return `<div class="engine-selector" role="group" aria-label="Default download engine"><button type="button" class="engine-choice" id="engine-ytdlp" data-engine="ytdlp" aria-pressed="${engine==='ytdlp'}"><span class="engine-glyph">${icon('play')}</span><span><strong>yt-dlp</strong><small>For video & audio</small></span><i class="chosen-dot"></i></button><button type="button" class="engine-choice" id="engine-jdownloader" data-engine="jdownloader" aria-pressed="${engine==='jdownloader'}"><span class="engine-glyph">${icon('download')}</span><span><strong>JDownloader</strong><small>For files & links</small></span><i class="chosen-dot"></i></button></div>`;
  }

  function launchPage() {
    return `${pageHeader(routes[0])}<section class="hero" aria-labelledby="hero-title"><div class="hero-fallback" aria-hidden="true"></div><div class="hero-art" aria-hidden="true"></div><div class="hero-theme-symbol" id="hero-theme-symbol" aria-hidden="true">${emblem(themes.find(item=>item.id===theme).symbol)}</div><div class="hero-copy"><span class="eyebrow">FROM FOUND TO YOURS</span><h2 id="hero-title">The internet’s full of good.<br>Keep a little of it.</h2><p>Videos, sounds, and everything in between.<br>One link is all it takes to get started.</p><div class="hero-actions"><button type="button" class="primary-button" id="add-link">Add a link ${icon('plus')}</button><button type="button" class="text-button" data-sample="landscape">Run a Demo ${icon('arrow-right')}</button></div></div><span class="hero-caption"><span class="status-dot"></span> YOUR NEXT DISCOVERY AWAITS</span></section>
      <div class="two-columns"><section class="panel" aria-labelledby="quick-heading"><div class="panel-heading"><h2 id="quick-heading">${icon('link')} Got a good link?</h2><span>Let’s keep it.</span></div><form id="quick-form"><label for="quick-url">Paste your video or file URL</label><div class="input-combo">${icon('link')}<input id="quick-url" type="url" required placeholder="https://something-you-love…" autocomplete="url" value="${esc(draft.quick)}"><button class="primary-button" type="submit" aria-label="Start download">${icon('arrow-right')}</button></div><label class="production-demo"><input id="quick-demo" type="checkbox"> Demo only · no media saved</label><label class="uncertain-submission production-demo" hidden><input id="quick-confirm-new" type="checkbox"> I checked the queue/history. Submit again despite possible duplicate after restart.</label><p id="quick-error" class="form-error" role="alert"></p></form><div id="launch-candidates" class="form-candidates" data-pick-target="quick-url" hidden><p class="form-candidates-title">Found on the page · pick one <span>unverified</span></p><div class="form-candidate-rows" role="group" aria-label="Links found on the page"></div></div>${engineChoices()}<p class="helper-line">${icon('check')} Real downloads use the selected engine. Demo is opt-in and writes no media.</p></section>
      <section class="panel" aria-labelledby="inspiration-heading"><div class="panel-heading"><h2 id="inspiration-heading">A little inspiration</h2><span>Try one ↘</span></div><div class="collection-card"><img class="collection-art" src="/assets/landscape.svg" alt="Illustrated green mountain landscape"><div class="collection-copy"><strong>Somewhere, slower.</strong><p>Scenic video · Demo simulation</p></div><button type="button" class="icon-button" data-sample="landscape" aria-label="Try scenic sample">${icon('arrow-right')}</button></div><div class="collection-card"><img class="collection-art" src="/assets/soundwave.svg" alt="Amber audio wave illustration"><div class="collection-copy"><strong>A soundtrack for today.</strong><p>Original audio · Demo simulation</p></div><button type="button" class="icon-button" data-sample="audio" aria-label="Try audio sample">${icon('arrow-right')}</button></div></section></div>
      <section class="panel" aria-labelledby="pipeline-heading"><div class="panel-heading"><h2 id="pipeline-heading">In the pipeline <span class="badge" id="pipeline-count">0</span></h2><button type="button" class="text-button" data-open-route="queue">View all ${icon('arrow-right')}</button></div><div id="job-list" class="job-list"></div><div id="empty-queue" class="empty-queue"><div class="empty-illustration">${icon('download')}</div><div><h3>A little room for something good.</h3><p>Your next download will feel right at home here.</p></div><button type="button" class="secondary-button" data-sample="landscape">Run a Demo</button></div></section>`;
  }

  function queuePage() {
    return `${pageHeader(routes[1],`<button type="button" class="primary-button" id="add-link">${icon('plus')} Add a link</button>`)}<div class="stat-grid"><div class="stat-card">${icon('download')}<strong id="stat-active">0</strong><span>On their way</span></div><div class="stat-card">${icon('clock')}<strong id="stat-queued">0</strong><span>Next in line</span></div><div class="stat-card">${icon('check')}<strong id="stat-completed">0</strong><span>All yours</span></div></div><section class="panel"><div class="panel-heading"><h2>Your collection in motion</h2><button type="button" id="queue-hold" class="secondary-button">Hold waiting queue</button></div><div class="filter-tabs" role="group" aria-label="Filter downloads">${[['all','Everything'],['active','In progress'],['completed','Completed']].map(([value,label])=>`<button type="button" data-filter="${value}" aria-pressed="${jobFilter===value}">${label}</button>`).join('')}</div><div id="job-list" class="job-list"></div><div id="empty-queue" class="view-empty"><div class="empty-illustration">${icon('download')}</div><h2>A fresh start. A world of possibilities.</h2><p>Add something you found, or explore a Demo simulation to see how everything works.</p><button type="button" class="primary-button" data-sample="landscape">Run a Demo ${icon('arrow-right')}</button></div><p class="simulation-note"><span class="status-dot"></span> Holding the queue affects waiting jobs only. Active downloads continue. Demo jobs are marked explicitly.</p></section>`;
  }

  function libraryPage() {
    return `${pageHeader(routes[2])}<section class="panel"><div class="panel-heading"><h2>${icon('heart')} Save a little inspiration</h2><span id="saved-count">0 links</span></div><form id="save-form"><label for="save-url">A link worth coming back to</label><div class="input-combo">${icon('link')}<input id="save-url" type="url" required placeholder="https://your-next-great-find…" value="${esc(draft.saved)}" autocomplete="url"><button type="submit" class="primary-button">Save link ${icon('plus')}</button></div><p id="save-error" class="form-error" role="alert"></p></form><p class="helper-line" id="saved-storage">Loading saved-link storage status.</p><section id="native-candidate" class="panel" hidden><strong id="candidate-heading">Shared page link</strong><p id="candidate-url"></p><p id="candidate-hint"></p><button type="button" class="secondary-button" id="save-candidate">Save page link</button><button type="button" class="secondary-button" id="fill-candidate">Use page link</button><div id="candidate-rows"></div><p id="candidate-wire-note" role="status"></p></section></section><section class="panel"><div class="panel-heading"><h2>Your good finds</h2><span>Kept for later.</span></div><div id="saved-list"></div><div id="saved-empty" class="view-empty"><div class="empty-illustration">${icon('library')}</div><h2>Start a little collection.</h2><p>Save a link above. It’ll be here when the time feels right.</p></div></section>`;
  }

  function activityPage() {
    return `${pageHeader(routes[3])}<div class="stat-grid"><div class="stat-card">${icon('download')}<strong id="stat-total">0</strong><span>Little discoveries</span></div><div class="stat-card">${icon('check')}<strong id="stat-completed">0</strong><span>Reported complete</span></div><div class="stat-card">${icon('library')}<strong id="stat-saved">0</strong><span>Saved for another day</span></div></div><section class="panel"><div class="panel-heading"><h2>Recently in your universe</h2><span>Worker history · bounded to 100 jobs</span></div><div id="activity-list"></div><div id="activity-empty" class="view-empty"><div class="empty-illustration">${icon('activity')}</div><h2>Your story starts here.</h2><p>Downloads and saved links will leave a little trail here. Nothing to catch up on yet.</p><button type="button" class="secondary-button" data-open-route="launch">Find your next download ${icon('arrow-right')}</button></div></section>`;
  }

  function settingsPage() {
    return `${pageHeader(routes[4])}<section class="panel"><div class="panel-heading"><h2>${icon('spark')} Your atmosphere</h2><span>Little changes, big feeling.</span></div><div class="setting-row"><div><strong>A whole new universe</strong><p>${themes.length} looks, ${themes.length} ways to find your way. Your queue and links stay put.</p></div><button type="button" class="secondary-button" data-open-themes>Explore themes ${icon('arrow-right')}</button></div><div class="setting-row"><div><strong>A little less motion</strong><p>Keep things still. Less animation, the same personality.</p></div><label class="switch"><input id="motion-toggle" type="checkbox" aria-label="Reduce motion" ${state.preferences.reduced_motion?'checked':''}><span></span></label></div><div class="setting-row"><div><strong>Controller labels</strong><p>Show Xbox or PlayStation button names. The buttons work the same either way.</p></div><select id="glyph-select" class="glyph-select" aria-label="Controller labels"><option value="xbox" ${glyphSet==='xbox'?'selected':''}>Xbox (A, B, LB, RB)</option><option value="playstation" ${glyphSet==='playstation'?'selected':''}>PlayStation (Cross, Circle, L1, R1)</option></select></div></section><section class="panel"><div class="panel-heading"><h2>${icon('download')} Your go-to engine</h2><span>Change it anytime.</span></div><p class="helper-line">Pick the starting point that suits what you save most.</p>${engineChoices()}<p id="runtime-status" class="helper-line"></p></section><section class="panel"><div class="panel-heading"><h2>Download runtime</h2><span class="badge">Worker connected</span></div><p class="helper-line">Real jobs run on the local worker. Theme and motion preferences stay in this browser. Paste any HTTP(S) link. Your go-to engine tries first; if it can’t take the link, the other engine takes over automatically and the job says which one did. yt-dlp handles single videos as plain files, HLS (.m3u8) and DASH (.mpd), tries the site’s extractor, then its generic page scan, then a direct file download. JDownloader keeps original files. Live streams, playlists, RTMP and DRM-protected media are not downloaded. Availability is reported below.</p><button type="button" class="text-button" data-preview-info>About the download runtime ${icon('arrow-right')}</button></section>`;
  }

  function commitNavigation(id, focus = false) {
    if (!routeIds.includes(id)) return;
    if ($('#quick-url')) draft.quick = $('#quick-url').value;
    if ($('#save-url')) draft.saved = $('#save-url').value;
    currentRoute = id;
    previewIndex = routeIds.indexOf(id);
    history.replaceState({omniRoute:id},'',location.pathname+location.search+(id==='library'?'#view=saved':''));
    routeVersion++;
    renderNavigation();
    $('#main-content').innerHTML = ({launch:launchPage,queue:queuePage,library:libraryPage,activity:activityPage,settings:settingsPage})[id]();
    refreshContent();
    if (focus) { $('h1').tabIndex=-1; $('h1').focus({preventScroll:true}); }
    // A slider moved with the D-pad keeps focus after the page it selected renders.
    if (padRestoreId) { const again=document.getElementById(padRestoreId); padRestoreId=''; if(again&&inputMode==='pad')again.focus({preventScroll:true}); }
  }

  async function navigate(id, focus = false, previewOnly = false) {
    if(!routeIds.includes(id))return;
    const reduce=document.body.classList.contains('reduced-motion') || matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(!ready || reduce || $$('dialog').some(dialog=>dialog.open)) {
      cancelTransformation();
      if(!previewOnly)commitNavigation(id,focus);return;
    }
    cancelTransformation();
    // Flush the idle stage so rapid same-theme requests restart CSS timelines.
    void $('#omni-transition').offsetWidth;
    const sequence=transformationSequence;
    const duration=780;
    $('#transform-destination').textContent=routes.find(route=>route.id===id).label.toUpperCase();
    $('#omni-transition').dataset.effect=theme;
    $('#omni-transition').style.setProperty('--transition-duration',duration+'ms');
    $('#omni-transition').dataset.state='transforming';
    document.body.classList.add('is-transforming');
    return new Promise(resolve=>{
      transformationResolve=resolve;
      transformationTimer=setTimeout(()=>{
        if(sequence!==transformationSequence)return;
        if(!previewOnly){commitNavigation(id,focus);$('#main-content').classList.add('omni-page-enter');}
      },Math.round(duration*.29));
      transformationEnd=setTimeout(()=>{if(sequence===transformationSequence){transformationResolve=null;cancelTransformation();resolve(true);}},duration);
    });
  }

  const size = value => value >= 1024**3 ? (value/1024**3).toFixed(1)+' GB' : value >= 1024**2 ? (value/1024**2).toFixed(1)+' MB' : value >=1024 ? (value/1024).toFixed(0)+' KB' : value+' B';
  const names={queued:'Queued',extracting:'Extracting',downloading:'Downloading',processing:'Processing',cancelling:'Cancelling',completed:'Completed',cancelled:'Cancelled',failed:'Failed',interrupted:'Interrupted · submit again'};
  const activeStatuses=new Set(['queued','extracting','downloading','processing','cancelling']);
  const artForJob=job=>job.kind==='audio'?'soundwave':job.engine==='jdownloader'?'orbital':'landscape';
  function jobButtons(job){
    if(activeStatuses.has(job.status)&&job.status!=='cancelling')return `<button type="button" class="icon-button" data-action="cancel" aria-label="Cancel ${esc(job.title)}">${icon('close')}</button>`;
    return `<span class="badge">${job.status==='completed'?(job.demo?'Demo complete':'Worker complete'):esc(names[job.status]||job.status)}</span>`;
  }

  function newJobNode(job) {
    const node = document.createElement('article');
    node.className = 'job'; node.dataset.jobId = job.id;
    node.innerHTML = `<img class="job-art" src="/assets/${artForJob(job)}.svg" alt=""><div class="job-info"><strong class="job-title"></strong><div class="job-details"><span class="job-engine"></span><span>·</span><span class="status-label"></span><span class="badge job-mode-label"></span></div><div class="job-progress" role="progressbar" aria-label="Reported download progress" aria-valuemin="0" aria-valuemax="100"><span></span></div><div class="job-progress-meta"><span class="job-byte-label"></span><span class="job-percent"></span></div><p class="job-note helper-line" role="status" hidden></p></div><div class="job-controls"></div>`;
    return node;
  }

  function focusJobControl(node) {
    const next=$('.job-controls button:not(:disabled)',node);
    if(next)next.focus({preventScroll:true});
    else {
      node.tabIndex=-1;
      node.setAttribute('aria-label',$('.job-title',node).textContent+' · '+$('.status-label',node).textContent);
      node.focus({preventScroll:true});
    }
  }

  function refreshJobs() {
    const container = $('#job-list');
    if (!container) return;
    let jobs = state.jobs.filter(job => jobFilter==='all' || (jobFilter==='active' ? activeStatuses.has(job.status) : job.status==='completed'));
    if (currentRoute === 'launch') jobs = jobs.slice(0,3);
    const ids = new Set(jobs.map(job=>job.id));
    [...container.children].forEach(node=>{if (!ids.has(node.dataset.jobId)) node.remove();});
    jobs.forEach((job,index)=>{
      let node = [...container.children].find(child=>child.dataset.jobId===job.id);
      if (!node) node = newJobNode(job);
      if (container.children[index] !== node) container.insertBefore(node,container.children[index] || null);
      const statusChanged = node.dataset.status !== job.status;
      node.dataset.status = job.status;
      // Write only what changed: the 700 ms status poll must not relayout every row.
      setText($('.job-title',node), job.title || 'A new discovery');
      if ($('.job-title',node).title !== job.url) $('.job-title',node).title = job.url;
      setText($('.job-engine',node), (job.engine === 'ytdlp' ? 'yt-dlp' : 'JDownloader')+(job.engine_requested&&job.engine_requested!==job.engine?' (auto-switched)':''));
      const noteNode=$('.job-note',node);if(noteNode){setText(noteNode,job.note||'');if(noteNode.hidden!==!job.note)noteNode.hidden=!job.note;}
      setText($('.status-label',node), names[job.status] || job.status);
      const progress = Math.min(100,Math.max(0,Number(job.progress)||0));
      setAttr($('.job-progress',node),'aria-valuenow',Math.round(progress));
      // Progress fill animates with transform (no layout per frame); see styles.css.
      const fill=$('.job-progress span',node),scale=`scaleX(${progress/100})`;
      if (fill.style.transform !== scale) fill.style.transform = scale;
      setText($('.job-mode-label',node), job.demo?'Demo · no file':'Real job');
      setText($('.job-byte-label',node), job.error|| (job.demo?'Simulation · no media saved':job.filepath?'Worker output: '+job.filepath:'Transferred size unavailable'));
      setText($('.job-percent',node), job.progress===null?'Progress unavailable':Math.round(progress)+'%');
      if (statusChanged) {
        const controls=$('.job-controls',node),hadFocus=controls.contains(document.activeElement);
        controls.innerHTML = jobButtons(job);
        if(hadFocus)focusJobControl(node);
      }
    });
    if ($('#empty-queue').hidden !== jobs.length>0) $('#empty-queue').hidden = jobs.length>0;
    setText($('#pipeline-count'), state.jobs.length);
    window.OmniJobDetails?.mountRows();
  }

  function refreshSaved() {
    const list = $('#saved-list');
    if (!list) return;
    const signature = state.saved_links.map(link=>link.id+link.url).join('|');
    if (list.dataset.signature !== signature) {
      list.dataset.signature = signature;
      list.innerHTML = state.saved_links.map(link=>`<article class="saved-link" data-saved-id="${esc(link.id)}"><span class="saved-icon">${icon('link')}</span><div class="saved-text"><strong>${esc(link.title || safeHost(link.url))}</strong><small>${esc(link.url)}</small></div><div class="saved-actions"><button type="button" class="secondary-button" data-use-link="${esc(link.id)}">Use link ${icon('arrow-right')}</button><button type="button" class="icon-button" data-delete-link="${esc(link.id)}" aria-label="Delete saved link ${esc(link.title || safeHost(link.url))}">${icon('trash')}</button></div></article>`).join('');
    }
    setText($('#saved-count'), `${state.saved_links.length} ${state.saved_links.length===1?'link':'links'}`);
    $('#saved-empty').hidden = state.saved_links.length>0;
  }

  function refreshActivity() {
    const list = $('#activity-list');
    if (!list) return;
    const entries = [...state.jobs.map(job=>({id:job.id,title:job.title,status:names[job.status] || job.status,created:undefined,icon:job.status==='completed'?'check':'download'})),...state.saved_links.map(link=>({id:link.id,title:link.title || safeHost(link.url),status:'Saved for another day',created:link.created_at,icon:'library'}))].slice(0,20);
    const signature = entries.map(item=>item.id+item.status).join('|');
    if (list.dataset.signature !== signature) {
      list.dataset.signature = signature;
      list.innerHTML = entries.map(item=>`<div class="activity-entry"><span class="activity-dot">${icon(item.icon)}</span><div><strong>${esc(item.title)}</strong><small>${esc(item.status)}</small></div><span>Worker record</span></div>`).join('');
    }
    $('#activity-empty').hidden = entries.length>0;
  }

  function refreshContent() {
    refreshJobs(); refreshSaved(); refreshActivity();
    const stats = {active:state.jobs.filter(job=>['extracting','downloading','processing','cancelling'].includes(job.status)).length, queued:state.jobs.filter(job=>job.status==='queued').length,completed:state.jobs.filter(job=>job.status==='completed').length,total:state.jobs.length,saved:state.saved_links.length};
    Object.entries(stats).forEach(([name,value])=>{ const node = $('#stat-'+name); if(node)setText(node,value); });
    $$('.engine-choice').forEach(node=>setAttr(node,'aria-pressed',node.dataset.engine===engine));
    updateFormControls();
    if($('#queue-hold'))setText($('#queue-hold'),state.queue_paused?'Release waiting queue':'Hold waiting queue');
    renderCandidate();
  }

  function safeHost(url) { try{return new URL(url).hostname;}catch(_){return 'A saved discovery';} }
  function validLink(value){return window.OmniProductionApi.validUrl(value);}
  function updateFormControls(){
    const selected=$('#download-engine').value;
    const kind=$('#download-kind');
    if(selected==='jdownloader')kind.value='file';
    kind.disabled=selected==='jdownloader';
    [...kind.options].forEach(option=>{option.disabled=selected==='ytdlp'&&option.value==='file';});
    if(selected==='ytdlp'&&kind.value==='file')kind.value='video';
    const caps=state.capabilities||{};
    for(const [formId,choice,demoId]of[['download-form',selected,'download-demo'],['quick-form',engine,'quick-demo']]){
      const form=$('#'+formId);if(!form)continue;
      // Either engine can take a real job: the worker tries the chosen one first, then switches automatically.
      const allowed=!!$('#'+demoId)?.checked||caps[choice]===true||caps[choice==='ytdlp'?'jdownloader':'ytdlp']===true;
      $('button[type=submit]',form).disabled=!allowed||form.getAttribute('aria-busy')==='true';
    }
    const status=$('#runtime-status');
    if(status)setText(status,`yt-dlp: ${caps.ytdlp?'available':'unavailable'} · JDownloader: ${caps.jdownloader_ready?'ready':caps.jdownloader?'can start on explicit download':'unavailable'} · ${caps.jdownloader_status||'Waiting for worker status'}`);
    const savedSubmit=$('#save-form button[type=submit]');if(savedSubmit)savedSubmit.disabled=state.saved_writable!==true;
    $$('#saved-list [data-delete-link]').forEach(node=>{node.disabled=state.saved_writable!==true;});
    const storage=$('#saved-storage');if(storage)setText(storage,state.saved_error|| (state.saved_persistent?'Saved links persist on this device.':'Saved links are for this worker session.'));
  }

  async function loadState() {
    state = await api('/api/state');
    // The local host spells this engine "yt-dlp"; the GUI uses the stable
    // internal ID shared with Omni. Keep that boundary explicit in both ways.
    state.jobs = state.jobs.map(job => ({...job,engine:job.engine==='yt-dlp'?'ytdlp':job.engine}));
    window.dispatchEvent(new CustomEvent('omni:state',{detail:{jobs:state.jobs,saved_links:state.saved_links}}));
    refreshContent();
    if (!online) { online = true; toast('You’re connected again. Right where you left off.'); }
  }

  async function addDownload(url,selectedEngine,kind,title,demo=false){
    if(!validLink(url))throw new Error('Use a complete HTTP(S) source without credentials or whitespace.');
    if(!demo&&state.capabilities?.ytdlp!==true&&state.capabilities?.jdownloader!==true)throw new Error('No download engine is available. Reconnect or explicitly choose Demo.');
    if(selectedEngine==='jdownloader'&&kind!=='file'&&!demo)throw new Error('JDownloader currently supports original file mode.');
    const confirmation=$('#'+(document.querySelector('#add-dialog[open]')?'download':'quick')+'-confirm-new');
    // OMNI_DOWNLOADS_PROBE_V5: the chosen quality (yt-dlp only) and the grabbing page's origin as Referer.
    const choice=selectedEngine==='ytdlp'?qualityChoices.get(url)?.quality||null:null;
    if(choice?.audio_only)kind='audio';
    const referer=probeOn()&&pickRows().some(row=>row.url===url)?pageOrigin():null;
    const result=await client.createJob({url,engine:selectedEngine,demo,audio:selectedEngine==='ytdlp'&&kind==='audio',quality:choice,referer},{confirmNewAfterRestart:confirmation?.checked===true});
    $$('.uncertain-submission').forEach(node=>{node.hidden=true;$('input',node).checked=false;});
    try{await loadState();}catch(_){toast('Submission accepted. Reconnect to check its status; do not resubmit.');}
    await navigate('queue');
    const other=selectedEngine==='ytdlp'?'JDownloader':'yt-dlp',first=selectedEngine==='ytdlp'?'yt-dlp':'JDownloader';
    toast(result.demo?'Demo queued. No media will be saved.':`Download accepted. ${first} goes first; ${other} takes over automatically if needed.`);
  }

  function setEngine(value) {
    if (!['ytdlp','jdownloader'].includes(value)) return;
    engine = value;
    try { localStorage.setItem('omni.themeLab.engine',value); } catch (_) {}
    $('#download-engine').value = value;
    refreshContent();
  }

  document.addEventListener('click',event=>{if(event.target.closest('.skip-link')){event.preventDefault();$('#main-content').focus();}});
  document.addEventListener('click', async event => {
    const target = event.target.closest('button,a[data-open-route]');
    if (!target) return;
    if(target.id==='queue-hold'){target.disabled=true;try{await client.setQueuePaused(!state.queue_paused);await loadState();toast(state.queue_paused?'Waiting queue held. Active downloads continue.':'Waiting queue released.');}catch(error){toast(error.message);}finally{if(target.isConnected)target.disabled=false;}return;}
    if (target.dataset.closeDialog) return $('#'+target.dataset.closeDialog).close();
    if (target.id === 'theme-toggle' || target.hasAttribute('data-open-themes')) return openDialog('theme-dialog');
    if (target.id === 'preview-info' || target.hasAttribute('data-preview-info')) return openDialog('info-dialog');
    if (target.dataset.themeChoice) return applyThemeChoice(target);
    if (target.dataset.route) return navigate(target.dataset.route,true);
    if (target.dataset.openRoute){event.preventDefault();return navigate(target.dataset.openRoute,true);}
    if (target.id === 'add-link') return openDialog('add-dialog');
    if (target.dataset.engine) return setEngine(target.dataset.engine);
    if (['arcade-left','arcade-up','tape-prev'].includes(target.id)) return preview(-1);
    if (['arcade-right','arcade-down','tape-next'].includes(target.id)) return preview(1);
    if (['arcade-activate','tape-activate'].includes(target.id)) return navigate(routeIds[previewIndex],true);
    if (['book-prev','book-next','station-next'].includes(target.id)) return navigate(routeIds[(routeIds.indexOf(currentRoute)+(target.id==='book-prev'?-1:1)+routes.length)%routes.length],true);
    if (target.dataset.filter) {
      jobFilter = target.dataset.filter;
      $$('#main-content [data-filter]').forEach(node=>node.setAttribute('aria-pressed',node.dataset.filter===jobFilter));
      return refreshJobs();
    }
    if (target.dataset.sample) {
      target.disabled=true;
      try { const audio = target.dataset.sample==='audio'; await addDownload(`https://preview.example.invalid/${audio?'soundtrack.ogg':'somewhere-slower.mp4'}`,engine,engine==='jdownloader'?'file':audio?'audio':'video',undefined,true); }
      catch(error){toast(error.message);} finally{if(target.isConnected)target.disabled=false;}
      return;
    }
    if (target.dataset.action) {
      const node=target.closest('[data-job-id]'),id=node.dataset.jobId;
      // Disabling the focused control blurs it in Edge. Remember intent first,
      // and yield to any focus move the user makes while the request is pending.
      const ownedFocus=document.activeElement===target;
      let focusMoved=false;
      const noteFocusMove=()=>{focusMoved=true;};
      target.disabled=true;
      document.addEventListener('focusin',noteFocusMove);
      try { await api(`/api/downloads/${encodeURIComponent(id)}/${target.dataset.action}`,'POST',{}); await loadState(); const messages={cancel:'Cancellation requested. The worker will report its final state.'};toast(messages[target.dataset.action]); }
      catch(error){toast(error.message);} finally{
        document.removeEventListener('focusin',noteFocusMove);
        if(target.isConnected)target.disabled=false;
        if(ownedFocus&&!focusMoved&&node.isConnected&&(document.activeElement===document.body||document.activeElement===target)) {
          if(target.isConnected)target.focus({preventScroll:true});
          else focusJobControl(node);
        }
      }
      return;
    }
    if (target.dataset.useLink) {
      const link = state.saved_links.find(item=>item.id===target.dataset.useLink);
      if(link){$('#download-url').value=link.url;openDialog('add-dialog');}
      return;
    }
    if (target.dataset.deleteLink) {
      target.disabled=true;
      try {await api('/api/saved-links/'+encodeURIComponent(target.dataset.deleteLink),'DELETE');await loadState();toast('Link removed from this collection.');}
      catch(error){toast(error.message);}finally{if(target.isConnected)target.disabled=false;}
    }
  });

  window.addEventListener('omni:navigate',event=>{
    if(!routeIds.includes(event.detail?.route))return;
    $$('dialog').filter(dialog=>dialog.open).forEach(dialog=>dialog.close());
    navigate(event.detail.route,true);
  });
  window.addEventListener('omni:collection',()=>{$$('dialog').filter(dialog=>dialog.open).forEach(dialog=>dialog.close());openDialog('theme-dialog');});

  window.addEventListener('omni:overlay-open',cancelTransformation);
  const osMotionPreference=matchMedia('(prefers-reduced-motion: reduce)');
  const onOsMotionChange=event=>{if(event.matches)cancelTransformation();};
  if(typeof osMotionPreference.addEventListener==='function')osMotionPreference.addEventListener('change',onOsMotionChange);
  else if(typeof osMotionPreference.addListener==='function')osMotionPreference.addListener(onOsMotionChange);
  let pendingNavigatorDraft=null;
  window.OmniNavigatorHost=Object.freeze({
    async setTheme(id) {
      if(typeof id!=='string'||!themes.some(item=>item.id===id))return {ok:false,reason:'invalid'};
      $$('dialog').filter(dialog=>dialog.open).forEach(dialog=>dialog.close());
      const saving=changeTheme(id);
      const heading=$('.page-top h1');
      if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}
      await saving;
      return {ok:true};
    },
    prepareLink(value,options={}) {
      if(typeof value!=='string')return {ok:false,reason:'invalid'};
      const url=value.trim();
      if(!window.OmniLinkTools?.normalizeUrl(url).ok)return {ok:false,reason:'invalid'};
      const input=$('#download-url'),existing=input.value;
      const confirmed=options?.replaceDraft===true&&
        pendingNavigatorDraft?.token===options.confirmationToken&&
        pendingNavigatorDraft?.draft===existing&&pendingNavigatorDraft?.url===url;
      if(existing.trim()&&existing.trim()!==url&&!confirmed) {
        pendingNavigatorDraft={token:crypto.randomUUID(),draft:existing,url};
        return {ok:false,reason:'draft-exists',confirmationToken:pendingNavigatorDraft.token};
      }
      pendingNavigatorDraft=null;
      $$('dialog').filter(dialog=>dialog.open).forEach(dialog=>dialog.close());
      input.value=url;
      openDialog('add-dialog');
      return {ok:true};
    }
  });

  document.addEventListener('submit',async event=>{
    const form = event.target;
    if (!['quick-form','download-form','save-form'].includes(form.id)) return;
    event.preventDefault();
    const submit = $('button[type=submit]',form); if(submit.disabled)return;
    submit.disabled=true;form.setAttribute('aria-busy','true');
    const errorNode = $('#'+({ 'quick-form':'quick-error','download-form':'download-error','save-form':'save-error'}[form.id]));
    errorNode.textContent='';
    try {
      if (form.id==='save-form') {
        const url=$('#save-url').value.trim();
        if(!validLink(url))throw new Error('Use a complete http:// or https:// link, without sign-in details.');
        const result=await api('/api/saved-links','POST',{url});
        draft.saved='';$('#save-url').value='';await loadState();toast(!result.present?'This replay refers to a removed link. Save again to create a new entry.':result.created?'Link saved.':'Link already saved.');
      } else if (form.id==='download-form') {
        await addDownload($('#download-url').value.trim(),$('#download-engine').value,$('#download-kind').value,undefined,$('#download-demo').checked);
        $('#add-dialog').close();$('#download-url').value='';
        $('h1').tabIndex=-1;$('h1').focus({preventScroll:true});
      } else {
        await addDownload($('#quick-url').value.trim(),engine,engine==='jdownloader'?'file':'video',undefined,$('#quick-demo').checked);draft.quick='';
      }
    } catch(error){errorNode.textContent=error.message;if(error.requiresNewSubmissionConfirmation){const warning=$('.uncertain-submission',form);if(warning)warning.hidden=false;}} finally{form.removeAttribute('aria-busy');updateFormControls();}
  });

  document.addEventListener('input',event=>{
    const target=event.target;
    if(target.id==='quick-url')draft.quick=target.value;
    if(target.id==='quick-url'||target.id==='download-url')renderPickLists(); // OMNI_DOWNLOADS_PICK_V3
    if(target.id==='save-url')draft.saved=target.value;
    if(target.id==='command-query') {
      $('.command-list').innerHTML = commandOptions(target.value);
    }
    if(target.id==='depth-range')$('#depth-value').textContent=(Number(target.value)*200)+'m';
  });

  document.addEventListener('focusin',event=>{
    const routeButton=event.target.closest('#navigation [data-route]');
    if(routeButton && ['arcade','cassette'].includes(theme)) {
      previewIndex=Number(routeButton.dataset.index);
      preview(0);
    }
  });

  document.addEventListener('change',async event=>{
    const target=event.target;
    if(target.id==='glyph-select'){glyphSet=target.value==='playstation'?'playstation':'xbox';try{localStorage.setItem('omni.glyphs',glyphSet);}catch(_){}applyGlyphs();const shown=themes.find(item=>item.id===theme);if(shown)$('#navigation-hint').innerHTML=glyphText(shown.hint);toast(glyphSet==='xbox'?'Xbox button labels.':'PlayStation button labels.',1400);return;}
    if(['download-engine','download-demo','quick-demo'].includes(target.id)){updateFormControls();return;}
    if(['depth-range','tape-seek'].includes(target.id))return navigate(routeIds[Number(target.value)]);
    if(target.id==='motion-toggle') {
      cancelTransformation();
      document.body.classList.toggle('reduced-motion',target.checked);
      try {await api('/api/preferences','PATCH',{reduced_motion:target.checked});state.preferences.reduced_motion=target.checked;toast(target.checked?'A calmer pace. Motion reduced.':'A little movement, back in your space.');}catch(error){toast(error.message);}
    }
  });

  document.addEventListener('keydown',event=>{
    const editable = event.target.closest('input,textarea,select,[contenteditable]');
    const activeDialog=$$('dialog').find(dialog=>dialog.open);
    const dialogOpen=!!activeDialog;
    if(dialogOpen && event.key==='Tab') {
      const controls=$$('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]',activeDialog).filter(node=>node.getClientRects().length>0);
      const first=controls[0],last=controls.at(-1),focused=document.activeElement;
      if(first && (!activeDialog.contains(focused) || (event.shiftKey && focused===first) || (!event.shiftKey && focused===last))) {
        event.preventDefault();(event.shiftKey?last:first).focus();
      }
      return;
    }
    if(dialogOpen && !editable && /^Arrow(Up|Down|Left|Right)$/.test(event.key) && !event.altKey && !event.ctrlKey && !event.metaKey) {
      // Keyboard arrows in a dialog use the same focus movement as the D-pad.
      event.preventDefault();setInputMode('pad');padMove(event.key.slice(5).toLowerCase(),topModal());return;
    }
    if(event.key==='Escape' && theme==='prism' && event.target.id==='command-query') {renderNavigation();$('#command-query').focus();event.preventDefault();return;}
    if(dialogOpen)return;
    if((event.key==='/' || ((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k')) && theme==='prism' && !editable){event.preventDefault();$('#command-query').focus();return;}
    if(editable) {
      if(event.target.id==='command-query' && event.key==='Enter') {const first=$('#navigation [data-route]');if(first){event.preventDefault();navigate(first.dataset.route,true);}}
      if(event.target.id==='command-query' && event.key==='ArrowDown') {event.preventDefault();$('#navigation [data-route]')?.focus();}
      return;
    }
    if(event.key.toLowerCase()==='t' && !event.ctrlKey && !event.metaKey && !event.altKey){event.preventDefault();openDialog('theme-dialog');return;}
    if(event.altKey && /^[1-5]$/.test(event.key)){event.preventDefault();navigate(routeIds[Number(event.key)-1],true);return;}
    if(theme==='sakura' && ['PageDown','PageUp'].includes(event.key)){event.preventDefault();navigate(routeIds[(routeIds.indexOf(currentRoute)+(event.key==='PageDown'?1:-1)+5)%5]);return;}
    if(event.target.closest('#navigation')) {
      if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) {
        event.preventDefault();
        const delta=['ArrowLeft','ArrowUp'].includes(event.key)?-1:1;
        if(['arcade','cassette'].includes(theme))return preview(delta);
        const buttons=$$('#navigation [data-route]');
        const at=buttons.indexOf(event.target.closest('[data-route]'));
        buttons[(at+delta+buttons.length)%buttons.length]?.focus();
      }
      if(event.key==='Enter' && ['arcade','cassette'].includes(theme) && (event.target.dataset.route || ['arcade-activate','tape-activate'].includes(event.target.id))) {event.preventDefault();navigate(routeIds[previewIndex]);}
    }
  });

  function clearCandidates(){candidateEpoch++;candidateLink='';candidateDetected=false;candidateSnapshot=null;candidateWireError='';savingCandidate=false;renderCandidate();}
  // ---- OMNI_DOWNLOADS_PICK_V3: the grabbed candidate rows on the form view too --------------
  // Same rows as the Saved panel (validated by OmniCandidateWire), shown under the add-link URL
  // field and under the Launch page's quick link. Cross / click on a row puts its URL into that
  // field; the row matching the field is marked (the engine prefills the top row). Text only.
  // ---- OMNI_DOWNLOADS_PROBE_V5: every grabbed link is checked by the worker (real type, qualities, size) ----
  // The worker reads only the start of each link (or its manifest) from public hosts; DRM is reported, never bypassed.
  const probes=new Map(); // url -> {state:'checking'|'done', result, tries, deep}
  const probeQueue=[];let probeActive=0,siteActive=0;
  const qualityChoices=new Map(); // url -> {quality, label}
  function probeOn(){return state?.capabilities?.probe===true;}
  function pageOrigin(){const page=candidateSnapshot?.source||candidateLink;try{return page&&validLink(page)?new URL(page).origin+'/':null;}catch(_){return null;}}
  function probeResult(url){const entry=probes.get(url);return entry?.state==='done'?entry.result:null;}
  function requestProbes(rows){
    if(!probeOn())return;
    for(const row of rows){if(probes.has(row.url)||!validLink(row.url))continue;probes.set(row.url,{state:'checking',tries:0,deep:row.kind==='source-page'});probeQueue.push(row.url);}
    pumpProbes();
  }
  function pumpProbes(){
    for(let index=0;index<probeQueue.length;){
      const url=probeQueue[index],entry=probes.get(url);
      if(!entry){probeQueue.splice(index,1);continue;}
      if(entry.deep?siteActive>=1:probeActive>=3){index++;continue;}
      probeQueue.splice(index,1);
      if(entry.deep)siteActive++;else probeActive++;
      client.probe(url,pageOrigin(),entry.deep).then(result=>{
        if(['slow','busy'].includes(result.status)&&entry.tries<5){entry.tries++;entry.result=result;setTimeout(()=>{probeQueue.push(url);pumpProbes();},result.status==='slow'?2500:4000);}
        else{entry.state='done';entry.result=result;}
      },()=>{entry.state='done';entry.result={status:'error',ok:false,message:'This link could not be checked.',variants:[],audio_tracks:[],subtitles:[]};})
      .finally(()=>{if(entry.deep)siteActive--;else probeActive--;renderCandidate();pumpProbes();});
    }
  }
  function fmtBytes(value){if(!value)return '';const units=['B','KB','MB','GB','TB'];let n=value,i=0;while(n>=1000&&i<4){n/=1000;i++;}return (n>=100||i===0?Math.round(n):n.toFixed(1))+' '+units[i];}
  function fmtTime(seconds){if(!seconds)return '';const s=Math.round(seconds),h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return h?`${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`:`${m}:${String(x).padStart(2,'0')}`;}
  function qualityName(v){if(!v)return '';if(v.height)return v.height+'p'+(v.fps&&v.fps>30?v.fps:'');return '';}
  function sizeText(value,estimated){return value?(estimated?'~':'')+fmtBytes(value):'';}
  function probeBadge(result){
    if(!result)return '';
    if(result.status!=='ok')return result.message||'This link could not be checked.';
    const video=result.video,best=result.variants[0];
    const quality=result.kind==='file'&&video?.width&&video?.height?`${video.width}×${video.height}`:qualityName(best||video);
    const codecs=[best?.vcodec||video?.vcodec,best?.acodec||result.audio?.codec].filter(Boolean).join('/');
    return [result.container||result.kind.toUpperCase(),quality,codecs,fmtTime(result.duration),sizeText(result.size,result.size_estimated)].filter(Boolean).join(' · ');
  }
  function probeDetail(result){
    if(!result||result.status!=='ok')return '';
    const parts=[];
    if(result.title)parts.push(result.title);
    if(result.variants.length>1)parts.push(result.variants.length+glyphText(' qualities · {cross} to choose'));
    if(result.audio_tracks.length>1)parts.push('audio: '+result.audio_tracks.map(t=>t.name||t.lang).filter(Boolean).slice(0,4).join(', '));
    if(result.subtitles.length)parts.push('subtitles: '+result.subtitles.map(t=>t.lang||t.name).filter(Boolean).slice(0,4).join(', '));
    if(result.encrypted==='aes-128')parts.push('standard encryption, downloadable');
    if(!result.video&&result.audio&&!result.variants.length)parts.push('audio only');
    return parts.join(' · ')||'Checked';
  }
  function probeSort(rows){
    const rank=(row,index)=>{const r=probeResult(row.url);if(r?.status==='ok'){const v=r.variants[0]||r.video;return [0,-((v?.height||0)*1000+(v?.fps||0)),index];}return [r?2:1,0,index];};
    return rows.map((row,index)=>({row,key:rank(row,index)})).sort((a,b)=>a.key[0]-b.key[0]||a.key[1]-b.key[1]||a.key[2]-b.key[2]).map(item=>item.row);
  }
  function hasChoices(result){return !!result&&result.status==='ok'&&(result.variants.filter(v=>v.height).length>1||result.audio_tracks.length>1);}
  function pickRows(){
    let rows=(candidateSnapshot?.rows||[]).map(row=>({url:row.url,kind:row.kind,confidence:row.confidence,evidence:row.evidence}));
    if(candidateLink&&!rows.some(row=>row.url===candidateLink))rows.push({url:candidateLink,kind:'source-page',confidence:'Low',evidence:['shared page']});
    if(probeOn()){requestProbes(rows);rows=probeSort(rows);}
    return rows;
  }
  function renderPickList(panel){
    if(!panel)return;
    const field=document.getElementById(panel.dataset.pickTarget),list=panel.querySelector('.form-candidate-rows');
    const rows=candidateSnapshot?pickRows():[];
    panel.hidden=!field||!rows.length;
    const checking=probeOn();
    const signature=JSON.stringify(rows.map(row=>[row,probes.get(row.url)?.state||'',probes.get(row.url)?.result?.status||'']));
    if(list.dataset.signature!==signature){
      const focusedUrl=list.contains(document.activeElement)?document.activeElement.dataset.pickUrl:null;
      list.dataset.signature=signature;list.replaceChildren();
      for(const [index,row]of rows.entries()){
        const button=document.createElement('button');button.type='button';button.className='candidate-pick';button.dataset.pickIndex=index;button.dataset.pickUrl=row.url;
        const entry=probes.get(row.url),result=probeResult(row.url);
        const heading=document.createElement('strong');
        const url=document.createElement('span');url.className='candidate-pick-url';url.textContent=row.url;
        const evidence=document.createElement('small');
        if(checking&&entry){ // OMNI_DOWNLOADS_PROBE_V5
          button.dataset.probe=result?result.status:'checking';
          heading.textContent=(row.kind==='source-page'?'Page link · ':'')+(result?probeBadge(result):entry.result?.status==='slow'?'Still checking the site…':'Checking…');
          evidence.textContent=result?(result.status==='ok'?probeDetail(result):'Not downloadable as it is'):row.evidence.join(', ');
        } else {
          heading.textContent=row.kind==='source-page'?'Page link':`${row.kind} · ${row.confidence}`;
          evidence.textContent=row.evidence.join(', ');
        }
        button.append(heading,url,evidence);list.append(button);
      }
      const again=focusedUrl&&[...list.children].find(node=>node.dataset.pickUrl===focusedUrl);
      if(again)again.focus({preventScroll:true});
    }
    const label=panel.querySelector('.form-candidates-title span');
    if(label)setText(label,!checking?'unverified':rows.some(row=>!probeResult(row.url))?'checking…':'checked');
    markPicked(panel);
    renderQualityNote(panel);
  }
  function markPicked(panel){
    const field=document.getElementById(panel.dataset.pickTarget);if(!field)return;
    const value=field.value.trim(),rows=pickRows();
    panel.querySelectorAll('.candidate-pick').forEach(button=>setAttr(button,'aria-pressed',rows[Number(button.dataset.pickIndex)]?.url===value));
  }
  function renderPickLists(){renderPickList($('#form-candidates'));renderPickList($('#launch-candidates'));}
  // The field may be replaced only when it is empty or still holds a suggestion (never a typed draft).
  function pickInto(panel,key){
    const rows=pickRows(),field=document.getElementById(panel.dataset.pickTarget);
    const row=typeof key==='string'?rows.find(item=>item.url===key):rows[key];
    if(!field||!row||!validLink(row.url))return false;
    const current=field.value.trim();
    if(current&&current!==row.url&&!rows.some(item=>item.url===current)){toast('Your draft is kept. Clear it before using a suggested link.');return true;}
    field.value=row.url;
    if(field.id==='quick-url')draft.quick=row.url;
    field.dispatchEvent(new Event('input',{bubbles:true}));
    markPicked(panel);renderQualityNote(panel);
    const result=probeResult(row.url); // OMNI_DOWNLOADS_PROBE_V5
    if(!probeOn())toast('Link chosen. It is unverified until a download engine takes it.',1800);
    else if(hasChoices(result))openQuality(row.url);
    else if(result&&result.status!=='ok')toast(result.message||'This link may not download.',2600);
    else toast(result?'Link chosen: '+probeBadge(result):'Link chosen. Still checking it.',2200);
    return true;
  }
  // ---- OMNI_DOWNLOADS_PROBE_V5: quality picker (Best / each resolution / audio only; audio language) ----
  let qualityUrl='';
  function qualityLabel(url){
    const result=probeResult(url),choice=qualityChoices.get(url);
    if(choice)return choice.label;
    const best=result?.variants[0];
    return 'Best available'+(best?' ('+[qualityName(best),sizeText(best.size||result.size,true)].filter(Boolean).join(' · ')+')':'');
  }
  function renderQualityNote(panel){
    if(!panel)return;
    let note=panel.querySelector('.quality-note');
    const field=document.getElementById(panel.dataset.pickTarget),url=field?.value.trim()||'';
    const show=probeOn()&&hasChoices(probeResult(url));
    if(!show){if(note)note.hidden=true;return;}
    if(!note){note=document.createElement('p');note.className='quality-note';const text=document.createElement('span');const change=document.createElement('button');change.type='button';change.className='secondary-button quality-change';change.textContent='Change quality';note.append(text,change);panel.append(note);}
    note.hidden=false;setText(note.firstChild,'Quality: '+qualityLabel(url));
  }
  function qualityButton(group,key,label,detail,pressed){
    const button=document.createElement('button');button.type='button';button.className='quality-option';button.dataset.qualityGroup=group;button.dataset.qualityKey=key;setAttr(button,'aria-pressed',pressed);
    const name=document.createElement('strong');name.textContent=label;const more=document.createElement('small');more.textContent=detail;button.append(name,more);return button;
  }
  function qualityOptions(result){
    const best=result.variants[0];
    const options=[{key:'best',label:'Best available',detail:[qualityName(best||result.video),[best?.vcodec,best?.acodec].filter(Boolean).join('/'),sizeText(best?.size||result.size,true)].filter(Boolean).join(' · '),quality:null}];
    for(const v of result.variants){if(v.height)options.push({key:`h${v.height}f${v.fps||0}`,label:qualityName(v),detail:[[v.vcodec,v.acodec].filter(Boolean).join('/'),sizeText(v.size,true)].filter(Boolean).join(' · '),quality:{height:v.height,...(v.fps?{fps:v.fps}:{})}});}
    if(result.audio_tracks.length)options.push({key:'audio',label:'Audio only',detail:result.audio_tracks[0].codec||result.audio?.codec||'',quality:{audio_only:true}});
    return options;
  }
  function openQuality(url){
    const result=probeResult(url);if(!hasChoices(result))return;
    qualityUrl=url;
    const choice=qualityChoices.get(url),options=qualityOptions(result),box=$('#quality-options'),langs=$('#quality-langs');
    setText($('#quality-summary'),probeBadge(result));
    box.replaceChildren(...options.map(option=>qualityButton('video',option.key,option.label,option.detail,(choice?.key||'best')===option.key)));
    const tracks=result.audio_tracks.length>1?result.audio_tracks:[];
    langs.hidden=!tracks.length;
    const chosenLang=choice?.lang||(tracks.find(t=>t.default)||tracks[0])?.lang||'';
    langs.replaceChildren(...(tracks.length?[Object.assign(document.createElement('p'),{className:'quality-group-title',textContent:'Audio language'})]:[]),
      ...tracks.map(track=>qualityButton('lang',track.lang,track.name||track.lang||'Audio',[track.lang,track.codec].filter(Boolean).join(' · '),track.lang===chosenLang)));
    openDialog('quality-dialog');
  }
  function applyQuality(){
    const result=probeResult(qualityUrl);if(!result)return $('#quality-dialog').close();
    const picked=$('#quality-options [aria-pressed="true"]'),option=qualityOptions(result).find(item=>item.key===picked?.dataset.qualityKey)||qualityOptions(result)[0];
    const lang=$('#quality-langs').hidden?'':($('#quality-langs [aria-pressed="true"]')?.dataset.qualityKey||'');
    const validLang=/^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8}){0,2}$/.test(lang)?lang:'';
    let quality=option.quality?{...option.quality}:null;
    if(validLang)quality={...(quality||{}),audio_lang:validLang};
    const label=option.label+(option.detail?' ('+option.detail+')':'')+(validLang?' · audio '+validLang:'');
    if(option.key==='best'&&!validLang)qualityChoices.delete(qualityUrl);else qualityChoices.set(qualityUrl,{key:option.key,lang:validLang,quality,label});
    $('#quality-dialog').close();
    renderQualityNote($('#form-candidates'));renderQualityNote($('#launch-candidates'));
    toast('Quality: '+label,2200);
  }
  // Start on the marked row (or the first): the D-pad then walks the list; Cross picks.
  function pickStart(panel){
    if(!panel||panel.hidden)return null;
    return panel.querySelector('.candidate-pick[aria-pressed="true"]')||panel.querySelector('.candidate-pick');
  }
  function renderCandidate(){
    renderPickLists(); // OMNI_DOWNLOADS_PICK_V3
    const panel=$('#native-candidate');if(!panel)return;
    panel.hidden=!candidateLink&&!candidateSnapshot&&!candidateWireError;
    setText($('#candidate-url'),candidateLink);
    setText($('#candidate-hint'),probeOn()?'Each link is checked: its real type, quality and size show as soon as they are known.':candidateDetected?'Browser suggested possible media. Format and downloadability are unverified.':'Shared page link. It may not be directly downloadable.');
    $('#save-candidate').disabled=!candidateLink||savingCandidate||state.saved_writable!==true;
    $('#fill-candidate').disabled=!candidateLink;
    const rows=$('#candidate-rows');
    if(probeOn()&&candidateSnapshot)requestProbes(pickRows()); // OMNI_DOWNLOADS_PROBE_V5
    const signature=JSON.stringify([candidateSnapshot,(candidateSnapshot?.rows||[]).map(row=>probes.get(row.url)?.result?.status||probes.get(row.url)?.state||'')]);
    if(rows.dataset.signature!==signature){
      rows.dataset.signature=signature;rows.replaceChildren();
      for(const [index,row]of(candidateSnapshot?.rows||[]).entries()){
        const card=document.createElement('article');card.className='candidate-row';
        const result=probeOn()?probeResult(row.url):null,entry=probeOn()?probes.get(row.url):null;
        if(entry)card.dataset.probe=result?result.status:'checking';
        const heading=document.createElement('strong');heading.textContent=entry?(result?probeBadge(result):'Checking…'):`${row.kind} · ${row.confidence} evidence hint`;
        const source=document.createElement('p');source.textContent=row.url;
        const evidence=document.createElement('small');evidence.textContent=entry?(result?(result.status==='ok'?probeDetail(result):'Not downloadable as it is'):row.evidence.join(', ')):'Unverified · '+row.evidence.join(', ');
        card.append(heading,source,evidence);
        for(const [action,label]of[['save','Save link'],['fill','Use link']]){const button=document.createElement('button');button.type='button';button.className='secondary-button';button.dataset.candidateAction=action;button.dataset.candidateIndex=index;button.textContent=label;card.append(button);}
        rows.append(card);
      }
    }
    $$('[data-candidate-action="save"]',rows).forEach(button=>{button.disabled=savingCandidate||state.saved_writable!==true;});
    setText($('#candidate-wire-note'),candidateWireError||(candidateSnapshot?(candidateSnapshot.truncated?'Some suggestions were omitted to keep the snapshot bounded. ':'')+(probeOn()?'Checked links show their real type, quality and size. ':'Suggestions are unverified. ')+'Saving keeps a link; Use link fills the form without starting a download.':''));
  }
  async function saveCandidate(value=candidateLink){
    if(!validLink(value)||savingCandidate||state.saved_writable!==true)return;
    const epoch=candidateEpoch;savingCandidate=true;renderCandidate();
    try{const result=await client.saveLink(value);await loadState();if(epoch===candidateEpoch)toast(result.present?(result.created?'Link saved.':'Link already saved.'):'That saved link was removed. Save again to create a new entry.');}catch(error){if(epoch===candidateEpoch)toast(error.message);}finally{if(epoch===candidateEpoch){savingCandidate=false;renderCandidate();}}
  }
  function fillCandidate(value=candidateLink){
    if(!validLink(value))return false;
    const existing=$('#download-url').value.trim();
    if(existing&&existing!==value){toast('Your draft is kept. Clear it before using the suggested link.');return false;}
    $('#download-url').value=value;openDialog('add-dialog');return true;
  }
  function takeNativeLink(){
    const raw=location.hash;
    const bounded=raw.length<=32768;
    const p=new URLSearchParams(bounded?raw.slice(1):'');
    const view=p.get('view')==='saved'?'library':'launch';
    // Source-bearing data is removed synchronously, before parsing or network I/O.
    history.replaceState({omniRoute:view},'',location.pathname+location.search+(view==='library'?'#view=saved':''));
    if(!bounded){clearCandidates();candidateWireError='The media suggestion exceeded its safety limit.';commitNavigation(view);return;}
    if(p.has('candidate')){clearCandidates();candidateLink=validLink(p.get('candidate'))?p.get('candidate'):'';candidateDetected=!!candidateLink&&p.get('detected')==='1';}
    if(p.has('candidates')){
      const parsed=window.OmniCandidateWire.parse(raw);
      if(parsed.ok&&(!p.has('candidate')||candidateLink===parsed.source)){candidateEpoch++;candidateSnapshot=parsed;candidateWireError='';}
      else{candidateSnapshot=null;candidateWireError=parsed.ok?'The candidate source did not match this snapshot.':parsed.message;}
    }
    if(p.has('url')){const value=p.get('url');if(validLink(value)){if(!p.has('candidate'))candidateLink=value;if(!$('#download-url').value.trim())$('#download-url').value=value;else if($('#download-url').value.trim()!==value)toast('Shared link received. Your existing draft was kept.');}else toast('The shared source must be a complete HTTP(S) link without credentials.');}
    commitNavigation(view);
    renderPickLists(); // OMNI_DOWNLOADS_PICK_V3
    if(view==='launch'&&!p.has('url')){const field=$('#quick-url'),top=pickRows()[0];if(field&&!field.value.trim()&&top&&top.kind!=='source-page'&&validLink(top.url)){field.value=top.url;draft.quick=top.url;markPicked($('#launch-candidates'));}} // L1+R1: top row preselected
    if(p.has('url')&&view==='launch')openDialog('add-dialog');
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('#save-candidate'))saveCandidate();
    if(event.target.closest('#fill-candidate'))fillCandidate();
    const pick=event.target.closest('.candidate-pick'); // OMNI_DOWNLOADS_PICK_V3
    if(pick){const panel=pick.closest('.form-candidates');if(panel)pickInto(panel,pick.dataset.pickUrl||Number(pick.dataset.pickIndex));return;}
    const option=event.target.closest('.quality-option'); // OMNI_DOWNLOADS_PROBE_V5
    if(option){$$(`.quality-option[data-quality-group="${option.dataset.qualityGroup}"]`).forEach(node=>setAttr(node,'aria-pressed',node===option));if(option.dataset.qualityGroup==='video'&&$('#quality-langs').hidden)applyQuality();return;}
    if(event.target.closest('#quality-done')){applyQuality();return;}
    const change=event.target.closest('.quality-change');
    if(change){const panel=change.closest('.form-candidates'),field=panel&&document.getElementById(panel.dataset.pickTarget);if(field)openQuality(field.value.trim());return;}
    const button=event.target.closest('[data-candidate-action]');
    if(button){const row=candidateSnapshot?.rows[Number(button.dataset.candidateIndex)];if(!row)return;if(button.dataset.candidateAction==='save')saveCandidate(row.url);else if(button.dataset.candidateAction==='fill')fillCandidate(row.url);}
  });
  // ---- OMNI_DOWNLOADS_PAD_V2: one controller model for every screen and dialog ----------
  // The engine calls omniMediaController with fixed action names; true = the page used the
  // press, false = the engine runs its normal action (Cross clicks under the pointer, D-pad
  // up/down scroll, Triangle opens the keyboard for a focused field, Circle goes back).
  const PAD_DIRECTIONS={'saved.previous':'up','saved.next':'down','saved.left':'left','saved.right':'right'};
  const PAD_POINTER_SLOP=24; // OMNI_DOWNLOADS_NAV_V4: CSS px
  const PAD_FOCUSABLE='button,a[href],input:not([type=hidden]),select,textarea,[tabindex]:not([tabindex="-1"])';
  function setInputMode(mode){if(inputMode===mode)return;inputMode=mode;document.documentElement.dataset.omniInput=mode;}
  function isTextField(node){return !!node&&node.nodeType===1&&(node.matches('textarea,[contenteditable]:not([contenteditable=false])')||node.tagName==='INPUT'&&/^(text|url|search|email|password|tel|number)$/.test(node.type));}
  function topModal(){
    const dialogs=$$('dialog[open]').filter(dialog=>dialog.getClientRects().length&&!dialog.closest('[hidden],[inert]'));
    const focusedModal=document.activeElement?.closest?.('dialog[open]');
    return dialogs.includes(focusedModal)?focusedModal:dialogs.at(-1)||null;
  }
  function padCandidates(modal){
    // Inside a modal only its own controls; otherwise the page outside every dialog.
    const nodes=modal?$$(PAD_FOCUSABLE,modal):$$(PAD_FOCUSABLE).filter(node=>!node.closest('dialog,#omni-transition'));
    return nodes.filter(node=>!node.disabled&&!node.classList.contains('skip-link')&&!node.closest('[hidden],[inert]')&&node.getClientRects().length>0&&getComputedStyle(node).visibility!=='hidden');
  }
  // Nearest control in a direction: rows/columns that overlap the current control win, then the
  // smallest gap. All rects are read in one pass before focus is written (no layout thrash).
  // sameRow: left/right only to controls sharing the row (Done never jumps to the Close X).
  function padNearest(from,nodes,direction,sameRow){
    const vertical=direction==='up'||direction==='down',forward=direction==='down'||direction==='right';
    const fromCross=vertical?(from.left+from.right)/2:(from.top+from.bottom)/2;
    const fromMid=vertical?(from.top+from.bottom)/2:(from.left+from.right)/2;
    let best=null,bestScore=Infinity,loose=null,looseScore=Infinity;
    for(const node of nodes){
      const r=node.getBoundingClientRect();
      const gap=vertical?(forward?r.top-from.bottom:from.top-r.bottom):(forward?r.left-from.right:from.left-r.right);
      const ahead=((vertical?(r.top+r.bottom)/2:(r.left+r.right)/2)-fromMid)*(forward?1:-1);
      const lo=vertical?Math.max(from.left,r.left):Math.max(from.top,r.top),hi=vertical?Math.min(from.right,r.right):Math.min(from.bottom,r.bottom);
      const off=hi>=lo?0:lo-hi,drift=Math.abs((vertical?(r.left+r.right)/2:(r.top+r.bottom)/2)-fromCross);
      if(sameRow&&!vertical&&off>Math.max(from.bottom-from.top,r.height)/2)continue;
      const weight=vertical?2:5;
      if(gap>=-2){const score=Math.max(gap,0)+off*weight+drift*.05;if(score<bestScore){best=node;bestScore=score;}}
      else if(ahead>4){const score=ahead+off*weight+drift*.05;if(score<looseScore){loose=node;looseScore=score;}}
    }
    return best||loose;
  }
  function padStart(nodes,modal){
    if(modal){
      if(modal.id==='theme-dialog'){const card=nodes.find(node=>node.dataset.themeChoice===theme)||nodes.find(node=>node.dataset.themeChoice);if(card)return card;}
      if(modal.id==='add-dialog'){const pick=pickStart($('#form-candidates'));if(pick&&nodes.includes(pick))return pick;} // OMNI_DOWNLOADS_PICK_V3
      return nodes.find(node=>!node.matches('[data-close-dialog]'))||nodes[0];
    }
    if(currentRoute==='library'){const review=nodes.find(node=>node.closest('#native-candidate,#saved-list'));if(review)return review;}
    if(currentRoute==='launch'){const pick=pickStart($('#launch-candidates'));if(pick&&nodes.includes(pick))return pick;} // OMNI_DOWNLOADS_PICK_V3
    const inView=node=>{const r=node.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;};
    const nav=nodes.filter(node=>node.closest('#navigation')&&inView(node));
    return nav.find(node=>node.getAttribute('aria-current')==='page'||node.classList.contains('is-current'))||nav[0]||nodes.find(inView)||nodes[0];
  }
  function padReveal(node){
    // Instant, minimal scroll (no smooth-scroll repaint train on the CPU renderer).
    try{node.scrollIntoView({block:'nearest',inline:'nearest'});}catch(_){node.scrollIntoView(false);}
    // OMNI_DOWNLOADS_NAV_V4: if a scroll box (an open dialog, a list) still clips the control, scroll that box itself.
    for(let box=node.parentElement;box&&box!==document.body&&box!==document.documentElement;box=box.parentElement){
      if(box.scrollHeight<=box.clientHeight+1||!/(auto|scroll)/.test(getComputedStyle(box).overflowY))continue;
      const r=node.getBoundingClientRect(),b=box.getBoundingClientRect();
      if(r.top<b.top)box.scrollTop-=b.top-r.top+8;else if(r.bottom>b.bottom)box.scrollTop+=Math.min(r.bottom-b.bottom+8,r.top-b.top);
    }
  }
  // OMNI_DOWNLOADS_NAV_V4: the box a modal scrolls in (the same one the engine's right stick scrolls).
  function padScroller(modal){return [modal,...modal.querySelectorAll('*')].find(node=>node.scrollHeight>node.clientHeight+1&&/(auto|scroll)/.test(getComputedStyle(node).overflowY))||null;}
  function padFocus(node){
    setInputMode('pad');
    padAnchor=pointerAt?{x:pointerAt.x,y:pointerAt.y}:null; // OMNI_DOWNLOADS_NAV_V4
    node.focus({preventScroll:true});
    padReveal(node);
  }
  function padMove(direction,modal){
    const nodes=padCandidates(modal);
    if(!nodes.length)return !!modal;
    const current=nodes.includes(document.activeElement)?document.activeElement:null;
    let next=null;
    if(!current||inputMode!=='pad'){
      // First press after pointer use (or with nothing focused) shows where focus is.
      const under=inputMode==='pointer'&&pointerAt?document.elementFromPoint(pointerAt.x,pointerAt.y)?.closest(PAD_FOCUSABLE):null;
      next=nodes.includes(under)?under:current||padStart(nodes,modal);
    } else {
      const grid=current.closest('.theme-grid');
      const others=nodes.filter(node=>node!==current);
      if(grid&&(direction==='left'||direction==='right')){
        const cards=nodes.filter(node=>grid.contains(node)),at=cards.indexOf(current);
        next=cards[(at+(direction==='left'?-1:1)+cards.length)%cards.length];
      } else {
        const from=current.getBoundingClientRect(),vertical=direction==='up'||direction==='down';
        // Left/right: same row first; on the page (not in a dialog) any control that way next.
        next=vertical?padNearest(from,others,direction,false):padNearest(from,others,direction,true)||(!modal&&padNearest(from,others,direction,false));
        if(!next&&modal&&(direction==='up'||direction==='down')){
          // OMNI_DOWNLOADS_NAV_V4: a dialog taller than the screen first scrolls to its end, then wraps.
          const box=padScroller(modal),down=direction==='down';
          if(box&&(down?box.scrollHeight-box.clientHeight-box.scrollTop>24:box.scrollTop>24)){box.scrollTop+=(down?1:-1)*Math.max(40,box.clientHeight*.8);return true;}
          // Dialogs wrap top <-> bottom; the page instead lets the engine scroll.
          const edge=direction==='down'?-1e6:1e6;
          next=padNearest({left:from.left,right:from.right,top:edge,bottom:edge},others,direction,false);
        }
      }
    }
    if(!next)return !!modal;
    padFocus(next);return true;
  }
  function stepSelect(node,delta){
    const options=[...node.options].filter(option=>!option.disabled);
    if(options.length<2)return;
    const at=options.findIndex(option=>option.selected);
    options[(at+delta+options.length)%options.length].selected=true;
    node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));
  }
  // Left/right change a focused slider; elsewhere they move
  // focus (a select keeps left/right for moving on; Cross steps through its options).
  function padAdjust(node,direction){
    if((direction!=='left'&&direction!=='right')||inputMode!=='pad'||!node||node.nodeType!==1||node.disabled)return null;
    const delta=direction==='left'?-1:1;
    if(node.tagName==='INPUT'&&node.type==='range'){
      const before=node.value;if(delta<0)node.stepDown();else node.stepUp();
      if(node.value!==before){padRestoreId=node.id||'';node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));}
      return true;
    }
    return null;
  }
  function padChoose(modal){
    if(inputMode!=='pad')return false; // pointer: the engine's native click lands under the pointer
    const nodes=padCandidates(modal),node=document.activeElement;
    if(!nodes.includes(node)){const start=padStart(nodes,modal);if(!start)return false;padFocus(start);return true;}
    if(isTextField(node)){
      // Let the engine's click through so it opens its keyboard, but keep focus on this field:
      // the click it sends lands wherever the pointer is, so swallow that one click.
      keyboardArmedUntil=performance.now()+900;return false;
    }
    if(node.tagName==='SELECT'){stepSelect(node,1);return true;}
    if(node.tagName==='INPUT'&&node.type==='range')return true;
    node.click();return true;
  }
  window.omniMediaController=action=>{
    if(location.origin!=='http://127.0.0.1:8765'||location.pathname!=='/downloads'||location.search||parent!==window||!['','#view=saved'].includes(location.hash))return false;
    if(typeof action!=='string')return false;
    if(action==='candidates.clear'){clearCandidates();return true;}
    const modal=topModal(),focused=document.activeElement,typing=isTextField(focused),direction=PAD_DIRECTIONS[action];
    if(direction){const adjusted=padAdjust(focused,direction);return adjusted!==null?adjusted:padMove(direction,modal);}
    if(action==='saved.choose')return padChoose(modal);
    if(action==='saved.dismiss'){
      // Handle only explicit actions in the current modal; never its backdrop.
      if(modal){modal.close();return true;}
      if(typing)return false;
    }
    // Triangle on a focused field: false, so the engine opens its on-screen keyboard.
    if(modal||typing)return false;
    if(action==='saved.open'){commitNavigation('library',true);loadState().catch(error=>toast(error.message));return true;}
    if(action==='form.prefillCandidate')return fillCandidate();
    if(currentRoute!=='library'||location.hash!=='#view=saved')return false;
    if(action==='saved.dismiss'){clearCandidates();commitNavigation('launch',true);return true;}
    if(action==='saved.saveCandidate'){saveCandidate();return true;}
    return false;
  };
  document.addEventListener('mousedown',event=>{if(performance.now()<keyboardArmedUntil)event.preventDefault();else setInputMode('pointer');},true);
  document.addEventListener('click',event=>{if(performance.now()<keyboardArmedUntil){keyboardArmedUntil=0;event.preventDefault();event.stopImmediatePropagation();}},true);
  document.addEventListener('mousemove',event=>{
    // Only real movement counts: WebKit's synthetic moves after a scroll repeat the position.
    const x=event.clientX,y=event.clientY;
    if(!Number.isFinite(x)||!Number.isFinite(y))return;
    if(pointerAt&&Math.abs(x-pointerAt.x)<3&&Math.abs(y-pointerAt.y)<3)return;
    const known=!!pointerAt;pointerAt={x,y};
    // OMNI_DOWNLOADS_NAV_V4: stick drift and pointer snapping nudge the pointer a few px between D-pad presses;
    // that must not turn every press back into a "show where focus is" press. Pointer use = a real move away
    // from where the pointer was at the last D-pad press.
    if(known&&!(inputMode==='pad'&&padAnchor&&Math.hypot(x-padAnchor.x,y-padAnchor.y)<PAD_POINTER_SLOP))setInputMode('pointer');
  },{passive:true});
  document.addEventListener('keydown',event=>{if(!event.ctrlKey&&!event.metaKey&&!event.altKey)setInputMode('pad');});
  window.addEventListener('hashchange',takeNativeLink);
  window.addEventListener('message',event=>{if(parent===window||event.source!==parent||event.origin!==location.origin||event.data?.type!=='omni-media-section-visibility'||typeof event.data.visible!=='boolean')return;sectionVisible=event.data.visible;if(sectionActive())loadState().catch(()=>{});else cancelTransformation();});
  document.addEventListener('visibilitychange',()=>{if(sectionActive())loadState().catch(()=>{});else cancelTransformation();});
  $('#theme-toggle').addEventListener('click',renderThemeGallery);
  renderThemeGallery();
  applyGlyphs();
  changeTheme('bloom',false);
  takeNativeLink();
  commitNavigation(currentRoute);
  (async()=>{
    try {
      await loadState();
      const savedTheme=themes.some(item=>item.id===state.preferences.theme)?state.preferences.theme:'bloom';
      await changeTheme(savedTheme,false);
      document.body.classList.toggle('reduced-motion',!!state.preferences.reduced_motion);
      ready=true;document.documentElement.dataset.ready='true';
    }catch(error){online=false;toast('Worker unavailable. Your draft stays here.');}
    async function tick(){try{if(sectionActive())await loadState();}catch(error){if(online){online=false;toast('Worker disconnected. Your draft stays here.');}}finally{setTimeout(tick,sectionActive()?700:2200);}}
    setTimeout(tick,800);
  })();
})();
