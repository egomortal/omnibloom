'use strict';
const video = document.getElementById('video');
const button = document.getElementById('run');
const report = document.getElementById('result');
window.omniMSEResult = {status: 'READY', checks: []};
window.omniFeatureResults = [];
const deadline = (promise, ms, label) => new Promise((resolve,reject) => {
  const timer=setTimeout(()=>reject(Error(label+' timeout')),ms);
  promise.then(v=>{clearTimeout(timer);resolve(v)},e=>{clearTimeout(timer);reject(e)});
});
function event(target, success, failure='error') {
  return new Promise((resolve,reject)=>{
    const clear=()=>{clearTimeout(timer);target.removeEventListener(success,ok);target.removeEventListener(failure,bad)};
    const ok=()=>{clear();resolve()}; const bad=()=>{clear();reject(Error(failure))};
    target.addEventListener(success,ok,{once:true});target.addEventListener(failure,bad,{once:true});
    const timer=setTimeout(()=>{clear();reject(Error(success+' timeout'))},5000);
  });
}
let started = false;
async function start() {
  if (started) return window.omniMSEResult;
  started = true;
  button.disabled=true; const checks=[];let source,objectURL;
  const check=(name)=>{checks.push(name);report.textContent=checks.join('\n')};
  const cleanup=()=>{
    video.pause();video.removeAttribute('src');video.load();
    if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
  };
  try {
    window.omniMSEResult={status:'RUNNING',checks};
    if(typeof MediaSource==='undefined') {
      window.omniMSEResult={status:'UNSUPPORTED',reason:'MediaSource is absent',checks};return;
    }
    const response=await deadline(fetch('generated/manifest.json'),5000,'manifest fetch');if(!response.ok)throw Error('manifest HTTP '+response.status);
    const manifest=await deadline(response.json(),5000,'manifest body');
    if(!manifest.tracks.every(t=>MediaSource.isTypeSupported(t.mime))) {
      window.omniMSEResult={status:'UNSUPPORTED',reason:'Required H.264/AAC MIME unsupported',checks};return;
    }
    source=new MediaSource();objectURL=URL.createObjectURL(source);
    const opened=event(source,'sourceopen');video.src=objectURL;
    await deadline(opened,5000,'sourceopen');check('sourceopen');
    const buffers=[];
    for(const track of manifest.tracks) {
      const buffer=source.addSourceBuffer(track.mime);buffers.push(buffer);
      for(const file of [track.init,...track.segments]) {
        const resp=await deadline(fetch('generated/'+file),5000,'fetch');if(!resp.ok)throw Error('fixture HTTP '+resp.status);
        const bytes=await deadline(resp.arrayBuffer(),5000,'fixture body');if(bytes.byteLength>4*1024*1024)throw Error('fixture quota');
        const updated=event(buffer,'updateend');buffer.appendBuffer(bytes);
        let rejected=false;
        try{buffer.appendBuffer(new Uint8Array([0]));}catch(e){rejected=e.name==='InvalidStateError';}
        if(!rejected)throw Error('concurrent append did not reject');
        await deadline(updated,5000,'append');
      }
      if(!buffer.buffered.length)throw Error(track.kind+' has no buffered range');
      check(track.kind+' sequential init/segments + concurrent-append rejection');
    }
    for(const buffer of buffers) {
      const updated=event(buffer,'updateend');buffer.remove(0,.5);await deadline(updated,5000,'remove');
      if(!buffer.buffered.length || buffer.buffered.start(0)<.49)throw Error('remove range not reflected');
    }
    check('remove range');
    source.endOfStream();if(source.readyState!=='ended')throw Error('endOfStream state');check('endOfStream');
    const sought=event(video,'seeked');video.currentTime=1.5;await deadline(sought,5000,'seek');check('seek');
    video.muted=true;
    const qualitySupported=typeof video.getVideoPlaybackQuality==='function';
    const framesBefore=qualitySupported?video.getVideoPlaybackQuality().totalVideoFrames:null;
    let frameCallback;
    if(!qualitySupported&&typeof video.requestVideoFrameCallback==='function')
      frameCallback=new Promise(resolve=>video.requestVideoFrameCallback((_,metadata)=>resolve(metadata)));
    await deadline(video.play(),5000,'play');
    await new Promise((resolve,reject)=>{
      const clear=()=>{clearTimeout(timer);video.removeEventListener('timeupdate',f)};
      const f=()=>{if(video.currentTime>=2){clear();resolve()}};
      const timer=setTimeout(()=>{clear();reject(Error('playback progress timeout'))},5000);
      video.addEventListener('timeupdate',f);
    });
    check('muted playback timeline progressed; audible output not tested');
    if(qualitySupported) {
      const framesAfter=video.getVideoPlaybackQuality().totalVideoFrames;
      if(!Number.isFinite(framesAfter)||framesAfter<=framesBefore)throw Error('decoded video frame count did not advance');
      check('video decoded frame count advanced');
    } else if(frameCallback) {
      await deadline(frameCallback,5000,'video frame callback');
      check('video frame callback observed');
    } else check('video decoding and audio output were not verified (frame evidence unavailable)');
    video.pause();
    cleanup();check('pause/detach/revoke cleanup');
    window.omniMSEResult={status:'PASS',checks};
  } catch(e) {
    cleanup();window.omniMSEResult={status:'FAIL',error:String(e),checks};
  } finally {
    report.textContent=JSON.stringify(window.omniMSEResult,null,2);button.disabled=false;
    window.omniFeatureResults.push({name:'MSE bounded fragmented MP4 smoke test',
      pass:window.omniMSEResult.status==='PASS',value:window.omniMSEResult});
  }
}
window.omniStartMediaTest = start;
button.onclick = start;
