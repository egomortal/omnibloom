/* Local navigation command matcher. Deterministic rules, not an AI model. */
(function (root, factory) {
  'use strict';
  var commands = factory();
  if (typeof module === 'object' && module.exports) module.exports = commands;
  else root.OmniNavigationCommands = commands;
})(typeof globalThis !== 'undefined' ? globalThis : window, function () {
  'use strict';
  var VERSION = '1.0.0-local-prototype';
  var MAX_INPUT = 4096;
  var routes = [
    { id: 'launch', name: 'Launch', aliases: ['launch', 'home', 'dashboard', 'start screen'] },
    { id: 'queue', name: 'Queue', aliases: ['queue', 'downloads', 'transfers', 'download list'] },
    { id: 'library', name: 'Saved links', aliases: ['saved links', 'library', 'bookmarks', 'saved urls'] },
    { id: 'activity', name: 'Activity', aliases: ['activity', 'history', 'recent activity', 'recents'] },
    { id: 'settings', name: 'Settings', aliases: ['settings', 'preferences', 'options'] }
  ];
  var collections=[
    {id:'originals',name:'Original styles',aliases:['original styles','original themes','original universes']}
  ];
  var themes = [
    ['bloom', 'Bloom', ['bloom', 'petals']], ['relay', 'Relay', ['relay', 'patchboard']],
    ['loom', 'Loom', ['loom', 'threads']], ['kinetic', 'Kinetic', ['kinetic', 'counterweight']],
    ['tide', 'Tide', ['tide', 'tide table']],
    ['aurora', 'Aurora', ['aurora']], ['cosmic', 'Cosmic', ['cosmic']],
    ['arcade', 'Arcade', ['arcade']], ['solstice', 'Solstice', ['solstice']],
    ['metro', 'Metro', ['metro']], ['sakura', 'Sakura', ['sakura']],
    ['abyss', 'Abyss', ['abyss']], ['prism', 'Prism', ['prism']],
    ['atlas', 'Atlas', ['atlas']], ['cassette', 'Cassette', ['cassette', 'tape deck']]
  ].map(function (row) { return { id: row[0], name: row[1], aliases: row[2] }; });

  function normalize(value) {
    return value.normalize('NFKC').toLowerCase().replace(/[’']/g, '').replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim();
  }
  function mentions(text, alias) { return (' ' + text + ' ').indexOf(' ' + normalize(alias) + ' ') !== -1; }
  function frozenAction(kind, value, label, description) {
    var action = { kind: kind, label: label, description: description };
    if (value !== undefined) action.value = value;
    return Object.freeze(action);
  }
  function routeAction(route) { return frozenAction('navigate', route.id, 'Open ' + route.name, 'Open this page. No transfer starts.'); }
  function themeAction(theme) { return frozenAction('theme', theme.id, 'Switch to ' + theme.name, 'Change the interface theme. Your queue stays in place.'); }
  function collectionAction(collection) { return frozenAction('collection',collection.id,'Browse '+collection.name,'Open this theme collection. No transfer starts.'); }
  function helpAction() { return frozenAction('help', undefined, 'Open the Quick guide', 'Read the guide for your current theme.'); }
  function result(status, message, actions) {
    return Object.freeze({ status: status, message: message, actions: Object.freeze(actions || []), deterministic: true, modelConnected: false });
  }
  function validateUrl(value) {
    if (typeof value !== 'string' || value.length > MAX_INPUT) return null;
    if (!/^https?:\/\//i.test(value) || /[\u0000-\u0020\u007f<>"`\\]/.test(value)) return null;
    var authority = value.match(/^https?:\/\/([^/?#]*)/i);
    if (!authority || authority[1].indexOf('@') !== -1) return null;
    try {
      var url = new URL(value);
      if (!url.hostname || url.username || url.password || !['http:', 'https:'].includes(url.protocol)) return null;
      return url.href.length <= MAX_INPUT * 3 ? value : null;
    } catch (_) { return null; }
  }
  function validateAction(action) {
    if (!action || typeof action !== 'object' || Array.isArray(action)) return null;
    try {
      if (action.kind === 'help') return helpAction();
      if (action.kind === 'navigate') {
        var route = routes.find(function (item) { return item.id === action.value; });
        return route ? routeAction(route) : null;
      }
      if (action.kind === 'theme') {
        var theme = themes.find(function (item) { return item.id === action.value; });
        return theme ? themeAction(theme) : null;
      }
      if(action.kind==='collection') {
        var collection=collections.find(function(item){return item.id===action.value;});
        return collection?collectionAction(collection):null;
      }
      if (action.kind === 'fill-url') {
        var url = validateUrl(action.value);
        return url ? frozenAction('fill-url', url, 'Prepare this link', 'Fill the Add link form only. Choose an engine and start it yourself.') : null;
      }
    } catch (_) { return null; }
    return null;
  }
  function namedActions(words) {
    var actions = [];
    routes.forEach(function (route) { if (route.aliases.some(function (alias) { return mentions(words, alias); })) actions.push(routeAction(route)); });
    themes.forEach(function (theme) { if (theme.aliases.some(function (alias) { return mentions(words, alias); })) actions.push(themeAction(theme)); });
    collections.forEach(function(collection){if(collection.aliases.some(function(alias){return mentions(words,alias);}))actions.push(collectionAction(collection));});
    var help = ['help', 'guide', 'instructions', 'how do i navigate', 'what can you do'];
    if (help.some(function (alias) { return mentions(words, alias); })) actions.push(helpAction());
    return actions;
  }
  function parse(value) {
    if (typeof value !== 'string') return result('invalid', 'Type a destination, theme name or complete web link.');
    if (value.length > MAX_INPUT) return result('invalid', 'That command is too long. Try one short request or a single web link.');
    if (/[\u0000-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/.test(value) || /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/.test(value)) return result('invalid', 'Use a single line of ordinary text.');
    var trimmed = value.trim();
    if (!trimmed) return result('unknown', 'Try “open Queue”, “switch to Tide”, or paste a link.', [helpAction()]);
    var urls = trimmed.match(/https?:\/\/[^\s<>"`]+/gi) || [];
    var withoutUrls = trimmed.replace(/https?:\/\/[^\s<>"`]+/gi, ' ');
    var words = normalize(withoutUrls);
    if (/\b(?:delete|remove|erase|wipe|clear|cancel|pause|resume|retry|install|uninstall|deploy|reboot|shutdown|execute|eval|submit)\b/.test(words) || /\brun\b/.test(words) || /\bstart (?:a |the |all )?(?:download|transfer)s?\b/.test(words)) {
      return result('unsupported', 'This helper only navigates or prepares a link. Manage transfers with their visible controls.', [helpAction()]);
    }
    if (/\b(?:not|dont|never|avoid|except|ignore)\b/.test(words)) return result('unknown', 'Tell me the destination you want to open, without exclusions or extra instructions.', [helpAction()]);
    if (urls.length > 1) return result('ambiguous', 'I found more than one link. Paste just the one you want to prepare.', [helpAction()]);
    if (urls.length === 1) {
      var suffix = trimmed.slice(trimmed.indexOf(urls[0]) + urls[0].length).trim();
      if ((/^https?:\/\//i.test(trimmed) && /\s/.test(trimmed)) || (suffix && !namedActions(normalize(suffix)).length && !/^(?:please|for me|(?:in|into) (?:the )?(?:add link )?form)[.!?]?$/i.test(suffix))) {
        return result('invalid', 'That link may contain an unescaped space. Paste one complete link; use %20 for a space inside its URL.');
      }
      var url = validateUrl(urls[0]);
      if (!url || /[<>`]/.test(trimmed)) return result('invalid', 'Use a complete HTTP or HTTPS link without sign-in details, spaces or markup.');
      var draft = validateAction({ kind: 'fill-url', value: url });
      var others = namedActions(words);
      if (others.length) return result('ambiguous', 'I found a link and a named destination. Choose which action you meant.', [draft].concat(others));
      return result('ready', 'I can prepare this link in the form. Nothing will be downloaded until you start it yourself.', [draft]);
    }
    if (/\bhttps?:/i.test(trimmed)) return result('invalid', 'Use a complete HTTP or HTTPS link with a hostname.');
    if (/(?:javascript|data|file|ftp):/i.test(trimmed)) return result('invalid', 'Only HTTP and HTTPS links can be prepared.');
    var actions = namedActions(words);
    if (actions.length > 1) return result('ambiguous', 'That could mean a few things. Choose exactly what you want to open.', actions);
    if (actions.length === 1) return result('ready', 'Here is the matching action. Choose it to continue.', actions);
    if (/\b(?:theme|themes|universe|universes|look|looks)\b/.test(words)) return result('ambiguous', 'Which theme would you like? Choose one, or type its name.', themes.map(themeAction));
    return result('unknown', 'I did not find an exact destination. Try a page name, a theme name, or ask for help.', [helpAction()]);
  }

  routes.forEach(function (item) { Object.freeze(item.aliases); Object.freeze(item); });
  themes.forEach(function (item) { Object.freeze(item.aliases); Object.freeze(item); });
  collections.forEach(function(item){Object.freeze(item.aliases);Object.freeze(item);});
  return Object.freeze({ version: VERSION, parse: parse, validateAction: validateAction, validateUrl: validateUrl,
    routes: Object.freeze(routes), themes: Object.freeze(themes), collections:Object.freeze(collections), limits: Object.freeze({ inputCharacters: MAX_INPUT }) });
});

/* Optional manual navigation assistant UI. Deterministic matcher; no AI connection. */
(function (root) {
  'use strict';
  var commands = root.OmniNavigationCommands;
  if (!commands) return;
  function install(options) {
    options = options || {};
    var doc = options.document || root.document;
    if (!doc || doc.getElementById('navigation-assistant-dialog')) return null;
    var mount = options.mount || doc.querySelector('.app-footer');
    if (typeof mount === 'string') mount = doc.querySelector(mount);
    if (!mount) return null;
    function make(tag, text, className) {
      var node = doc.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    }
    var launch = make('button', 'Find my way', 'text-button navigation-helper-launch');
    launch.id = 'navigation-assistant-toggle'; launch.type = 'button';
    launch.setAttribute('aria-haspopup', 'dialog'); launch.setAttribute('aria-controls', 'navigation-assistant-dialog');
    var dialog = make('dialog', undefined, 'navigation-helper-dialog');
    dialog.id = 'navigation-assistant-dialog';
    dialog.setAttribute('aria-labelledby', 'navigation-assistant-heading');
    dialog.setAttribute('aria-describedby', 'navigation-assistant-boundary');
    var header = make('div', undefined, 'dialog-heading');
    var titles = make('div'); titles.append(make('span', 'A HELPFUL WAY AROUND', 'eyebrow'));
    var title = make('h2', 'Where would you like to go?'); title.id = 'navigation-assistant-heading'; titles.append(title);
    var close = make('button', '×', 'icon-button navigation-helper-close'); close.type = 'button';
    close.id = 'navigation-assistant-close'; close.setAttribute('aria-label', 'Close navigation helper');
    header.append(titles, close);
    var boundary = make('p', 'Local command matcher · no AI model connected. Choose a suggested action before anything changes.', 'navigation-helper-boundary');
    boundary.id = 'navigation-assistant-boundary';
    var form = make('form'); form.id = 'navigation-assistant-form';
    var label = make('label', 'A page, a theme, or one link'); label.htmlFor = 'navigation-assistant-input';
    var inputRow = make('div', undefined, 'navigation-helper-input-row');
    var input = make('input'); input.id = 'navigation-assistant-input'; input.type = 'text';
    input.placeholder = 'Try “open Queue” or “switch to Tide”'; input.maxLength = commands.limits.inputCharacters;
    input.autocomplete = 'off'; input.spellcheck = false;
    input.setAttribute('aria-describedby', 'navigation-assistant-privacy');
    var submit = make('button', 'Find a match', 'primary-button'); submit.type = 'submit';
    inputRow.append(input, submit);
    var privacy = make('p', 'Commands are matched in this page. Links only fill the form; this helper never starts, cancels or deletes a transfer.', 'navigation-helper-small');
    privacy.id = 'navigation-assistant-privacy';
    form.append(label, inputRow, privacy);
    var examples = make('div', undefined, 'navigation-helper-examples'); examples.setAttribute('aria-label', 'Example commands');
    ['Open Queue', 'Show saved links', 'Switch to Tide', 'Help'].forEach(function (text) {
      var button = make('button', text, 'secondary-button'); button.type = 'button';
      button.addEventListener('click', function () { input.value = text; analyze(); }); examples.append(button);
    });
    var status = make('p', 'Ready when you are.', 'navigation-helper-status'); status.id = 'navigation-assistant-status';
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    var results = make('ul', undefined, 'navigation-helper-results'); results.id = 'navigation-assistant-results';
    results.setAttribute('aria-label', 'Suggested actions');
    var foot = make('p', 'This helper changes navigation or prepares a link for review. It never submits a download, deletes a record, or fetches a source.', 'navigation-helper-small');
    dialog.append(header, boundary, form, examples, status, results, foot);
    var before = mount.querySelector('#help-toggle') || mount.querySelector('#preview-info'); mount.insertBefore(launch, before);
    doc.body.append(dialog);
    var opener = null, restoreOnClose = true, busy = false;
    function closeDialog(restore) { restoreOnClose = restore !== false; dialog.close(); }
    function bridge() { return options.bridge || root.OmniNavigatorHost || {}; }
    function report(message) { status.textContent = message; }
    function draftConflict(action, token) {
      results.replaceChildren();
      report('There is already a different link in the Add form. Replace that draft, or keep it? Nothing has changed.');
      var replaceItem = make('li'), keepItem = make('li');
      var replace = make('button', 'Replace existing draft', 'navigation-helper-action'); replace.type = 'button';
      var keep = make('button', 'Keep existing draft', 'navigation-helper-action'); keep.type = 'button';
      replace.addEventListener('click', function () { apply(action, replace, token); });
      keep.addEventListener('click', function () { results.replaceChildren(); report('Your existing draft is kept. You can keep exploring.'); input.focus(); });
      replaceItem.append(replace); keepItem.append(keep); results.append(replaceItem, keepItem); replace.focus();
    }
    async function apply(proposal, button, confirmationToken) {
      var action = commands.validateAction(proposal);
      if (!action || busy) return;
      var adapter = bridge();
      if (action.kind === 'theme' && typeof adapter.setTheme !== 'function') return report('Theme switching is not connected in this prototype yet. Choose it in Change universe.');
      if (action.kind === 'fill-url' && typeof adapter.prepareLink !== 'function') return report('Form preparation is not connected yet. Copy the link into Add a link yourself.');
      if (action.kind === 'help' && !doc.getElementById('help-toggle') && typeof adapter.help !== 'function') return report('The Quick guide is not connected in this standalone example.');
      busy = true; button.disabled = true; input.disabled = true; submit.disabled = true;
      restoreOnClose = false;
      try {
        if (action.kind === 'navigate') {
          closeDialog(false);
          root.dispatchEvent(new root.CustomEvent('omni:navigate', { detail: { route: action.value } }));
        } else if(action.kind==='collection') {
          closeDialog(false);
          root.dispatchEvent(new root.CustomEvent('omni:collection',{detail:{collection:action.value}}));
        } else if (action.kind === 'theme') {
          var changed = await adapter.setTheme(action.value);
          if (!changed || changed.ok !== true) { restoreOnClose = true; return report('That theme could not be opened. Use Change universe to choose it.'); }
          if (dialog.open) closeDialog(false);
        } else if (action.kind === 'fill-url') {
          var prepared = await adapter.prepareLink(action.value, { replaceDraft: !!confirmationToken, confirmationToken: confirmationToken });
          if (prepared && prepared.ok === false && prepared.reason === 'draft-exists' && typeof prepared.confirmationToken === 'string' && prepared.confirmationToken.length > 0 && prepared.confirmationToken.length <= 256) {
            restoreOnClose = true; draftConflict(action, prepared.confirmationToken); return;
          }
          if (!prepared || prepared.ok !== true) { restoreOnClose = true; return report('That link could not be prepared. Use the regular Add link form to continue.'); }
          if (dialog.open) closeDialog(false);
        } else {
          closeDialog(false);
          if (typeof adapter.help === 'function') await adapter.help();
          else { var helpButton = doc.getElementById('help-toggle'); helpButton.focus(); helpButton.click(); }
        }
      } catch (_) {
        if (!dialog.open) { dialog.showModal(); input.focus(); }
        report('That action could not be opened. Your command is still here; use the regular navigation to continue.');
      } finally { busy = false; input.disabled = false; submit.disabled = false; if (button.isConnected) button.disabled = false; }
    }
    function analyze() {
      var matched = commands.parse(input.value); results.replaceChildren(); report(matched.message);
      matched.actions.forEach(function (action) {
        var item = make('li'); var button = make('button', undefined, 'navigation-helper-action'); button.type = 'button';
        button.append(make('strong', action.label), make('span', action.description));
        button.addEventListener('click', function () { apply(action, button); }); item.append(button); results.append(item);
      });
    }
    launch.addEventListener('click', function () {
      if (doc.querySelector('dialog[open]')) return;
      root.dispatchEvent(new root.CustomEvent('omni:overlay-open', { detail: { source: 'navigation-helper' } }));
      opener = doc.activeElement; restoreOnClose = true; dialog.showModal(); dialog.scrollTop = 0; input.focus();
    });
    close.addEventListener('click', function () { closeDialog(true); });
    dialog.addEventListener('cancel', function () { restoreOnClose = true; });
    dialog.addEventListener('close', function () {
      if (restoreOnClose && !doc.querySelector('dialog[open]') && opener && opener.isConnected) opener.focus({ preventScroll: true });
    });
    form.addEventListener('submit', function (event) { event.preventDefault(); analyze(); });
    input.addEventListener('input', function () { results.replaceChildren(); report('Choose Find a match to see suggestions for this command.'); });
    dialog.addEventListener('keydown', function (event) {
      if (event.key !== 'Tab' || event.defaultPrevented) return;
      var controls = Array.from(dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),[tabindex="0"]')).filter(function (node) { return node.getClientRects().length; });
      var first = controls[0], last = controls[controls.length - 1];
      if (!first) return;
      if (event.shiftKey && doc.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    return Object.freeze({ button: launch, dialog: dialog, input: input, analyze: analyze });
  }
  root.OmniNavigationAssistant = Object.freeze({ install: install, modelConnected: false, version: commands.version });
  if (root.document) {
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', function () { install(); }, { once: true });
    else install();
  }
})(typeof globalThis !== 'undefined' ? globalThis : window);
