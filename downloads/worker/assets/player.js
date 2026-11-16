/* OMNI_DL_LIBRARY_V1: minimal controller-friendly player for one saved file.
   Cross (Enter/Space) play/pause, Left/Right seek 10 s, Circle (Escape/Backspace) back to the Library.
   The page holds the session token (like /downloads) and trades the file id for a short-lived signed stream link,
   because a <video src> cannot send the X-Omni-Token header. An expired link is renewed and playback resumes. */
(function(){
  'use strict';
  var $=function(id){return document.getElementById(id);};
  var token=(document.querySelector('meta[name="omni-session-token"]')||{}).content||'';
  var match=/^#id=([a-f0-9]{32})$/.exec(location.hash),fileId=match?match[1]:null;
  var media=null,dragging=false,renewedAt=0,kind='';
  // OMNI_DL_WATCH_V1: position saved every 5 s and on pause / leaving; a resume prompt when it was left mid-film.
  var W=window.OmniWatch||null,store=null,watchKey=null,prompt=null;
  try{store=window.localStorage;}catch(_){}
  var GLYPHS={xbox:{cross:'A',circle:'B'},playstation:{cross:'Cross',circle:'Circle'}};
  var glyphs='xbox';try{if(localStorage.getItem('omni.glyphs')==='playstation')glyphs='playstation';}catch(_){}
  document.querySelectorAll('[data-glyph]').forEach(function(n){n.textContent=GLYPHS[glyphs][n.dataset.glyph]||n.textContent;});

  function say(text){$('message').textContent=text||'';}
  function clock(s){if(!isFinite(s)||s<0)s=0;s=Math.floor(s);var h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(r).padStart(2,'0');}
  function back(){if(media){try{media.pause();}catch(_){}}save();location.replace('/downloads#view=files');}

  function save(){
    if(!W||!store||!watchKey||!media||prompt||!isFinite(media.duration)||media.duration<=0)return;
    W.record(store,watchKey,media.ended?media.duration:media.currentTime,media.duration);
  }
  function play(){var p=media.play();if(p&&p.catch)p.catch(function(){/* autoplay may be refused: Cross starts it */});}
  // "Resume from 12:34?": Cross takes the focused button (Resume first), Left/Right move, Circle starts over.
  // With no answer it resumes after 5 s.
  function offerResume(at){
    var box=document.createElement('div'),left=5;
    box.className='resume';box.setAttribute('role','dialog');box.setAttribute('aria-label','Resume');
    box.innerHTML='<p>Resume from <strong>'+clock(at)+'</strong>?</p><div class="resume-actions">'+
      '<button type="button" class="pbtn resume-yes" data-resume="yes">Resume <kbd>'+GLYPHS[glyphs].cross+'</kbd></button>'+
      '<button type="button" class="pbtn" data-resume="no">Start over</button></div><p class="resume-count" aria-live="polite"></p>';
    $('stage').append(box);
    var count=box.querySelector('.resume-count'),tick=function(){count.textContent='Resuming in '+left+' s';};
    tick();
    prompt={box:box,timer:setInterval(function(){left--;if(left<=0)choose(true);else tick();},1000),choose:choose};
    box.addEventListener('click',function(e){var b=e.target.closest('[data-resume]');if(b)choose(b.dataset.resume==='yes');});
    box.querySelector('.resume-yes').focus({preventScroll:true});
    function choose(resume){
      if(!prompt)return;clearInterval(prompt.timer);prompt.box.remove();prompt=null;
      media.currentTime=resume?at:0;show();play();$('toggle').focus({preventScroll:true});
    }
  }
  function promptAct(action){
    var buttons=[].slice.call(prompt.box.querySelectorAll('[data-resume]'));
    if(action==='left'||action==='right'){buttons[action==='left'?0:1].focus({preventScroll:true});return true;}
    if(action==='cross'){prompt.choose(document.activeElement!==buttons[1]);return true;}
    if(action==='circle'){prompt.choose(false);return true;}
    return false;
  }

  async function link(){
    var response=await fetch('/api/files/link',{method:'POST',headers:{'X-Omni-Token':token,'Content-Type':'application/json'},body:JSON.stringify({id:fileId}),cache:'no-store',credentials:'same-origin',redirect:'error'});
    var value=null;try{value=await response.json();}catch(_){}
    if(response.status===403)throw new Error('The download worker restarted. Go back and choose the file again.');
    if(!response.ok||!value||typeof value.url!=='string'||!/^\/api\/files\/stream\?id=[a-f0-9]{32}&exp=\d+&sig=[a-f0-9]{64}$/.test(value.url))throw new Error(value&&value.error||'The file could not be opened.');
    return value;
  }

  function toggle(){if(!media)return;if(media.paused||media.ended){var p=media.play();if(p&&p.catch)p.catch(function(e){say(e.message||'Playback could not start.');});}else media.pause();}
  function seek(delta){if(!media||!isFinite(media.duration))return;media.currentTime=Math.max(0,Math.min(media.duration-0.1,media.currentTime+delta));show();}
  function show(){if(!media)return;$('now').textContent=clock(media.currentTime);if(isFinite(media.duration)){$('total').textContent=clock(media.duration);$('seek').max=String(Math.floor(media.duration));}if(!dragging)$('seek').value=String(Math.floor(media.currentTime));}
  function playing(){var on=media&&!media.paused&&!media.ended;$('toggle-icon').setAttribute('href','/assets/icons.svg#'+(on?'pause':'play'));$('toggle').setAttribute('aria-label',on?'Pause':'Play');$('stage').classList.toggle('playing',!!on);}

  async function renew(){
    // A signed link lasts two hours; when it runs out mid-film, get a new one and carry on from the same spot.
    if(Date.now()-renewedAt<10000){say('The file stopped playing. Go back and try again.');return;}
    renewedAt=Date.now();
    var at=media.currentTime,wasPlaying=!media.paused;
    try{var fresh=await link();media.src=fresh.url;media.addEventListener('loadedmetadata',function(){media.currentTime=at;if(wasPlaying)toggle();},{once:true});say('');}
    catch(error){say(error.message);}
  }

  async function start(){
    if(!fileId){say('No file was chosen.');$('title').textContent='Nothing to play';return;}
    try{
      var info=await link();kind=info.kind;
      $('title').textContent=info.name;document.title=info.name+' · Omni player';
      if(kind!=='video'&&kind!=='audio'){location.replace(info.url);return;}
      media=document.createElement(kind);media.preload='metadata';media.playsInline=true;media.src=info.url;
      var stage=$('stage');
      if(kind==='audio'){stage.classList.add('audio');var disc=document.createElement('div');disc.className='disc';disc.textContent='♪';stage.append(disc,media);}
      else stage.append(media);
      ['timeupdate','durationchange','loadedmetadata','seeked'].forEach(function(e){media.addEventListener(e,show);});
      ['play','pause','ended'].forEach(function(e){media.addEventListener(e,playing);});
      media.addEventListener('error',function(){if(media.error&&media.error.code===MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED&&media.readyState===0&&!renewedAt){say('This browser cannot play this file type.');return;}renew();});
      media.addEventListener('click',toggle);
      watchKey=W?W.keyFor({place:info.place,name:info.name,size:info.size}):null;
      var saved=W&&store?W.get(store,watchKey):null;
      media.addEventListener('pause',save);media.addEventListener('ended',save);
      folderInfo=info;media.addEventListener('ended',playNext);   // OMNI_DL_FOLDER_PLAY_V1
      if(kind==='video')addCaptions(info);   // OMNI_DL_SIDECARS_V1
      setInterval(function(){if(media&&!media.paused)save();},5000);
      $('toggle').focus({preventScroll:true});
      if(saved){
        // Wait for the real duration before deciding; the prompt holds playback until it is answered.
        media.addEventListener('loadedmetadata',function(){var at=W.resumeAt(saved,media.duration);if(at>0)offerResume(at);else play();},{once:true});
      }else play();
    }catch(error){say(error.message);$('title').textContent='Cannot play this file';}
  }

  // OMNI_DL_FOLDER_PLAY_V1 (D12): when a file ends, the next one in its folder (in order, shuffled or on repeat).
  var FP=window.OmniFolderPlay||null,folderInfo=null,folderMode=FP&&store?FP.load(store):'off';
  function showMode(){var b=$('folder-mode');if(b&&FP)b.textContent=FP.LABELS[folderMode];}
  async function listFolder(){var rows=[];for(var off=0;off<500;off+=100){
      var r=await fetch('/api/files?cats=video,audio&sort=name&limit=100&offset='+off,{headers:{'X-Omni-Token':token},cache:'no-store',credentials:'same-origin',redirect:'error'});
      var v=null;try{v=await r.json();}catch(_){}if(!r.ok||!v||!Array.isArray(v.files))break;rows=rows.concat(v.files);if(rows.length>=v.total)break;}
    return rows;}
  // OMNI_DL_SIDECARS_V1 (D11): .vtt captions beside the video become <track>s (signed links, same origin).
  async function addCaptions(info){if(!FP||!FP.sidecars)return;try{var rows=[];for(var off=0;off<500;off+=100){
      var r=await fetch('/api/files?cats=document&sort=name&limit=100&offset='+off,{headers:{'X-Omni-Token':token},cache:'no-store',credentials:'same-origin',redirect:'error'});
      var v=null;try{v=await r.json();}catch(_){}if(!r.ok||!v||!Array.isArray(v.files))break;rows=rows.concat(v.files);if(rows.length>=v.total)break;}
    var subs=FP.sidecars(rows,info);for(var i=0;i<subs.length;i++){
      var lr=await fetch('/api/files/link',{method:'POST',headers:{'X-Omni-Token':token,'Content-Type':'application/json'},body:JSON.stringify({id:subs[i].id}),cache:'no-store',credentials:'same-origin',redirect:'error'});
      var lv=null;try{lv=await lr.json();}catch(_){}if(!lr.ok||!lv||typeof lv.url!=='string'||!/^\/api\/files\/stream\?/.test(lv.url))continue;
      var tr=document.createElement('track');tr.kind='subtitles';tr.src=lv.url;tr.label=subs[i].label;if(subs[i].lang)tr.srclang=subs[i].lang;if(i===0)tr.default=true;media.append(tr);}
    if(subs.length)say(subs.length===1?'Captions on.':subs.length+' caption tracks.');}catch(_){}}
  async function playNext(){if(!FP||folderMode==='off'||!folderInfo)return;
    try{var list=FP.siblings(await listFolder(),folderInfo),id=FP.next(list,fileId,folderMode);
      if(!id){say('End of the folder.');return;}say('Next: '+((list.filter(function(r){return r.id===id;})[0]||{}).name||''));
      setTimeout(function(){location.replace('/player#id='+id);location.reload();},1200);}
    catch(_){say('Could not find the next file in this folder.');}}
  if($('folder-mode')){showMode();$('folder-mode').addEventListener('click',function(){if(!FP)return;folderMode=FP.cycle(folderMode);if(store)FP.save(store,folderMode);showMode();});}
  $('toggle').addEventListener('click',toggle);
  $('back10').addEventListener('click',function(){seek(-10);});
  $('fwd10').addEventListener('click',function(){seek(10);});
  $('back').addEventListener('click',back);
  $('seek').addEventListener('input',function(){dragging=true;$('now').textContent=clock(Number($('seek').value));});
  $('seek').addEventListener('change',function(){dragging=false;if(media)media.currentTime=Number($('seek').value);});

  // One action vocabulary for keys and the Omni engine's controller hook.
  function act(action){
    if(prompt)return promptAct(action);
    switch(action){
      case 'cross':if(document.activeElement===$('back'))back();else if(document.activeElement===$('back10'))seek(-10);else if(document.activeElement===$('fwd10'))seek(10);else toggle();return true;
      case 'circle':back();return true;
      case 'left':seek(-10);return true;
      case 'right':seek(10);return true;
      default:return false;
    }
  }
  var PAD={'saved.choose':'cross',cross:'cross',a:'cross',accept:'cross','saved.dismiss':'circle',circle:'circle',b:'circle',back:'circle','saved.left':'left',left:'left','saved.right':'right',right:'right'};
  window.omniMediaController=window.omniPadController=function(action){return typeof action==='string'&&PAD.hasOwnProperty(action.toLowerCase())?act(PAD[action.toLowerCase()]):false;};
  document.addEventListener('keydown',function(event){
    if(event.ctrlKey||event.metaKey||event.altKey)return;
    var a={Enter:'cross',' ':'cross',Spacebar:'cross',MediaPlayPause:'cross',Escape:'circle',Backspace:'circle',BrowserBack:'circle',GoBack:'circle',ArrowLeft:'left',ArrowRight:'right',MediaTrackPrevious:'left',MediaTrackNext:'right'}[event.key];
    if(a&&act(a))event.preventDefault();
  });
  window.addEventListener('pagehide',save);
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='hidden')save();});
  start();
})();
