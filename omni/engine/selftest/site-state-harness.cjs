// Fixture logic only; this does not simulate WebKit disk persistence.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/site-state.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const storage=new Map();let cookie='',writes=0;
function session(phase){
 const elements=new Map();
 const document={getElementById(id){if(!elements.has(id))elements.set(id,{});return elements.get(id);}};
 Object.defineProperty(document,'cookie',{get(){return cookie;},set(value){++writes;cookie=value.includes('Max-Age=0')?'':value.split(';')[0];}});
 const context={document,location:{hostname:'127.0.0.1',search:'?phase='+phase},URLSearchParams,
 localStorage:{getItem:k=>storage.has(k)?storage.get(k):null,setItem(k,v){++writes;storage.set(k,v);},removeItem(k){++writes;storage.delete(k);}}};
 context.window=context;vm.runInNewContext(script,context);context.omniStartMediaTest();
 return context.omniFeatureResults;
}
assert(session('verify').every(r=>!r.pass));assert.equal(writes,0);
assert(session('write').every(r=>r.pass));const before=writes;
assert(session('verify').every(r=>r.pass));assert.equal(writes,before);
assert(session('cleanup').every(r=>r.pass));assert(session('verify').every(r=>!r.pass));
console.log('PASS fixture missing-state failure, write/read, read-only verification and scoped cleanup; actual browser restart untested');
