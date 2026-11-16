/* OMNI_DL_LIBRARY_V1: the Library panel on the Queue page. Lists saved files by opaque id (the worker never sends a
   path to act on and never accepts one), plays video/audio in /player, opens PDFs and pictures in the browser, and
   deletes in two steps: a file goes to the trash first; only a file in the trash can be deleted for real. */
(function(){
  'use strict';
  var PAGE=50,ARM_MS=5000;
  var esc=function(value){return String(value==null?'':value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});};
  var icon=function(name){return '<svg class="icon" aria-hidden="true"><use href="/assets/icons.svg#'+name+'"></use></svg>';};
  var size=function(v){return v>=1073741824?(v/1073741824).toFixed(1)+' GB':v>=1048576?(v/1048576).toFixed(1)+' MB':v>=1024?Math.round(v/1024)+' KB':v+' B';};
  var KIND_ICON={video:'video',audio:'music',image:'file',pdf:'file',text:'file',other:'file'};
  var KIND_LABEL={video:'Video',audio:'Audio',image:'Picture',pdf:'PDF',text:'Text',other:'File'};
  var view={kind:'all',area:'files',offset:0},client=null,root=null,toast=function(){},seq=0,completed=null,focusNext=false;

  function date(seconds){try{return new Date(seconds*1000).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'});}catch(_){return '';}}
  function playable(kind){return kind==='video'||kind==='audio';}
  function openable(kind){return kind==='image'||kind==='pdf'||kind==='text';}

  function shell(){
    var tabs=[['all','All'],['video','Video'],['audio','Audio'],['other','Other']].map(function(t){return '<button type="button" data-lib-kind="'+t[0]+'" aria-pressed="'+(view.kind===t[0])+'">'+t[1]+'</button>';}).join('');
    return '<div class="panel-heading"><h2>'+icon('folder')+' '+(view.area==='trash'?'Library trash':'Library')+'</h2><div class="section-actions">'+
      '<button type="button" class="secondary-button" data-lib-area="'+(view.area==='trash'?'files':'trash')+'">'+(view.area==='trash'?icon('arrow-left')+' Back to files':icon('trash')+' Trash')+'</button>'+
      '<button type="button" class="icon-button" data-lib-refresh aria-label="Refresh the library" title="Refresh">'+icon('refresh')+'</button></div></div>'+
      '<div class="filter-tabs" role="group" aria-label="Filter the library">'+tabs+'</div>'+
      '<p class="helper-line lib-status" role="status"></p><div class="lib-list"></div>'+
      '<div class="lib-pager" hidden><button type="button" class="secondary-button" data-lib-page="-1">'+icon('arrow-left')+' Previous</button><span class="lib-range"></span><button type="button" class="secondary-button" data-lib-page="1">Next '+icon('arrow-right')+'</button></div>';
  }

  function row(file){
    var where=file.place_label+(file.folder?' / '+file.folder:'');
    var meta=[KIND_LABEL[file.kind]||'File',size(file.size),date(file.mtime),where].filter(Boolean).join(' · ');
    var actions='';
    if(view.area==='trash'){
      actions='<button type="button" class="secondary-button" data-lib-restore="'+file.id+'">'+icon('refresh')+' Restore</button>'+
        '<button type="button" class="secondary-button lib-danger" data-lib-delete="'+file.id+'" aria-label="Delete '+esc(file.name)+' for good">'+icon('trash')+' Delete for good</button>';
    }else{
      if(playable(file.kind))actions+='<button type="button" class="secondary-button" data-lib-play="'+file.id+'">'+icon('play')+' Play</button>';
      else if(openable(file.kind))actions+='<button type="button" class="secondary-button" data-lib-open="'+file.id+'">'+icon('external')+' Open</button>';
      actions+='<button type="button" class="icon-button lib-danger" data-lib-trash="'+file.id+'" aria-label="Delete '+esc(file.name)+'" title="Delete">'+icon('trash')+'</button>';
    }
    return '<article class="saved-link lib-row" data-file-id="'+file.id+'" data-kind="'+file.kind+'"><span class="saved-icon">'+icon(KIND_ICON[file.kind]||'file')+'</span>'+
      '<div class="saved-text"><strong>'+esc(file.name)+'</strong><small>'+esc(meta)+'</small>'+(file.job_title&&file.job_title!==file.name?'<small class="lib-job">'+esc(file.job_title)+'</small>':'')+'</div>'+
      '<div class="saved-actions">'+actions+'</div></article>';
  }

  async function load(){
    if(!root||!root.isConnected)return;
    var ticket=++seq,status=root.querySelector('.lib-status');
    status.textContent='Looking through your saved files…';
    try{
      var result=await client.listFiles({kind:view.kind,area:view.area,offset:view.offset,limit:PAGE});
      if(ticket!==seq||!root.isConnected)return;
      if(result.total&&view.offset>=result.total){view.offset=Math.max(0,Math.floor((result.total-1)/PAGE)*PAGE);return load();}
      var list=root.querySelector('.lib-list'),hadFocus=list.contains(document.activeElement),focusIndex=hadFocus?[].indexOf.call(list.querySelectorAll('button'),document.activeElement):-1;
      list.innerHTML=result.files.map(row).join('');
      var empty=view.area==='trash'?'The trash is empty.':view.kind==='all'?'Nothing saved yet. Finished downloads show up here.':'No '+(view.kind==='other'?'other files':view.kind+' files')+' yet.';
      status.textContent=result.total?(result.total+(result.total===1?' file':' files')+(view.area==='trash'?' in the trash. Restore one, or delete it for good.':', newest first.')+(result.truncated?' Very big folders are only partly listed.':'')):empty;
      var pager=root.querySelector('.lib-pager');pager.hidden=result.total<=PAGE;
      root.querySelector('.lib-range').textContent=result.total?(view.offset+1)+'–'+Math.min(result.total,view.offset+PAGE)+' of '+result.total:'';
      root.querySelector('[data-lib-page="-1"]').disabled=view.offset===0;
      root.querySelector('[data-lib-page="1"]').disabled=view.offset+PAGE>=result.total;
      var buttons=list.querySelectorAll('button');
      if(focusIndex>=0&&buttons.length)buttons[Math.min(focusIndex,buttons.length-1)].focus({preventScroll:true});
      if(focusNext){focusNext=false;var first=buttons[0]||root.querySelector('[data-lib-kind]');if(first){first.focus({preventScroll:true});first.scrollIntoView({block:'center'});}}
    }catch(error){if(ticket===seq&&root.isConnected)status.textContent=error.message||'The library could not be read.';}
  }

  function render(){root.innerHTML=shell();return load();}

  async function openFile(id){var link=await client.fileLink({id:id});location.assign(link.url);}
  function play(id){location.assign('/player#id='+id);}

  function arm(button,label){
    if(button.dataset.armed&&Number(button.dataset.armed)>Date.now())return true;
    button.dataset.armed=String(Date.now()+ARM_MS);button.dataset.label=button.innerHTML;
    button.classList.add('armed');button.innerHTML=icon('trash')+' '+label;
    setTimeout(function(){if(button.isConnected&&button.dataset.armed){delete button.dataset.armed;button.classList.remove('armed');button.innerHTML=button.dataset.label;}},ARM_MS);
    return false;
  }

  async function click(event){
    var b=event.target.closest('button');if(!b||!root.contains(b))return;
    var d=b.dataset;
    try{
      if(d.libKind){view.kind=d.libKind;view.offset=0;root.querySelectorAll('[data-lib-kind]').forEach(function(n){n.setAttribute('aria-pressed',n.dataset.libKind===view.kind);});return await load();}
      if(d.libArea){view.area=d.libArea;view.offset=0;focusNext=true;return await render();}
      if(d.libRefresh!==undefined)return await load();
      if(d.libPage){view.offset=Math.max(0,view.offset+Number(d.libPage)*PAGE);focusNext=true;return await load();}
      if(d.libPlay)return play(d.libPlay);
      if(d.libOpen){b.disabled=true;return await openFile(d.libOpen);}
      if(d.libTrash){if(!arm(b,'Delete?'))return toast('Press again to move it to the trash.');b.disabled=true;await client.fileAction('trash',d.libTrash);toast('Moved to the trash. You can restore it from Trash.');return await load();}
      if(d.libRestore){b.disabled=true;await client.fileAction('restore',d.libRestore);toast('Restored.');return await load();}
      if(d.libDelete){if(!arm(b,'Delete for good?'))return toast('Press again to delete it for good. This cannot be undone.');b.disabled=true;await client.fileAction('delete',d.libDelete);toast('Deleted for good.');return await load();}
    }catch(error){toast(error.message||'That did not work.');if(b.isConnected)b.disabled=false;load();}
  }

  window.OmniFilesLibrary=Object.freeze({
    mount:function(node,apiClient,options){
      if(!node||!apiClient||typeof apiClient.listFiles!=='function')return;
      client=apiClient;root=node;toast=options&&options.toast||toast;
      if(options&&options.focus)focusNext=true;
      node.addEventListener('click',click);
      render();
    },
    // A newly completed job refreshes the list while it is on screen.
    notify:function(jobs){
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
