// Drives OMNI_YT_ATTEST_GUARD_V1's page script through a mocked fetch/clock with the three console patterns.
const fs=require('fs');const src=fs.readFileSync(__dirname+'/../title/OmniYtGuard.h','utf8');
const js=src.slice(src.indexOf('R"JS(')+5,src.indexOf(')JS"'));
function venc(n){if(n<128)return [n];if(n<16384)return [128|(n&63),n>>6];return [192|(n&31),(n>>5)&255,n>>13];}
function part(t,p){return [...venc(t),...venc(p.length),...p];}
function ump(st){return Uint8Array.from([...part(21,new Array(3000).fill(7)),...part(58,[0x08,st])]);}
async function scenario(name,steps,expect){
  let now=0,timers=[],said=[],reloads=0;const store={};
  const win={top:null,prompt:(m,v)=>{said.push(v);return null;},addEventListener(){},
    fetch:async(u)=>{const s=steps.shift();return new Response(s.body||ump(s.st),{status:200});}};
  win.top=win;
  const ctx={window:win,location:{hostname:'www.youtube.com',pathname:'/watch',search:'?v=abc',href:'https://www.youtube.com/watch?v=abc',reload:()=>reloads++},
    history:{state:null,replaceState(){}},sessionStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>store[k]=v,removeItem:k=>delete store[k]},
    performance:{now:()=>now*1000},setInterval:(f)=>timers.push(f),setTimeout:()=>{},document:{querySelector:()=>({currentTime:30})},
    XMLHttpRequest:function(){},URL,URLSearchParams,Uint8Array,Promise};
  ctx.XMLHttpRequest.prototype={open(){},send(){}};
  new Function(...Object.keys(ctx),js)(...Object.values(ctx));
  const f=win.fetch;
  const plan=expect.plan;
  for(const ev of plan){now=ev.t;
    if(ev.it){await f('https://www.youtube.com/api/jnn/v1/GenerateIT');}
    else if(ev.vp){await f('https://rr1---x.googlevideo.com/videoplayback?x');}
    await new Promise(r=>setTimeout(r,5));timers.forEach(t=>t());}
  const rl=said.filter(x=>/^reload/.test(x));
  const ok=rl.length===expect.reloads&&(!expect.kind||rl.every(x=>x.startsWith(expect.kind)));
  console.log((ok?'ok  ':'FAIL')+' '+name+': '+rl.join(' / ')+(rl.length?'':'(no reload)'));return ok;}
(async()=>{let all=true;
 // accepted: vp pending, GenerateIT, next vp attested -> no reload
 all&=await scenario('accepted',[{st:2},{},{st:1},{st:1}],{reloads:0,plan:[{t:13,vp:1},{t:14,it:1},{t:20,vp:1},{t:40,vp:1}]});
 // rejected token (mode B): vp after GenerateIT still pending -> plain reload at once
 all&=await scenario('rejected',[{st:2},{},{st:2}],{reloads:1,kind:'reloadn rejected',plan:[{t:13,vp:1},{t:15.8,it:1},{t:23.4,vp:1}]});
 // never minted (mode A): pending, no GenerateIT -> cache-bypass reload after 20 s
 all&=await scenario('no token',[{st:2},{st:2},{st:2}],{reloads:1,kind:'reload pending20s',plan:[{t:19.5,vp:1},{t:24,vp:1},{t:35,vp:1},{t:41,vp:0}]});
 // request in flight when GenerateIT answered (sent before it): not counted as rejected
 all&=await scenario('in-flight',[{st:2},{},{st:1}],{reloads:0,plan:[{t:13,vp:1},{t:14,it:1},{t:20,vp:1}]});
 process.exit(all?0:1);})();
