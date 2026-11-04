'use strict';
const M = Model, U = OmniUI, $ = id => document.getElementById(id);
window.OMNI_PREVIEW = !window.omnibloomHost;
let current = null, fetching = false, answering = false, active = true, generation = 0, seq = 0;
const kinds = ['storage', 'controller', 'camera', 'microphone', 'notifications'];
function controls() {
  $('next').disabled = !active || fetching || answering || !!current;
  $('deny').disabled = !active || answering || !current;
  $('allow').disabled = !active || answering || !current?.supported;
}
function focusSummary() { $('request-summary').tabIndex = -1; U.focus($('request-summary')); }
function closePrompt() { if (!$('prompt').hidden) U.close(); }
function cancel(message) {
  ++generation; current = null; closePrompt(); controls();
  if (active) {
    U.notify(message + (fetching || answering ? ' Waiting for the browser to finish the previous request.' : ''));
    if (document.activeElement === document.body || document.activeElement?.disabled) {
      if (!$('next').disabled) U.focus($('next')); else focusSummary();
    }
  }
}
async function next() {
  if (!active || fetching || answering || current) return;
  fetching = true;
  const ticket = generation, invoker = document.activeElement;
  const waiting = setTimeout(() => { if (active && ticket === generation) U.notify('The browser has not responded. Permission review is paused.'); }, 10000);
  controls();
  if (invoker === $('next')) focusSummary();
  try {
    const result = await U.request('permissions.next', {}, () => ({
      id: 'fixture-' + seq, navigationEpoch: 1, origin: 'https://example.org',
      kind: kinds[seq++ % 5], supported: seq <= 2, expiresAt: Date.now() + 60000
    }));
    if (!active || ticket !== generation) return;
    if (result === null) { U.notify('No permission requests.'); return; }
    current = M.validate(result);
    $('request-origin').textContent = current.origin;
    $('prompt-title').textContent = M.labels[current.kind] + '?';
    $('explain').textContent = 'This choice applies only to this request and this page.';
    $('unsupported').textContent = current.supported ? '' : 'Unavailable in this browser build. Access will be denied.';
    $('error').textContent = ''; controls();
    U.modal('prompt'); U.focus($('deny'));
    $('request-summary').textContent = 'A site is requesting ' + current.kind;
  } catch (_) {
    if (active && ticket === generation) U.notify('No valid permission request is available.');
  } finally {
    clearTimeout(waiting); fetching = false; controls();
    if (active && !current && (document.activeElement === $('request-summary') || document.activeElement === document.body)) U.focus($('next'));
  }
}
async function answer(decision) {
  if (!active || !current || answering) return;
  const request = current, ticket = generation;
  const waiting = setTimeout(() => { if (active && ticket === generation) U.notify('The browser has not confirmed this choice. Permission review is paused.'); }, 10000);
  answering = true; controls();
  $('prompt-title').tabIndex = -1; U.focus($('prompt-title'));
  try {
    const params = M.answer(request, decision, Date.now());
    const result = await U.request('permissions.respond', params, () => ({requestId: request.id, decision, applied: true}));
    if (!active || ticket !== generation || current !== request) return;
    if (result?.requestId !== request.id || result?.decision !== decision || result?.applied !== true) throw Error();
    current = null; closePrompt();
    U.notify(window.OMNI_PREVIEW ? 'Preview choice: ' + decision : decision === 'deny' ? 'Access denied.' : 'Allowed for this request.');
    $('request-summary').textContent = 'Request resolved.';
  } catch (_) {
    if (!active || ticket !== generation || current !== request) return;
    current = null; closePrompt();
    U.notify('The browser did not confirm the result. This request is closed.');
    $('request-summary').textContent = 'Request unavailable.';
  } finally {
    clearTimeout(waiting); answering = false; controls();
    if (active && !current && (document.activeElement === document.body || document.activeElement === $('request-summary') || document.activeElement?.disabled || !document.activeElement?.getClientRects().length)) U.focus($('next'));
  }
}
$('next').onclick = next;
$('deny').onclick = () => answer('deny');
$('allow').onclick = () => answer('allow-once');
window.handlePageController = action => {
  if (action === 'circle' && current) { answer('deny'); return true; }
  return false;
};
function expire() { if (active && current && Date.now() >= current.expiresAt) cancel(answering ? 'Request expired before the browser confirmed the result.' : 'Request expired. No choice was sent.'); }
let timer = setInterval(expire, 1000);
const navigationChanged = () => cancel('Page changed. Request cancelled.');
window.addEventListener('omni-navigation-changed', navigationChanged);
window.addEventListener('omnibloom-event', event => {
  if (event.detail?.version === 1 && event.detail.event === 'navigation.changed') navigationChanged();
});
window.addEventListener('pagehide', () => { active = false; clearInterval(timer); cancel(''); });
window.addEventListener('pageshow', () => {
  if (active) return;
  active = true; timer = setInterval(expire, 1000); controls();
  if (fetching || answering) U.notify('Waiting for the browser to finish the previous request. Permission review is paused.');
  if (!$('next').disabled) U.focus($('next'));
});
$('availability').textContent = window.OMNI_PREVIEW ? 'Preview queue: storage, controller, camera, microphone and notifications.' : 'Unsupported capabilities remain unavailable.';
controls(); U.focus($('next'));
