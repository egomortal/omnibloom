// Host test for OMNI_YT_ATTEST_GUARD_V1's streaming UMP walk (Ump + pbStatus), extracted from OmniYtGuard.h.
const fs=require('fs');const src=fs.readFileSync(__dirname+'/../title/OmniYtGuard.h','utf8');
const js=src.slice(src.indexOf('R"JS(')+5,src.indexOf(')JS"'));
const body=js.slice(js.indexOf('function pbStatus'),js.indexOf('var cur=null;'));
const {Ump,pbStatus}=new Function(body+';return {Ump:Ump,pbStatus:pbStatus};')();
function venc(n){if(n<128)return [n];if(n<16384)return [128|(n&63),n>>6];if(n<2097152)return [192|(n&31),(n>>5)&255,n>>13];if(n<268435456)return [224|(n&15),(n>>4)&255,(n>>12)&255,n>>20];return [240,n&255,(n>>8)&255,(n>>16)&255,(n>>24)&255];}
function part(t,p){return [...venc(t),...venc(p.length),...p];}
function filler(n){return Array.from({length:n},(_,i)=>i&255);}
let fail=0,ok=0;function eq(a,b,m){if(a===b)ok++;else{fail++;console.log('FAIL',m,a,b);}}
function run(bytes,chunks){const u=new Ump();let i=0;const b=Uint8Array.from(bytes);for(const c of chunks){if(u.feed(b.subarray(i,i+c)))break;i+=c;}if(i<b.length&&!u.done)u.feed(b.subarray(i));return u.st;}
function splits(len){const r=[];let left=len;while(left>0){const c=1+Math.floor(Math.random()*Math.min(left,9000));r.push(c);left-=c;}return r;}
const sps=(s,extra=[])=>[0x08,s,...extra];
for(const s of [1,2,3]){
 const a=[...part(20,filler(30)),...part(21,filler(20000)),...part(58,sps(s)),...part(21,filler(300000))];
 const b=[...part(35,[0x20,0xd0,0x0f]),...part(21,filler(2000000)),...part(58,sps(s,[0x10,5]))];
 const c=[...part(58,[0x10,7,0x08,s])];                       // field order swapped
 for(let k=0;k<25;k++){eq(run(a,splits(a.length)),s,'a'+s);eq(run(b,splits(b.length)),s,'b'+s);eq(run(c,splits(c.length)),s,'c'+s);}
 eq(run(a,[1,1,1,1,1,1,1,1,1,1,1,1]),s,'byte-by-byte head');
}
const none=[...part(21,filler(5000)),...part(35,[0x20,1])];eq(run(none,splits(none.length)),null,'no part 58');
const big=[...part(21,filler(300000000>>12)),...part(58,sps(2))];eq(run(big,[big.length]),2,'one chunk');
eq(pbStatus([0x08,0x96,0x01]),150,'varint status');
console.log(`guard ump test: ${ok} ok, ${fail} failures`);process.exit(fail?1:0);
