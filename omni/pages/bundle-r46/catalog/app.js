let available = [], installed = [], active = true, action = 0;
const generations = {installed: 0, catalog: 0}, list = document.getElementById('list');
const pending = {installed: 0, catalog: 0};
let stateError = null;
function syncState() {
  if (!active || !window.BloomScreenStates?.config('catalog#root')) return;
  const hasRows = Catalog.merge(available, installed).length > 0;
  const waiting = pending.installed || pending.catalog;
  const state = stateError || (waiting ? hasRows ? 'partial' : 'loading' : hasRows ? 'full' : 'empty');
  BloomScreenStates.show('catalog#root', state, {retain: hasRows});
}
function render() {
  const focused = document.activeElement, focusedId = list.contains(focused) ? focused.dataset.appId : null;
  const rows = Catalog.merge(available, installed);
  list.replaceChildren();
  document.getElementById('empty').hidden = rows.length > 0;
  for (const app of rows) {
    const card = document.createElement('article'); card.className = 'tile';
    const heading = document.createElement('h2'); heading.textContent = app.name;
    const summary = document.createElement('p'); summary.textContent = app.summary;
    const meta = document.createElement('p'); meta.textContent = (app.installed ? 'Installed · ' + app.version : 'Available') + ' · ' + app.license;
    const button = document.createElement('button'); button.textContent = 'Install via Setup'; button.dataset.appId = app.id;
    button.onclick = () => {
      document.getElementById('detail-title').textContent = app.name;
      document.getElementById('detail-text').textContent = 'On your computer, open Omnibloom Setup, check your PS5, then select ' + app.name + '. Review the release and install there.';
      const source = document.getElementById('source');
      if (app.source) source.href = app.source; else source.removeAttribute('href');
      source.textContent = app.source || 'Source not declared by this installed app';
      OmniUI.modal('details');
    };
    card.append(heading, summary, meta, button); list.append(card);
  }
  syncState();
  if (focusedId && document.getElementById('details').hidden) {
    const replacement = [...list.querySelectorAll('button')].find(button => button.dataset.appId === focusedId);
    OmniUI.focus(replacement || document.getElementById('refresh'));
  }
}
async function load(kind = 'installed') {
  if (!active) return;
  const ticket = ++generations[kind], statusTicket = ++action;
  pending[kind] = ticket; stateError = null; syncState();
  try {
    const result = await OmniUI.request(kind === 'installed' ? 'bloom.apps' : 'catalog.fetch', kind === 'installed' ? {} : {source: 'official'});
    if (!active || ticket !== generations[kind]) return;
    if (kind === 'installed') {
      const rows = Array.isArray(result) ? result : result?.apps;
      if (!Array.isArray(rows)) throw Error('Invalid installed apps');
      installed = rows;
    } else available = Catalog.validate(result);
    render();
    if (statusTicket === action) OmniUI.notify(kind === 'catalog' ? 'Catalog refreshed.' : '');
  } catch (error) {
    if (active && ticket === generations[kind] && statusTicket === action) {
      stateError = error?.message === 'DENIED' ? 'permission-denied' : 'error';
      OmniUI.notify(kind === 'catalog' ? 'Catalog unavailable.' : 'Installed apps unavailable.');
    }
  } finally {
    if (active && ticket === generations[kind]) { pending[kind] = 0; syncState(); }
  }
}
document.getElementById('refresh').onclick = () => load('installed');
document.getElementById('online').onclick = () => load('catalog');
function invalidate() { ++generations.installed; ++generations.catalog; ++action; pending.installed = pending.catalog = 0; stateError = null; syncState(); }
window.addEventListener('omnibloom-event', event => {
  if (event.detail?.version === 1 && event.detail.event === 'navigation.changed') invalidate();
});
window.addEventListener('pagehide', () => { active = false; invalidate(); if (!document.getElementById('details').hidden) OmniUI.close(); });
window.addEventListener('pageshow', () => { if (!active) { active = true; load(); } });
load();
