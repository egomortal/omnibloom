let saved=Themes.normalize({}),preview=saved,ready=false,busy=false,dirty=false,draft=0,active=true,session=0,deferred=false;const list=document.getElementById('list'),apply=document.getElementById('apply');apply.disabled=true;
const label=document.createElement('label');label.textContent='Search settings';const search=document.createElement('input');search.id='theme-search';search.type='search';search.maxLength=120;label.append(search);document.querySelector('.toolbar').prepend(label);
const resetSection=document.createElement('button');resetSection.id='reset-section';resetSection.textContent='Reset section';document.querySelector('.toolbar .row').append(resetSection);
function update(){const lostApply=document.activeElement===apply;let visible=0;for(const card of list.children){card.hidden=!card.textContent.toLowerCase().includes(search.value.trim().toLowerCase());if(!card.hidden)visible++}document.getElementById('empty').hidden=visible>0;document.getElementById('empty').textContent='No matching themes.';resetSection.disabled=busy||!!search.value.trim();apply.disabled=!ready||busy;if(lostApply&&apply.disabled&&active)document.getElementById('reset').focus()}
search.oninput=update;
Object.keys(Themes.themes).forEach(key=>{const card=document.createElement('article');card.className='tile';const h=document.createElement('h2');h.textContent={'silver-blue':'Silver blue',aurora:'Aurora',ember:'Ember'}[key];const p=document.createElement('p');p.textContent='Shared across your apps';const b=document.createElement('button');b.textContent='Preview';b.onclick=()=>{if(!active)return;dirty=true;draft++;preview={...saved,theme:key,accent:null};Themes.apply(document,preview);OmniUI.notify(h.textContent+' preview')};card.append(h,p,b);list.append(card)});
apply.onclick=async()=>{
 if(!active||!ready||busy)return;
 const owner=session,submitted={...preview},restore=document.activeElement===apply;
 busy=true;++generation;update();if(restore)document.getElementById('reset').focus();
 const fallback=document.activeElement;
 try{
  await OmniUI.request('settings.patch',{theme:submitted.theme,accent:submitted.accent});
  if(active&&owner===session){saved=submitted;dirty=preview.theme!==submitted.theme||preview.accent!==submitted.accent;OmniUI.notify('Theme saved.')}
 }catch(_){if(active&&owner===session)OmniUI.notify('Could not save. Your preview is still visible.')}
 finally{
  busy=false;update();
  if(active&&owner===session&&restore&&document.activeElement===fallback&&!apply.disabled)apply.focus();
  if(active&&deferred){deferred=false;read();}
 }
};
document.getElementById('reset').onclick=()=>{if(!active)return;draft++;dirty=false;preview={...saved};Themes.apply(document,preview);OmniUI.notify('Saved theme restored.')};
resetSection.onclick=()=>{if(!active||resetSection.disabled)return;draft++;dirty=true;preview={...saved,theme:Themes.normalize({}).theme,accent:null};Themes.apply(document,preview);OmniUI.notify('Default theme is ready. Apply theme to save it.')};
let generation=0;
async function read(){
 if(!active)return;
 if(busy){deferred=true;return;}
 const ticket=++generation,owner=session,startedDraft=draft;update();
 try{
  const s=await OmniUI.request('bloom.settings',{});
  if(!active||owner!==session||ticket!==generation)return;
  if(!s||typeof s!=='object'||!Object.hasOwn(Themes.themes,s.theme))throw Error('Unsupported settings');
  saved=Themes.normalize(s);
  if(!dirty&&draft===startedDraft)preview={...saved};else preview={...preview,motion:saved.motion};Themes.apply(document,preview);
  ready=true;OmniUI.notify(dirty?'Saved settings refreshed. Your preview is unchanged.':'Saved theme loaded.');
 }catch(_){if(active&&owner===session&&ticket===generation){ready=false;OmniUI.notify('Preview only. Saved settings are unavailable.');}}
 if(active&&owner===session&&ticket===generation)update();
}
window.onBloomEvent=e=>{if(['theme.changed','settings.changed','resync'].includes(e?.type))read()};
window.addEventListener('pagehide',()=>{active=false;session++;generation++;ready=false;deferred=true;update()});
window.addEventListener('pageshow',()=>{if(active)return;active=true;session++;deferred=false;read()});
read();
