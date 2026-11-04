// Host control-flow tests only; actual decoding/storage release requires PS5 runs.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'media-retention.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
function environment(mode){
    class Target{
        constructor(){this.listeners=new Map();this.readyState=0;this.error=null;this.videoWidth=0;this.videoHeight=0;this.src='';}
        addEventListener(name,fn){if(!this.listeners.has(name))this.listeners.set(name,new Set());this.listeners.get(name).add(fn);}
        removeEventListener(name,fn){this.listeners.get(name)?.delete(fn);}
        emit(name){for(const fn of [...(this.listeners.get(name)||[])])fn({type:name});}
        appendChild(){} pause(){} removeAttribute(name){if(name==='src')this.src='';}
        load(){
            loads++;
            if(mode==='timeout')return;
            queueMicrotask(()=>{
                if(!this.src){this.readyState=0;this.error=null;this.emit('emptied');}
                else if(this.src==='media-invalid.mp4'){
                    if(mode==='accept-invalid'){this.readyState=2;this.emit('loadeddata');return;}
                    this.readyState=0;this.error={code:4};this.emit('error');
                }else{this.error=null;this.readyState=2;this.videoWidth=320;this.videoHeight=180;this.emit('loadeddata');}
            });
        }
    }
    let loads=0;const timers=new Map();let nextTimer=0;
    const window=new Target(),nodes=new Map();
    const document={getElementById(id){if(!nodes.has(id))nodes.set(id,new Target());return nodes.get(id);},createElement(){return new Target();}};
    vm.runInNewContext(script,{window,document,Date,JSON,Promise,setTimeout(fn){timers.set(++nextTimer,fn);return nextTimer;},clearTimeout(id){timers.delete(id);}});
    return {window,timers,get loads(){return loads;},fireTimeout(){for(const fn of [...timers.values()])fn();}};
}
(async()=>{
    let e=environment('success');
    assert.equal((await e.window.omniStartMediaTest()).outcome,'not-ready');assert.equal(e.loads,0);
    e.window.emit('load');assert.equal(e.loads,0);
    const pending=e.window.omniStartMediaTest();assert.equal((await e.window.omniStartMediaTest()).outcome,'busy');
    assert.equal((await pending).outcome,'passed');
    assert.equal(e.window.omniRetainedMedia.length,8);assert.equal(e.window.omniFeatureResults.length,18);
    assert(e.window.omniFeatureResults.every(result=>result.pass));assert.equal(e.timers.size,0);
    assert.equal((await e.window.omniStartMediaTest()).outcome,'already-run');
    for(const mode of ['timeout','accept-invalid']){
        e=environment(mode);e.window.emit('load');const run=e.window.omniStartMediaTest();
        // Allow a successful first phase to install the malformed-input waiter.
        for(let i=0;i<8;i++)await Promise.resolve();
        e.fireTimeout();assert.equal((await run).outcome,'failed');
        assert(e.window.omniFeatureResults.some(result=>!result.pass));assert.equal(e.timers.size,0);
        assert.equal(e.window.omniRetainedMedia.length,1);
    }
    console.log('PASS: gated start, 8 retained failures, valid reload/cancel, timeouts reject, cleanup/reentry; host flow only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
