/* OMNI_DL_LIBRARY_V1: the Library panel on the Queue page. Lists saved files by opaque id (the worker never sends a
   path to act on and never accepts one), plays video/audio in /player, opens PDFs and pictures in the browser, and
   deletes in two steps: a file goes to the trash first; only a file in the trash can be deleted for real.
   OMNI_DL_LIBRARY_SEARCH_V1: search box (name or download title), sort select, type chips and a Show trash toggle.
   The worker pages the listing, so search/sort/filter go to the same token-protected /api/files as query values.
   Sort and chips are remembered in localStorage (this origin only); the search text and the trash view are not. */
(function(){
  'use strict';
  var PAGE=50,ARM_MS=5000,SEARCH_MS=300,STORE='omni-dl-library-view-v1';
  var esc=function(value){return String(value==null?'':value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};
  var icon=function(name){return '<svg class="icon" aria-hidden="true"><use href="/assets/icons.svg#'+name+'"></use></svg>';};
  var size=function(v){return v>=1073741824?(v/1073741824).toFixed(1)+' GB':v>=1048576?(v/1048576).toFixed(1)+' MB':v>=1024?Math.round(v/1024)+' KB':v+' B';};
  var KIND_ICON={video:'video',audio:'music',image:'file',pdf:'file',text:'file',other:'file'};
  var KIND_LABEL={video:'Video',audio:'Audio',image:'Picture',pdf:'PDF',text:'Text',other:'File'};
  var CATS=[['video','Video'],['audio','Audio'],['image','Images'],['document','Documents'],['archive','Archives'],['other','Other']];
  var SORTS=[['newest','Newest'],['oldest','Oldest'],['name','Name'],['size','Size'],['type','Type']];
  var SORT_NOTE={newest:'newest first',oldest:'oldest first',name:'by name',size:'largest first',type:'by type'};
  var view={cats:[],sort:'newest',q:'',area:'files',offset:0},client=null,root=null,toast=function(){},seq=0,completed=null,focusNext=false,searchTimer=0;
  var places=[];   // OMNI_DL_STORAGE_METER_V1: status.places from app.js (notify)
  var catOrder=function(list){return CATS.map(function(c){return c[0];}).filter(function(c){return list.indexOf(c)>=0;});};

  // Remembered choices: only known values survive a read (the store is per origin but still untrusted input).
  (function restore(){
    try{
      var saved=JSON.parse(window.localStorage.getItem(STORE)||'null');
      if(saved&&typeof saved==='object'){
        if(SORTS.some(function(s){return s[0]===saved.sort;}))view.sort=saved.sort;
        if(Array.isArray(saved.cats))view.cats=catOrder(saved.cats);
        if(view.cats.length===CATS.length)view.cats=[];
      }
    }catch(_){}
  })();
  function remember(){try{window.localStorage.setItem(STORE,JSON.stringify({sort:view.sort,cats:view.cats}));}catch(_){}}

  function date(seconds){try{return new Date(seconds*1000).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});}catch(_){return '';}}
  function playable(kind){return kind==='video'||kind==='audio';}
  function openable(kind){return kind==='image'||kind==='pdf'||kind==='text';}
  function filtered(){return view.cats.length>0||view.q.trim()!=='';}

  function chips(){
    return '<button type="button" data-lib-cat="all" aria-pressed="'+(view.cats.length===0)+'">All</button>'+
      CATS.map(function(c){return '<button type="button" data-lib-cat="'+c[0]+'" aria-pressed="'+(view.cats.indexOf(c[0])>=0)+'">'+c[1]+'</button>';}).join('');
  }

  function shell(){
    var trash=view.area==='trash';
    return '<div class="panel-heading"><h2>'+icon('folder')+' '+(trash?'Library trash':'Library')+'</h2><div class="section-actions">'+
      '<button type="button" class="secondary-button lib-trash-toggle" data-lib-area="'+(trash?'files':'trash')+'" aria-pressed="'+trash+'">'+(trash?icon('arrow-left')+' Back to files':icon('trash')+' Show trash')+'</button>'+
      (trash?'':'<button type="button" class="secondary-button" data-lib-largest>'+icon('folder')+' Largest files</button>')+
      '<button type="button" class="icon-button" data-lib-refresh aria-label="Refresh the library" title="Refresh">'+icon('refresh')+'</button></div></div>'+
      '<div class="lib-storage" role="group" aria-label="Storage" hidden></div>'+
      '<div class="lib-tools"><div class="lib-search"><label for="lib-search">Search</label>'+
      '<input type="search" id="lib-search" maxlength="100" autocomplete="off" spellcheck="false" enterkeyhint="search" placeholder="File name or title" value="'+esc(view.q)+'"></div>'+
      '<div class="lib-sort"><label for="lib-sort">Sort</label><select id="lib-sort">'+
      SORTS.map(function(s){return '<option value="'+s[0]+'"'+(view.sort===s[0]?' selected':'')+'>'+s[1]+'</option>';}).join('')+'</select></div></div>'+
      '<div class="filter-tabs lib-chips" role="group" aria-label="Filter the library by type">'+chips()+'</div>'+
      '<p class="helper-line lib-status" role="status"></p><div class="lib-list"></div>'+
      '<div class="lib-pager" hidden><button type="button" class="secondary-button" data-lib-page="-1">'+icon('arrow-left')+' Previous</button><span class="lib-range"></span><button type="button" class="secondary-button" data-lib-page="1">Next '+icon('arrow-right')+'</button></div>';
  }

  function typeLabel(file){
    if(file.kind==='other'&&file.category==='archive')return 'Archive';
    if(file.kind==='other'&&file.category==='document')return 'Document';
    return KIND_LABEL[file.kind]||'File';
  }

  // OMNI_DL_WATCH_V1: thin progress bar / "Watched" tick from the player's page-local store (read once per listing).
  var marks={};
  function readMarks(){try{marks=window.OmniWatch?window.OmniWatch.load(window.localStorage):{};}catch(_){marks={};}}
  function watchMark(file){return view.area==='files'&&playable(file.kind)&&window.OmniWatch?window.OmniWatch.tileHtml(marks[window.OmniWatch.keyFor(file)]):'';}

  function row(file){
    var where=file.place_label+(file.folder?' / '+file.folder:'');
    var meta=[typeLabel(file),size(file.size),date(file.mtime),where].filter(Boolean).join(' · ');
    var actions='';
    if(view.area==='trash'){
      actions='<button type="button" class="secondary-button" data-lib-restore="'+file.id+'">'+icon('refresh')+' Restore</button>'+
        '<button type="button" class="secondary-button lib-danger" data-lib-delete="'+file.id+'" aria-label="Delete '+esc(file.name)+' for good">'+icon('trash')+' Delete for good</button>';
    }else{
      if(playable(file.kind))actions+='<button type="button" class="secondary-button" data-lib-play="'+file.id+'">'+icon('play')+' Play</button>';
      else if(openable(file.kind))actions+='<button type="button" class="secondary-button" data-lib-open="'+file.id+'">'+icon('external')+' Open</button>';
      actions+='<button type="button" class="icon-button lib-danger" data-lib-trash="'+file.id+'" aria-label="Delete '+esc(file.name)+'" title="Delete">'+icon('trash')+'</button>';
    }
    return '<article class="saved-link lib-row" data-file-id="'+file.id+'" data-kind="'+file.kind+'" data-category="'+esc(file.category||'other')+'"><span class="saved-icon">'+icon(KIND_ICON[file.kind]||'file')+'</span>'+
      '<div class="saved-text"><strong>'+esc(file.name)+'</strong><small>'+esc(meta)+'</small>'+(file.job_title&&file.job_title!==file.name?'<small class="lib-job">'+esc(file.job_title)+'</small>':'')+watchMark(file)+'</div>'+
      '<div class="saved-actions">'+actions+'</div></article>';
  }

  function statusText(result){
    var q=view.q.trim();
    if(!result.total){
      if(filtered())return 'No files match'+(q?' “'+q+'”':'')+(view.cats.length?' in the chosen types':'')+'. Clear the search or choose All.';
      return view.area==='trash'?'The trash is empty.':'Nothing saved yet. Finished downloads show up here.';
    }
    var count=result.total+(result.total===1?' file':' files');
    var text=view.area==='trash'?count+' in the trash, '+SORT_NOTE[view.sort]+'. Restore one, or delete it for good.':
      count+(q?(result.total===1?' matches “':' match “')+q+'”, ':', ')+SORT_NOTE[view.sort]+'.';
    return text+(result.truncated?' Very big folders are only partly listed.':'');
  }

  async function load(){
    if(!root||!root.isConnected)return;
    var ticket=++seq,status=root.querySelector('.lib-status');
    status.textContent='Looking through your saved files…';
    try{
      var result=await client.listFiles({area:view.area,offset:view.offset,limit:PAGE,cats:view.cats,q:view.q.trim(),sort:view.sort});
      if(ticket!==seq||!root.isConnected)return;
      if(result.total&&view.offset>=result.total){view.offset=Math.max(0,Math.floor((result.total-1)/PAGE)*PAGE);return load();}
      var list=root.querySelector('.lib-list'),hadFocus=list.contains(document.activeElement),focusIndex=hadFocus?[].indexOf.call(list.querySelectorAll('button'),document.activeElement):-1;
      readMarks();list.innerHTML=result.files.map(row).join('');
      status.textContent=statusText(result);
      var pager=root.querySelector('.lib-pager');pager.hidden=result.total<=PAGE;
      root.querySelector('.lib-range').textContent=result.total?(view.offset+1)+'–'+Math.min(result.total,view.offset+PAGE)+' of '+result.total:'';
      root.querySelector('[data-lib-page="-1"]').disabled=view.offset===0;
      root.querySelector('[data-lib-page="1"]').disabled=view.offset+PAGE>=result.total;
      var buttons=list.querySelectorAll('button');
      if(focusIndex>=0){
        // The focused row went away (deleted, filtered out): keep focus in the panel, never on <body>.
        var keep=buttons.length?buttons[Math.min(focusIndex,buttons.length-1)]:root.querySelector('[data-lib-cat][aria-pressed="true"]');
        if(keep)keep.focus({preventScroll:true});
      }
      if(focusNext){focusNext=false;var first=buttons[0]||root.querySelector('#lib-search');if(first){first.focus({preventScroll:true});first.scrollIntoView({block:'center'});}}
    }catch(error){if(ticket===seq&&root.isConnected)status.textContent=error.message||'The library could not be read.';}
  }

  // OMNI_DL_STORAGE_METER_V1: one bar per place; low space turns the bar to the warning colour.
  function drawStorage(){
    var box=root&&root.querySelector('.lib-storage');if(!box)return;
    var list=window.OmniStorageMeter?window.OmniStorageMeter.rows(places):[];
    box.hidden=!list.length;
    box.innerHTML=list.map(function(r){return '<div class="lib-meter'+(r.low?' low':'')+'" data-place="'+esc(r.id)+'"><span class="lib-meter-label">'+esc(r.label)+'</span>'+
      '<span class="lib-meter-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+r.used_pct+'" aria-label="'+esc(r.label)+' used"><span style="width:'+r.used_pct+'%"></span></span>'+
      '<span class="lib-meter-text">'+esc(r.text)+(r.low?' · low on space':'')+'</span></div>';}).join('');
  }
  function render(){root.innerHTML=shell();drawStorage();return load();}

  async function openFile(id){var link=await client.fileLink({id:id});location.assign(link.url);}
  function play(id){location.assign('/player#id='+id);}

  function arm(button,label){
    if(button.dataset.armed&&Number(button.dataset.armed)>Date.now())return true;
    button.dataset.armed=String(Date.now()+ARM_MS);button.dataset.label=button.innerHTML;
    button.classList.add('armed');button.innerHTML=icon('trash')+' '+label;
    setTimeout(function(){if(button.isConnected&&button.dataset.armed){delete button.dataset.armed;button.classList.remove('armed');button.innerHTML=button.dataset.label;}},ARM_MS);
    return false;
  }

  // Chips: All clears; any other chip toggles (several types at once); every chip on is the same as All.
  function chooseCat(cat){
    if(cat==='all')view.cats=[];
    else{
      var next=view.cats.slice(),at=next.indexOf(cat);
      if(at>=0)next.splice(at,1);else next.push(cat);
      view.cats=catOrder(next);
      if(view.cats.length===CATS.length)view.cats=[];
    }
    view.offset=0;remember();
    root.querySelectorAll('[data-lib-cat]').forEach(function(n){n.setAttribute('aria-pressed',String(n.dataset.libCat==='all'?view.cats.length===0:view.cats.indexOf(n.dataset.libCat)>=0));});
    return load();
  }

  // Typing waits a moment before asking the worker; Enter, or the keyboard closing ("change"), asks at once.
  function search(now){
    clearTimeout(searchTimer);
    var field=root&&root.querySelector('#lib-search');if(!field)return;
    var value=field.value.slice(0,100);
    var run=function(){if(value===view.q)return;view.q=value;view.offset=0;load();};
    if(now)run();else searchTimer=setTimeout(run,SEARCH_MS);
  }

  async function click(event){
    var b=event.target.closest('button');if(!b||!root.contains(b))return;
    var d=b.dataset;
    try{
      if(d.libCat)return await chooseCat(d.libCat);
      if(d.libArea){view.area=d.libArea;view.offset=0;focusNext=true;return await render();}
      if(d.libRefresh!==undefined)return await load();
      if(d.libLargest!==undefined){view.sort='size';view.area='files';view.offset=0;remember();focusNext=true;return await render();}
      if(d.libPage){view.offset=Math.max(0,view.offset+Number(d.libPage)*PAGE);focusNext=true;return await load();}
      if(d.libPlay)return play(d.libPlay);
      if(d.libOpen){b.disabled=true;return await openFile(d.libOpen);}
      if(d.libTrash){if(!arm(b,'Delete?'))return toast('Press again to move it to the trash.');b.disabled=true;await client.fileAction('trash',d.libTrash);toast('Moved to the trash. You can restore it from Show trash.');return await load();}
      if(d.libRestore){b.disabled=true;await client.fileAction('restore',d.libRestore);toast('Restored.');return await load();}
      if(d.libDelete){if(!arm(b,'Delete for good?'))return toast('Press again to delete it for good. This cannot be undone.');b.disabled=true;await client.fileAction('delete',d.libDelete);toast('Deleted for good.');return await load();}
    }catch(error){toast(error.message||'That did not work.');if(b.isConnected)b.disabled=false;load();}
  }

  function input(event){if(event.target.id==='lib-search')search(false);}
  function change(event){
    if(event.target.id==='lib-sort'){
      var value=event.target.value;
      if(SORTS.some(function(s){return s[0]===value;})&&value!==view.sort){view.sort=value;view.offset=0;remember();load();}
    }else if(event.target.id==='lib-search')search(true);
  }
  function keydown(event){if(event.target.id==='lib-search'&&event.key==='Enter'){event.preventDefault();search(true);}}

  window.OmniFilesLibrary=Object.freeze({
    mount:function(node,apiClient,options){
      if(!node||!apiClient||typeof apiClient.listFiles!=='function')return;
      client=apiClient;root=node;toast=options&&options.toast||toast;
      if(options&&options.focus)focusNext=true;
      node.addEventListener('click',click);
      node.addEventListener('input',input);
      node.addEventListener('change',change);
      node.addEventListener('keydown',keydown);
      render();
    },
    // A newly completed job refreshes the list while it is on screen.
    notify:function(jobs,placeList){
      if(Array.isArray(placeList)){places=placeList;drawStorage();}
      var ids=(jobs||[]).filter(function(j){return j.status==='completed'&&!j.demo&&j.filepath;}).map(function(j){return j.id;}).join(',');
      if(ids!==completed){var first=completed===null;completed=ids;if(!first&&root&&root.isConnected)load();}
    },
    openJob:async function(jobId,apiClient,options){
      var c=apiClient||client;if(!c)return;
      try{var link=await c.fileLink({job:jobId});if(playable(link.kind))play(link.id);else if(openable(link.kind))location.assign(link.url);else (options&&options.toast||toast)('This file type cannot be opened here. It is in the Library.');}
      catch(error){(options&&options.toast||toast)(error.message||'The file could not be opened.');}
    }
  });
})();
