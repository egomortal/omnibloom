const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const script=fs.readFileSync(__dirname+'/av-playback.js','utf8');
async function scenario(mode) {
  let media,revoked=0,paused=0,detached=0,loaded=0,appends=0;
  class Buffer extends EventTarget {
    constructor(){super();this.buffered={length:1};}
    appendBuffer(){appends++;setImmediate(()=>this.dispatchEvent(new Event('updateend')));}
  }
  class Source extends EventTarget {
    static isTypeSupported(){return true;}
    constructor(){super();media=this;this.readyState='closed';}
    addSourceBuffer(){return new Buffer();}
    endOfStream(){this.readyState='ended';}
  }
  class Video extends EventTarget {
    constructor(){super();this.currentTime=0;this.frames=1;this.ended=false;this.error=null;}
    set src(value){setImmediate(()=>{media.readyState='open';media.dispatchEvent(new Event('sourceopen'));});}
    getVideoPlaybackQuality(){return {totalVideoFrames:this.frames,droppedVideoFrames:0};}
    play(){
      if(mode==='play-rejected')return Promise.reject(Error('NotAllowedError'));
      if(mode==='ended-timeout')return Promise.resolve();
      setImmediate(()=>{this.currentTime=4.01;this.duration=4.01;this.frames=mode==='frozen-frames'?1:120;this.ended=true;this.dispatchEvent(new Event('ended'));});
      return Promise.resolve();
    }
    pause(){paused++;}removeAttribute(){detached++;}load(){loaded++;}
  }
  const video=new Video(),run={},result={};
  const manifest={tracks:[{kind:'video',mime:'video/mp4',init:'init-0.mp4',segments:['segment-0.m4s']},
    {kind:'audio',mime:'audio/mp4',init:'init-1.mp4',segments:['segment-1.m4s']}]};
  const context=vm.createContext({window:{},document:{getElementById:id=>({video,run,result})[id]},
    MediaSource:mode==='unsupported'?undefined:Source,AbortController,Uint8Array,
    setTimeout:(callback,ms)=>setTimeout(callback,mode==='ended-timeout'&&ms===10000?5:ms),clearTimeout,
    URL:{createObjectURL(){return 'blob:fixture';},revokeObjectURL(){revoked++;}},
    fetch:async path=>({ok:mode!=='http-failure',status:404,json:async()=>manifest,arrayBuffer:async()=>new ArrayBuffer(10)})});
  vm.runInContext(script,context);
  const promise=context.window.omniStartMediaTest();
  assert.equal(context.window.omniStartMediaTest(),promise,'duplicate calls share one run');
  await promise;
  assert.deepEqual([paused,detached,loaded],[1,1,1]);assert.equal(run.disabled,false);
  return {value:context.window.omniAVPlaybackResult,revoked,appends,features:context.window.omniFeatureResults};
}
(async()=>{
  const pass=await scenario('success');assert.equal(pass.value.status,'PASS');assert.equal(pass.appends,4);assert.equal(pass.revoked,1);
  assert.equal(pass.value.after.frames,120);assert.equal(pass.value.after.muted,false);
  assert.equal(pass.value.audioEvidence.pcmSubmission,'REQUIRES_NATIVE_PROCESS_LOG');
  assert.equal(pass.value.audioEvidence.physicalAudibility,'NOT_VERIFIED');
  for(const mode of ['unsupported','http-failure','play-rejected','frozen-frames','ended-timeout']){
    const fail=await scenario(mode);assert.equal(fail.value.status,'FAIL',mode);assert.equal(fail.features[0].pass,false);
  }
  console.log('PASS mock AV harness: success, unsupported, HTTP failure, play rejection, frozen frames, ended timeout, idempotence and cleanup. Not a browser/media test.');
})().catch(error=>{console.error(error);process.exitCode=1;});
