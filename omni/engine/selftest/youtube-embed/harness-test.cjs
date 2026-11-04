const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'diagnostic.js'),'utf8');
function setup(automatic=false,observation){
    const nodes={},timers=new Map();let id=0,options,plays=0,destroyed=0,time=0;
    const window={omniYouTubeAutoTest:automatic,omniYouTubeObservationSeconds:observation,addEventListener(){},YT:{Player:function(target,value){options=value;this.getCurrentTime=()=>time;this.getVideoLoadedFraction=()=>0.5;this.playVideo=()=>plays++;this.destroy=()=>destroyed++;}}};
    const document={readyState:'complete',getElementById(key){return nodes[key]||(nodes[key]={});},createElement(){return {remove(){}};},head:{appendChild(){}}};
    vm.runInNewContext(source,{window,document,navigator:{},location:{origin:'http://localhost',protocol:'http:'},Number,JSON,setTimeout(fn,delay){timers.set(++id,{fn,delay});return id;},clearTimeout(id){timers.delete(id);}});
    return {window,nodes,timers,advance(value){time=value;const entry=[...timers.entries()].find(([id,t])=>t.delay===1000);assert.ok(entry);timers.delete(entry[0]);entry[1].fn();},get options(){return options;},get plays(){return plays;},get destroyed(){return destroyed;}};
}
let e=setup();e.window.omniStartMediaTest();assert.equal(e.plays,0);assert.equal([...e.timers.values()][0].delay,30000);
assert.equal(e.options.playerVars.autoplay,0);e.options.events.onReady();assert.equal(e.timers.size,0);
assert.equal(e.window.omniYouTubeDiagnostic.snapshot().phase,'waiting-user');assert.equal(e.plays,0);
e.nodes.play.onclick({isTrusted:false});assert.equal(e.plays,0);
e.nodes.play.onclick({isTrusted:true});assert.equal(e.plays,1);e.options.events.onStateChange({data:1});assert.equal(e.timers.size,0);
assert.equal(e.window.omniFeatureResults[1].name,'embed playing event');e.nodes.stop.onclick();assert.equal(e.destroyed,1);
e=setup();e.window.omniStartMediaTest();[...e.timers.values()][0].fn();assert.equal(e.window.omniFeatureResults[0].pass,false);assert.equal(e.destroyed,1);
e=setup();e.window.omniStartMediaTest();e.options.events.onReady();e.nodes.play.onclick({isTrusted:true});e.options.events.onAutoplayBlocked();assert.equal(e.timers.size,0);assert.equal(e.window.omniYouTubeDiagnostic.snapshot().phase,'waiting-user');assert.equal(e.window.omniFeatureResults[1].pass,false);
e=setup();e.window.omniStartMediaTest();e.options.events.onError({data:153});assert.equal(e.window.omniFeatureResults[0].value,153);assert.equal(e.destroyed,1);
console.log('PASS: init never plays, trusted click gating, readiness/play state, timeout, blocked/error cleanup (host API stub only).');

e=setup(true);e.window.omniStartMediaTest();e.options.events.onReady();assert.equal(e.plays,1);e.options.events.onReady();assert.equal(e.plays,1);e.options.events.onStateChange({data:1});assert.equal(e.destroyed,0);for(let i=1;i<=6;i++)e.advance(i);assert.equal(e.window.omniFeatureResults.at(-1).value.status,'PASS');assert.equal(e.window.omniFeatureResults.at(-1).value.snapshot.observation.samples.length,7);assert.equal(e.destroyed,1);assert.equal(e.timers.size,0);
e=setup(true);e.window.omniStartMediaTest();e.options.events.onReady();e.options.events.onAutoplayBlocked();assert.equal(e.window.omniFeatureResults.at(-1).value.status,'AUTOPLAY_BLOCKED');assert.equal(e.plays,1);assert.equal(e.timers.size,0);
e=setup(true);e.window.omniStartMediaTest();[...e.timers.values()].find(t=>t.delay===25000).fn();assert.equal(e.window.omniFeatureResults.at(-1).value.status,'TIMEOUT');assert.equal(e.destroyed,1);
console.log('PASS: explicit automatic mode makes one ordinary play request, records blocked/timeout, cleans up; no real network/media tested.');

e=setup(true);e.window.omniStartMediaTest();e.options.events.onReady();e.options.events.onStateChange({data:1});for(let i=1;i<=6;i++)e.advance(0);assert.equal(e.window.omniFeatureResults.at(-1).value.status,'FAIL');assert.equal(e.destroyed,1);
e=setup(true);e.window.omniStartMediaTest();e.options.events.onReady();e.options.events.onStateChange({data:1});e.options.events.onStateChange({data:2});for(let i=1;i<=6;i++)e.advance(i);assert.equal(e.window.omniFeatureResults.at(-1).value.status,'FAIL');
console.log('PASS: six-second observation requires >=3 seconds progress and PLAYING at completion; frozen/paused failures, no immediate success.');

e=setup(true);e.window.omniStartMediaTest();e.options.events.onReady();e.options.events.onStateChange({data:1});[...e.timers.values()].find(t=>t.delay===25000).fn();assert.equal(e.window.omniFeatureResults.at(-1).value.status,'TIMEOUT');assert.equal(e.timers.size,0);assert.equal(e.destroyed,1);

for(const invalid of [5,31,7.5,'30',null]){e=setup(true,invalid);assert.equal(e.window.omniYouTubeDiagnostic.snapshot().observationSeconds,6);assert.equal(e.window.omniYouTubeDiagnostic.snapshot().deadlineSeconds,25);}
e=setup(true,30);e.window.omniStartMediaTest();assert.ok([...e.timers.values()].some(t=>t.delay===50000));e.options.events.onReady();e.options.events.onStateChange({data:1});for(let i=1;i<30;i++)e.advance(i/2);assert.equal(e.destroyed,0);e.advance(15);assert.equal(e.window.omniFeatureResults.at(-1).value.status,'PASS');assert.equal(e.window.omniFeatureResults.at(-1).value.snapshot.observation.samples.length,31);assert.equal(e.timers.size,0);
console.log('PASS: validated observation range, unchanged short default, 30-second observation and 50-second total deadline.');
