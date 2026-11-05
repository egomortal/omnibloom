/* Source-copy enhancement: preserve schema defaults, explicit Save and native validation. */
document.addEventListener('DOMContentLoaded',async()=>{
 BloomUI.addHelp({title:'Settings'});
 const section=document.querySelector('.card.compact'),searchLabel=BloomUI.node('label','',BloomUI.text('settings.search')),search=document.createElement('input');
 search.id='settings-search';search.maxLength=120;search.type='search';searchLabel.append(search);section.insertBefore(searchLabel,document.querySelector('#category-title'));
 const empty=BloomUI.node('p','',BloomUI.text('settings.empty')),status=BloomUI.node('p','settings-read-status','');empty.hidden=true;status.setAttribute('role','status');section.append(empty);section.insertBefore(status,searchLabel);
 const native=!!window.omnibloomHost, schema=new Map(settingsSchema.map(s=>[s.key,s]));
 let ready=!native,busy=false,writable=new Set(native?[]:settingsSchema.filter(s=>!s.readOnly).map(s=>s.key));
 const reset=BloomUI.node('button','',BloomUI.text('settings.reset'));reset.id='reset-section';document.querySelector('#save').parentElement.append(reset);
 function valid(s,v){return typeof v===typeof s.value && (s.kind!=='number'||Number.isFinite(v)&&v>=s.min&&v<=s.max) && (!s.options||s.options.includes(v))}
 function validate(result,reading){
  if(!result||!Number.isSafeInteger(result.revision)||result.revision<1||reading&&result.schemaVersion!==1||!result.values||typeof result.values!=='object'||Array.isArray(result.values))throw Error('Settings response is unsupported. Changes were not confirmed.');
  for(const[k,v]of Object.entries(result.values)){const s=schema.get(k);if(s&&!valid(s,v))throw Error('Invalid settings response: '+k)}
  if(!reading){if(result.revision<=revision)throw Error('Settings revision did not advance.');for(const k of writable)if(!Object.hasOwn(result.values,k))throw Error('Incomplete settings confirmation.');}
  return result;
 }
 function refresh(){
  const query=search.value.trim().toLocaleLowerCase();let visible=0;
  for(const row of document.querySelectorAll('.settings-row')){const input=row.querySelector('[data-key]'),s=schema.get(input.dataset.key);row.hidden=!!query&&!`${s.label} ${s.group} ${s.key}`.toLocaleLowerCase().includes(query);if(!row.hidden)visible++;input.disabled=input.tagName==='A'&&input.hasAttribute('data-native-preference')?false:busy||!ready||s.readOnly||!writable.has(s.key)}
  empty.hidden=visible>0;document.querySelector('#category-title').textContent=query?'Search results':group;
  reset.disabled=busy||!ready||!!query||!settingsSchema.some(s=>s.group===group&&!s.danger&&!s.readOnly&&writable.has(s.key));
  document.querySelector('#save').disabled=busy||!ready;document.querySelector('#discard').disabled=busy||!ready;
 }
 const originalDraw=draw;draw=function(){originalDraw();refresh()};
 search.oninput=()=>{window.r4SettingsQuery=search.value.trim();draw()};
 reset.onclick=()=>{if(reset.disabled)return;for(const[k,v]of Object.entries(BloomState.sectionDefaults(settingsSchema,group)))if(writable.has(k))values[k]=v;draw();r2.toast('Default values are ready. Save changes to apply them.');obUI.focus(reset)};
 const request=r2.request.bind(r2);
 r2.request=async(method,params,mock)=>{
  if(method!=='settings.write')return request(method,params,mock);
  if(!ready||busy)throw Error('Settings are not ready.');
  for(const[k,v]of Object.entries(params.changes))if(!writable.has(k)||!valid(schema.get(k),v))throw Error('This setting is unavailable.');
  busy=true;refresh();try{const result=validate(await request(method,params,mock),false);return{...result,values:{...saved,...result.values}}}finally{busy=false;refresh()}
 };
 document.querySelector('#danger').addEventListener('toggle',()=>{if(document.querySelector('#danger').open)document.querySelector('#danger-cancel').focus()});
 status.textContent=native?'Loading saved settings…':'Local preview — defaults are not console settings.';refresh();
 if(native)try{const result=validate(await request('settings.read',{}),true);writable=new Set(Object.keys(result.values).filter(k=>schema.has(k)&&!schema.get(k).readOnly));values={...values,...Object.fromEntries(Object.entries(result.values).filter(([k])=>schema.has(k)))};saved={...values};revision=result.revision;ready=true;status.textContent='Saved settings loaded. Unavailable controls stay disabled.';draw()}catch(e){status.textContent='Saved settings unavailable. Reload to try again. '+e.message;refresh()}
});
