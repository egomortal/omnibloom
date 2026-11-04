(function () {
  'use strict';
  const $ = id => document.getElementById(id), host = window.obTranslateHost;
  let context = null, pending = false, loading = true, active = true;
  let readGeneration = 0, operation = 0, consent = null, unsubscribe = null, subscribed = false;
  let restoreFocus = false;
  let subscriptionEpoch = 0;
  const available = host && typeof host.snapshot === 'function' && typeof host.execute === 'function';
  function message(text) { $('status').textContent = text; }
  function controls() {
    const focusedBefore = document.activeElement;
    $('translate').disabled = !active || loading || pending || !context?.eligible || context.translated;
    $('restore').disabled = !active || loading || pending || !context?.translated || !context.canGoBack;
    if (active && focusedBefore?.disabled && (focusedBefore === $('translate') || focusedBefore === $('restore'))) {
      $('page-title').tabIndex = -1;
      obUI.focus($('page-title'));
      restoreFocus = true;
    }
    if (active && !loading && !pending && restoreFocus) {
      const focused = document.activeElement;
      if (!focused || focused === document.body || focused === $('page-title') || focused.disabled || !focused.getClientRects().length) {
        const target = !$('translate').disabled ? $('translate') : !$('restore').disabled ? $('restore') : $('page-title');
        if (target === $('page-title')) target.tabIndex = -1;
        obUI.focus(target);
      }
      restoreFocus = false;
    }
  }
  function cancelConsent() {
    consent = null;
    if ($('consent').open) {
      restoreFocus = restoreFocus || $('consent').contains(document.activeElement);
      $('consent').close();
    }
  }
  async function refresh() {
    if (!active || !available) return;
    const ticket = ++readGeneration;
    // A navigation notification must invalidate consent before snapshot resolves.
    cancelConsent();
    loading = true;
    controls();
    try {
      const next = obTranslateModel.normalize(await host.snapshot());
      if (!active || ticket !== readGeneration) return;
      if (context && (next.documentId !== context.documentId || next.url !== context.url)) {
        ++operation;
        pending = false;
      }
      context = next;
      $('page-title').textContent = context.title;
      $('page-origin').textContent = context.origin;
      $('page-language').textContent = 'Page language: ' + context.language;
      $('service-state').textContent = context.translated ? 'Translation is open.' : 'Translation opens after your confirmation.';
    } catch (_) {
      if (!active || ticket !== readGeneration) return;
      context = null;
      ++operation;
      pending = false;
      message('The browser could not provide the current page.');
    } finally {
      if (active && ticket === readGeneration) { loading = false; controls(); }
    }
  }
  async function run(command, restore) {
    if (!active || loading || pending || !context || command.documentId !== context.documentId) return;
    const ticket = ++operation, documentGeneration = readGeneration;
    pending = true;
    controls();
    try {
      const result = await host.execute(command);
      if (!active || ticket !== operation || documentGeneration !== readGeneration) return;
      if (!result || result.accepted !== true) throw new Error();
      message(restore ? 'Returning to the previous page…' : 'Opening Google Translate…');
    } catch (_) {
      if (active && ticket === operation && documentGeneration === readGeneration)
        message('The page changed or translation could not start. Try again.');
    } finally {
      if (active && ticket === operation) { pending = false; await refresh(); }
    }
  }
  $('translate').addEventListener('click', () => {
    if ($('translate').disabled) return;
    try {
      consent = { command: Object.freeze(obTranslateModel.command(context, false)), generation: readGeneration, origin: context.origin };
      $('consent-origin').textContent = consent.origin;
      obUI.openDialog('consent');
    } catch (error) { message(error.message); }
  });
  $('confirm').addEventListener('click', () => {
    const captured = consent;
    if (!$('consent').open || !captured || captured.generation !== readGeneration) return;
    cancelConsent();
    obUI.focus($('translate'));
    run(captured.command, false);
  });
  $('consent').addEventListener('close', () => { if (!$('consent').open) consent = null; });
  $('restore').addEventListener('click', () => {
    if ($('restore').disabled) return;
    try { run(Object.freeze(obTranslateModel.command(context, true)), true); }
    catch (error) { message(error.message); }
  });
  document.addEventListener('focusin', event => document.querySelectorAll('.pad-focus').forEach(element => {
    if (element !== event.target) element.classList.remove('pad-focus');
  }));
  function subscribe() {
    if (!subscribed && available && typeof host.subscribe === 'function') {
      const epoch = ++subscriptionEpoch;
      try {
        unsubscribe = host.subscribe(() => { if (epoch === subscriptionEpoch && active) refresh(); });
        subscribed = true;
      } catch (_) {
        ++subscriptionEpoch;
        message('Live page updates are unavailable. Reopen this panel after changing pages.');
      }
    }
  }
  window.addEventListener('omnibloom-event', event => {
    if (event.detail?.version === 1 && event.detail.event === 'navigation.changed') refresh();
  });
  window.addEventListener('pagehide', () => {
    active = false; ++readGeneration; ++operation; pending = false; loading = true;
    cancelConsent(); controls();
    if (typeof unsubscribe === 'function') {
      try { unsubscribe(); subscribed = false; ++subscriptionEpoch; }
      catch (_) { /* Keep the existing gated callback rather than duplicate it. */ }
    }
    unsubscribe = null;
  });
  window.addEventListener('pageshow', () => {
    if (active) return;
    active = true; subscribe(); refresh();
  });
  if (available) { subscribe(); refresh(); }
  else message('Translation is available when this panel is opened by Omni.');
  window.obTranslationUI = { refresh };
})();
