'use strict';
const video=document.getElementById('video');
const button=document.getElementById('run');
const report=document.getElementById('result');
window.omniAVPlaybackResult={status:'READY',checks:[]};
window.omniFeatureResults=[];
let running;
function start() {
  if(running)return running;
  running=run();return running;
}
async function run() {
  const checks=[];
  const controller=new AbortController();
  const signal=controller.signal;
  let objectURL,source,result;
  const overall=setTimeout(()=>controller.abort(),25000);
  const check=name=>{checks.push(name);report.textContent=checks.join('\n');};
  const wait=(target,name,ms=5000)=>new Promise((resolve,reject)=>{
    let timer;
    const clear=()=>{clearTimeout(timer);target.removeEventListener(name,ok);target.removeEventListener('error',bad);signal.removeEventListener('abort',aborted);};
    const ok=()=>{clear();resolve();};
    const bad=()=>{clear();reject(Error(name+' failed; mediaError='+(video.error?video.error.code:'none')));};
    const aborted=()=>{clear();reject(Error('overall deadline/cancellation'));};
    if(signal.aborted){aborted();return;}
    target.addEventListener(name,ok);target.addEventListener('error',bad);signal.addEventListener('abort',aborted);
    timer=setTimeout(()=>{clear();reject(Error(name+' timeout'));},ms);
  });
  const fetchBody=async(name,json=false)=>{
    const response=await fetch('generated/'+name,{signal});
    if(!response.ok)throw Error(name+' HTTP '+response.status);
    return json?response.json():response.arrayBuffer();
  };
  button.disabled=true;
  window.omniAVPlaybackResult={status:'RUNNING',checks};
  try {
    if(typeof MediaSource==='undefined')throw Error('MediaSource unavailable');
    const manifest=await fetchBody('manifest.json',true);
    if(manifest.tracks.length!==2||!manifest.tracks.some(t=>t.kind==='audio')||!manifest.tracks.some(t=>t.kind==='video'))throw Error('Expected separate audio/video tracks');
    if(!manifest.tracks.every(t=>MediaSource.isTypeSupported(t.mime)))throw Error('Required H264/AAC MIME unsupported');
    if(typeof video.getVideoPlaybackQuality!=='function')throw Error('Actual video-frame quality evidence unavailable');
    source=new MediaSource();objectURL=URL.createObjectURL(source);
    const opened=wait(source,'sourceopen');opened.catch(()=>{});video.src=objectURL;await opened;
    check('sourceopen');
    let totalBytes=0;
    for(const track of manifest.tracks) {
      const buffer=source.addSourceBuffer(track.mime);
      for(const name of [track.init,...track.segments]) {
        if(!/^[a-zA-Z0-9._-]+$/.test(name))throw Error('Invalid fixture name');
        const bytes=await fetchBody(name);totalBytes+=bytes.byteLength;
        if(bytes.byteLength>4*1024*1024||totalBytes>8*1024*1024)throw Error('Fixture byte quota');
        const updated=wait(buffer,'updateend');
        // Observe rejection even when appendBuffer throws synchronously.
        updated.catch(()=>{});buffer.appendBuffer(bytes);await updated;
      }
      if(!buffer.buffered.length)throw Error(track.kind+' buffered range absent');
      check(track.kind+' sequential initialization + all fragments');
    }
    source.endOfStream();
    if(source.readyState!=='ended')throw Error('Source did not enter ended state');
    check('endOfStream accepted');
    video.muted=false;video.volume=.25;
    const before={time:video.currentTime,frames:video.getVideoPlaybackQuality().totalVideoFrames};
    const ended=wait(video,'ended',10000);ended.catch(()=>{});
    // Race the play promise against the same bounded ended/error deadline.
    await Promise.race([Promise.resolve(video.play()),ended.then(()=>{if(!video.ended)throw Error('Playback never started');})]);
    await ended;
    const quality=video.getVideoPlaybackQuality();
    const after={time:video.currentTime,duration:video.duration,frames:quality.totalVideoFrames,dropped:quality.droppedVideoFrames,ended:video.ended,muted:video.muted,volume:video.volume};
    if(!after.ended||!Number.isFinite(after.time)||after.time<3.5||after.time<=before.time)throw Error('Timeline/ended evidence failed');
    if(!Number.isFinite(after.frames)||after.frames<=before.frames)throw Error('Decoded video frame count did not advance');
    if(after.muted||after.volume<=0)throw Error('Playback was not requested unmuted');
    check('decoded video frames advanced');check('timeline progressed and ended within 10 seconds');
    result={status:'PASS',checks,before,after,audioEvidence:{unmutedRequested:true,
      pcmSubmission:'REQUIRES_NATIVE_PROCESS_LOG',logPrefix:'OMNI MSE:',requiredNativeField:'pcmSubmittedFrames > 0',
      physicalAudibility:'NOT_VERIFIED'},scope:'JavaScript timeline/video checks passed; verify native PCM log separately'};
  } catch(error) {
    result={status:'FAIL',checks,error:String(error),audioEvidence:{physicalAudibility:'NOT_VERIFIED'}};
  } finally {
    clearTimeout(overall);controller.abort();
    video.pause();video.removeAttribute('src');video.load();
    if(objectURL)URL.revokeObjectURL(objectURL);
    window.omniAVPlaybackResult=result;
    window.omniFeatureResults.push({name:'MSE unmuted separate-track JS playback baseline',pass:result.status==='PASS',value:result});
    report.textContent=JSON.stringify(result,null,2);button.disabled=false;
  }
  return result;
}
window.omniStartMediaTest=start;
button.onclick=start;
