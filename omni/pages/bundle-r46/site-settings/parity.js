document.addEventListener('DOMContentLoaded',async()=>{
 const ids=['ads','javascript','controller'],panel=document.querySelector('#site-panel'),status=document.querySelector('#status'),native=!!window.omnibloomHost;
 const label=document.createElement('label');label.textContent='Search settings';const search=document.createElement('input');search.type='search';search.id='site-search';search.maxLength=120;label.append(search);panel.prepend(label);
 const reset=document.createElement('button');reset.id='reset-section';reset.textContent='Reset section';panel.querySelector('.row').append(reset);
 let ready=!native,busy=false,defaults=native?null:{ads:true,javascript:true,controller:false},saved=Object.fromEntries(ids.map(id=>[id,document.getElementById(id).checked]));
 const empty=document.createElement('p');empty.textContent='No matching settings.';empty.hidden=true;panel.append(empty);
 function refresh(){let count=0;for(const id of ids){const input=document.getElementById(id);input.disabled=!ready||busy;input.closest('label').hidden=!input.closest('label').textContent.toLowerCase().includes(search.value.trim().toLowerCase());if(!input.closest('label').hidden)count++}empty.hidden=count>0;reset.disabled=!ready||busy||!defaults||!!search.value.trim()}
 search.oninput=refresh;
 function validValues(value){return value&&ids.every(id=>typeof value[id]==='boolean')}
 async function write(changes){if(!ready||busy)return;busy=true;refresh();try{const r=await r2.request('site.settings.write',{origin,revision,changes},()=>({revision:revision+1,values:{...saved,...changes}}));if(!r||!Number.isSafeInteger(r.revision)||r.revision<=revision||!validValues(r.values))throw Error('Changes were not confirmed by the host.');revision=r.revision;saved=Object.fromEntries(ids.map(id=>[id,r.values[id]]));status.textContent=native?'Site settings saved.':'Saved in local preview.'}catch(e){status.textContent=e.message}finally{for(const id of ids)document.getElementById(id).checked=saved[id];busy=false;refresh()}}
 for(const id of ids)document.getElementById(id).onchange=()=>write({[id]:document.getElementById(id).checked});
 reset.onclick=()=>{if(!reset.disabled)write({...defaults})};
 status.textContent=native?'Loading site settings…':'Local preview — resets permission toggles only.';refresh();
 if(native)try{const r=await r2.request('site.settings.read',{origin});if(!r||r.origin!==origin||!Number.isSafeInteger(r.revision)||r.revision<1||!validValues(r.values))throw Error('Unsupported site settings response.');revision=r.revision;saved=Object.fromEntries(ids.map(id=>[id,r.values[id]]));defaults=validValues(r.defaults)?Object.fromEntries(ids.map(id=>[id,r.defaults[id]])):null;for(const id of ids)document.getElementById(id).checked=saved[id];ready=true;status.textContent=defaults?'Saved site settings loaded.':'Saved settings loaded. Reset needs defaults from the host.';refresh()}catch(e){status.textContent='Site settings unavailable. '+e.message;refresh()}
});
