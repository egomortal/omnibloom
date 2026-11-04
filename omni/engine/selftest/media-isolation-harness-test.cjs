// Host-only state-machine checks, not proof of browser/console media support.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'media-isolation.html'),'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
class Target {
    constructor(){this.handlers=new Map();}
    addEventListener(n,f){if(!this.handlers.has(n))this.handlers.set(n,new Set());this.handlers.get(n).add(f);}
    removeEventListener(n,f){this.handlers.get(n)?.delete(f);}
    emit(n){for(const f of [...(this.handlers.get(n)||[])])f({type:n});}
    listeners(){return [...this.handlers.values()].reduce((sum,x)=>sum+x.size,0);}
}
function setup(){
    const window=new Target(),timers=new Map(),elements=new Map();let next=0,created=0,last;
    for(const id of ['status','player','mp4','webm','cancel'])elements.set(id,{disabled:true,textContent:'',appendChild(){}});
    const document={readyState:'loading',getElementById:id=>elements.get(id),createElement(name){
        assert.equal(name,'video');created++;last=new Target();
        Object.assign(last,{readyState:0,networkState:0,currentTime:0,duration:2,videoWidth:0,videoHeight:0,error:null,ended:false,
            load(){},play(){return Promise.resolve();},pause(){},removeAttribute(){delete this.src;},remove(){this.removed=true;}});
        return last;
    }};
    vm.runInNewContext(script,{window,document,Date,Number,Promise,JSON,setTimeout(f){timers.set(++next,f);return next;},clearTimeout(id){timers.delete(id);}});
    return {window,document,timers,get video(){return last;},get created(){return created;},load(){document.readyState='complete';window.emit('load');},
        timeout(){assert.equal(timers.size,1);[...timers.values()][0]();}};
}
async function tick(){await Promise.resolve();await Promise.resolve();}
async function run(outcome){
    const h=setup();
    assert.equal((await h.window.omniStartMediaTest()).outcome,'not-ready');
    assert.equal(h.created,0);assert.equal(h.timers.size,0);
    h.load();assert.equal(h.created,0); // load never starts media implicitly
    assert.equal((await h.window.omniStartMediaTest('../remote')).outcome,'invalid-format');
    const pending=h.window.omniStartMediaTest('mp4'); const video=h.video;
    assert.equal(video.src,'media-test.mp4');
    assert.equal((await h.window.omniStartMediaTest('webm')).outcome,'busy');
    if(outcome==='timeout') h.timeout();
    else if(outcome==='error'){video.error={code:4};video.emit('error');}
    else if(outcome==='cancelled')h.window.omniMediaIsolation.cancel();
    else {
        if(outcome==='rejected')video.play=()=>Promise.reject(new Error('blocked playback'));
        video.videoWidth=320;video.videoHeight=180;video.readyState=2;video.emit('loadeddata');await tick();
        if(outcome==='passed'){video.currentTime=2;video.ended=true;video.emit('ended');}
        else if(outcome==='play-timeout')h.timeout();
    }
    const result=await pending;
    assert.equal(result.outcome,outcome==='play-timeout'?'timeout':outcome);
    assert.equal(h.timers.size,0);assert.equal(video.listeners(),0);assert.equal(video.removed,true);
    const results=h.window.omniFeatureResults;
    assert.equal(results.every(r=>r.pass),outcome==='passed');
    assert.equal(h.window.omniMediaIsolation.snapshot().stage,'complete');
    // Re-entry after cleanup must create a fresh player, not reuse stale listeners.
    const retry=h.window.omniStartMediaTest('webm');assert.equal(h.video.src,'media-test.webm');
    h.window.omniMediaIsolation.cancel();assert.equal((await retry).outcome,'cancelled');
    assert.equal(h.timers.size,0);assert.equal(h.video.listeners(),0);
}
(async()=>{
    for(const outcome of ['passed','error','timeout','cancelled','play-timeout','rejected'])await run(outcome);
    console.log('PASS: document gate, explicit start, busy gate, success/error/timeouts/cancel/rejection and cleanup/re-entry');
})().catch(e=>{console.error(e);process.exitCode=1;});
