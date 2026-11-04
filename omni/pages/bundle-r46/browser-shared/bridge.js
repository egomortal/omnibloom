window.r2={
 async request(method,payload,mock){if(window.omnibloomHost&&typeof window.omnibloomHost.request==='function'){const r=await window.omnibloomHost.request({version:1,id:crypto.randomUUID?crypto.randomUUID():String(Date.now()),method,params:payload});if(!r||r.ok!==true)throw new Error(r?.code||'REQUEST_FAILED');return r.result}if(window.omnibloomHost)throw new Error("UNSUPPORTED");return mock?mock(payload):null},
 toast(t){obUI.toast(t)},escape(s){const p=document.createElement('span');p.textContent=String(s);return p.innerHTML},
 url(s){try{const u=new URL(s);return ['http:','https:'].includes(u.protocol)?u.href:null}catch(e){return null}},
 focus(){obUI.focus(document.querySelector('[data-initial]')||obUI.items()[0])}
};