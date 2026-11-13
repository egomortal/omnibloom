/* Optional read-only details for reported worker jobs and clearly marked Demo. No fetch, polling, or actions. */
(function (root, factory) {
  'use strict';
  var api = factory(root);
  if (typeof module === 'object' && module && module.exports) module.exports = api;
  else root.OmniJobDetails = api;
  if (root.document && typeof root.document.addEventListener === 'function') api.install(root.document);
})(typeof globalThis !== 'undefined' ? globalThis : window, function (root) {
  'use strict';
  var MAX_JOBS = 100, MAX_URL = 4096, MAX_URL_BYTES = 8192;
  var engines = { 'yt-dlp': 'yt-dlp', ytdlp: 'yt-dlp', jdownloader: 'JDownloader' };
  var kinds = { video: 'Video', audio: 'Audio', file: 'File' };
  var statuses = { queued: 'Queued', downloading: 'Downloading', paused: 'Paused', completed: 'Completed', cancelled: 'Cancelled', failed: 'Failed', extracting:'Extracting',processing:'Processing',cancelling:'Cancelling',interrupted:'Interrupted' };
  var documentRef = null, dialog = null, currentId = null, returnFocus = null;
  var jobs = new Map(), copySequence = 0;
  var nodes = {};

  function read(value, key) { try { return value && typeof value === 'object' ? value[key] : undefined; } catch (_) { return undefined; } }
  function unicodeBytes(value) {
    var count = 0;
    for (var i = 0; i < value.length; i++) {
      var c = value.charCodeAt(i);
      if (c >= 0xD800 && c <= 0xDBFF) {
        var next = value.charCodeAt(i + 1);
        if (!(next >= 0xDC00 && next <= 0xDFFF)) return -1;
        i++; count += 4;
      } else if (c >= 0xDC00 && c <= 0xDFFF) return -1;
      else count += c <= 0x7F ? 1 : c <= 0x7FF ? 2 : 3;
    }
    return count;
  }
  function titleText(value) {
    if (typeof value !== 'string' || !value || value.length > 4096 || unicodeBytes(value) < 0 || /[\u0000-\u001F\u007F]/.test(value)) return 'Download details';
    if (value.length <= 160) return value;
    var cut = value.slice(0, 160);
    if (/[\uD800-\uDBFF]$/.test(cut)) cut = cut.slice(0, -1);
    return cut + '… (title shortened)';
  }
  function sourceText(value) {
    if (typeof value !== 'string' || !value || value.length > MAX_URL) return null;
    var bytes = unicodeBytes(value);
    if (bytes < 0 || bytes > MAX_URL_BYTES || !/^https?:\/\//i.test(value) || /[\u0000-\u0020\u007F\\]/.test(value)) return null;
    try {
      var authority = value.match(/^https?:\/\/([^/?#]*)/i);
      if (!authority || authority[1].indexOf('@') !== -1) return null;
      var parsed = new root.URL(value);
      if (!parsed.hostname || !/^(https?:)$/.test(parsed.protocol) || parsed.username || parsed.password) return null;
      return value; // Preserve the exact supplied source, including query and fragment.
    } catch (_) { return null; }
  }
  function numberText(value, suffix, maximum) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > maximum) return 'Unavailable';
    return value.toLocaleString('en-US', { maximumFractionDigits: 2 }) + suffix;
  }
  function enumText(map, value) {
    return typeof value === 'string' && Object.prototype.hasOwnProperty.call(map, value) ? map[value] : 'Unavailable';
  }
  function formatJob(record) {
    var source = sourceText(read(record, 'url'));
    var status = enumText(statuses, read(record, 'status'));
    return {
      title: titleText(read(record, 'title')),
      sourceUrl: source,
      sourceAvailable: source !== null,
      simulationLabel: read(record,'demo')===true?'DEMO · NO MEDIA SAVED':read(record,'demo')===false?'REPORTED WORKER JOB':'MODE UNAVAILABLE',
      disclaimer: 'These are reported worker values. Unavailable fields are not inferred. A reported path is not a file-existence check; Demo never saves media.',
      fields: [
        { label: 'Engine', value: enumText(engines, read(record, 'engine')) },
        { label: 'Format selection', value: enumText(kinds, read(record, 'kind')) },
        { label: 'Reported status', value: status },
        { label: 'Reported progress', value: numberText(read(record, 'progress'), '%', 100) },
        { label:'Reported output',value:read(record,'demo')===true?'None · Demo':(typeof read(record,'filepath')==='string'&&read(record,'filepath')?read(record,'filepath').slice(0,4096):'Unavailable') },
        { label: 'Reported transferred', value: numberText(read(record, 'downloaded_bytes'), ' bytes', Number.MAX_SAFE_INTEGER) },
        { label: 'Reported total', value: numberText(read(record, 'total_bytes'), ' bytes', Number.MAX_SAFE_INTEGER) },
        { label: 'Reported speed', value: numberText(read(record, 'speed_bps'), ' bytes/s', Number.MAX_SAFE_INTEGER) },
        { label: 'Reported time remaining', value: numberText(read(record, 'eta_seconds'), ' seconds', 31536000) }
      ]
    };
  }
  function validId(value) { return typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value); }
  function text(element, value) { if (element.textContent !== value) element.textContent = value; }
  function element(tag, className, value) {
    var item = documentRef.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined) item.textContent = value;
    return item;
  }
  function render() {
    if (!dialog || !dialog.open || !currentId) return;
    var formatted = jobs.get(currentId) || formatJob(null);
    text(nodes.title, formatted.title);
    text(nodes.badge,formatted.simulationLabel);
    text(nodes.missing, jobs.has(currentId) ? '' : 'This job is no longer available in the current worker history.');
    nodes.missing.hidden = jobs.has(currentId);
    var source = formatted.sourceUrl || '';
    if (nodes.source.value !== source) { copySequence++; text(nodes.copyStatus, ''); nodes.source.value = source; }
    nodes.source.placeholder = source ? '' : 'Source link unavailable or invalid';
    var copyHadFocus = documentRef.activeElement === nodes.copy;
    nodes.copy.disabled = !formatted.sourceAvailable;
    if (copyHadFocus && nodes.copy.disabled && !documentRef.querySelector('dialog[open]:not(#job-detail-dialog)')) nodes.close.focus({ preventScroll: true });
    for (var index = 0; index < formatted.fields.length; index++) text(nodes.values[index], formatted.fields[index].value);
  }
  function selectFallback(message, sequence) {
    if (!dialog.open || sequence !== copySequence) return;
    text(nodes.copyStatus, message + ' The exact source link is selected. Copy it with Ctrl/Cmd+C or your browser’s copy menu.');
    if (documentRef.querySelector('dialog[open]:not(#job-detail-dialog)')) return;
    nodes.source.focus({ preventScroll: true });
    nodes.source.select();
  }
  async function copySource(event) {
    var formatted = jobs.get(currentId), sequence = ++copySequence;
    if (!formatted || !formatted.sourceAvailable) return;
    var source = formatted.sourceUrl;
    try {
      if ((event && event.isTrusted === false) || !root.navigator ||
          (root.navigator.userActivation && !root.navigator.userActivation.isActive) ||
          !root.navigator.clipboard || typeof root.navigator.clipboard.writeText !== 'function') {
        selectFallback('Automatic copy is not available here.', sequence); return;
      }
      await root.navigator.clipboard.writeText(source);
      if (dialog.open && sequence === copySequence) text(nodes.copyStatus, 'Source link copied.');
    } catch (_) { selectFallback('Clipboard access was not available.', sequence); }
  }
  function close() { if (dialog && dialog.open) dialog.close(); }
  function createDialog() {
    if (dialog) return;
    dialog = element('dialog', 'job-detail-dialog'); dialog.id = 'job-detail-dialog';
    dialog.setAttribute('aria-labelledby', 'job-detail-heading');
    dialog.setAttribute('aria-describedby', 'job-detail-disclaimer');
    var header = element('div', 'job-detail-header'), copy = element('div', 'job-detail-heading-copy');
    nodes.badge=element('span','job-detail-badge','MODE UNAVAILABLE');copy.appendChild(nodes.badge);
    nodes.title = element('h2', '', 'Download details'); nodes.title.id = 'job-detail-heading';
    copy.appendChild(nodes.title); header.appendChild(copy);
    var dismiss = element('button', 'job-detail-close', 'Close'); dismiss.type = 'button';
    nodes.close = dismiss;
    dismiss.setAttribute('aria-label', 'Close download details'); dismiss.addEventListener('click', close); header.appendChild(dismiss); dialog.appendChild(header);
    nodes.missing = element('p', 'job-detail-missing'); nodes.missing.hidden = true; dialog.appendChild(nodes.missing);
    var sourceLabel = element('label', 'job-detail-source-label', 'Exact source link'); sourceLabel.htmlFor = 'job-detail-source'; dialog.appendChild(sourceLabel);
    nodes.source = element('textarea', 'job-detail-source'); nodes.source.id = 'job-detail-source'; nodes.source.readOnly = true; nodes.source.rows = 3; nodes.source.spellcheck = false;
    nodes.source.setAttribute('autocomplete', 'off'); dialog.appendChild(nodes.source);
    nodes.copy = element('button', 'secondary-button job-detail-copy', 'Copy source link'); nodes.copy.type = 'button'; nodes.copy.addEventListener('click', copySource); dialog.appendChild(nodes.copy);
    nodes.copyStatus = element('p', 'job-detail-copy-status'); nodes.copyStatus.setAttribute('role', 'status'); nodes.copyStatus.setAttribute('aria-live', 'polite'); dialog.appendChild(nodes.copyStatus);
    var list = element('dl', 'job-detail-facts'); nodes.values = [];
    formatJob(null).fields.forEach(function (field) { var pair = element('div', 'job-detail-fact'); pair.appendChild(element('dt', '', field.label)); var value = element('dd', '', 'Unavailable'); pair.appendChild(value); nodes.values.push(value); list.appendChild(pair); });
    dialog.appendChild(list);
    var disclaimer = element('p', 'job-detail-disclaimer', formatJob(null).disclaimer); disclaimer.id = 'job-detail-disclaimer'; dialog.appendChild(disclaimer);
    dialog.addEventListener('cancel', function (event) { event.preventDefault(); close(); });
    dialog.addEventListener('close', function () {
      copySequence++; currentId = null;
      var target = returnFocus; returnFocus = null;
      if (documentRef.querySelector('dialog[open]')) return;
      var visible = function (node) { return node && node.isConnected && !node.disabled && !node.closest('[inert],[hidden]') && node.getClientRects().length > 0; };
      if (visible(target)) target.focus({ preventScroll: true });
      else {
        var queue = documentRef.querySelector('#navigation [data-route="queue"]');
        if (visible(queue)) queue.focus({ preventScroll: true });
        else { var heading = documentRef.querySelector('#main-content h1'); if (visible(heading)) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: true }); } }
      }
    });
    documentRef.body.appendChild(dialog);
  }
  function open(id, trigger) {
    if (!documentRef || !validId(id)) return false;
    createDialog();
    var activeDialog = documentRef.querySelector('dialog[open]');
    if (activeDialog && activeDialog !== dialog) return false;
    if (typeof dialog.showModal !== 'function') return false;
    root.dispatchEvent(new root.CustomEvent('omni:overlay-open', { detail: { overlay: 'job-details' } }));
    currentId = id; returnFocus = trigger || documentRef.activeElement; copySequence++;
    text(nodes.copyStatus, '');
    if (!dialog.open) dialog.showModal();
    render(); dialog.querySelector('.job-detail-close').focus({ preventScroll: true });
    return true;
  }
  function mountRows(scope) {
    if (!documentRef) return 0;
    var container = scope && typeof scope.querySelectorAll === 'function' ? scope : documentRef;
    var rows = container.querySelectorAll('[data-job-id]'), count = 0;
    if (rows.length) createDialog();
    for (var i = 0; i < Math.min(rows.length, MAX_JOBS); i++) {
      var row = rows[i], id = row.getAttribute('data-job-id');
      if (!validId(id) || row.querySelector('[data-job-details]')) continue;
      var button = element('button', 'text-button job-details-trigger', 'Details');
      button.type = 'button'; button.setAttribute('data-job-details', id); button.setAttribute('aria-haspopup', 'dialog');
      button.setAttribute('aria-controls', 'job-detail-dialog');
      var metadata = row.querySelector('.job-details') || row.querySelector('.job-info') || row;
      metadata.appendChild(button); count++;
    }
    return count;
  }
  function install(document) {
    if (!document || document.__omniJobDetailsInstalled) return false;
    document.__omniJobDetailsInstalled = true; documentRef = document;
    document.addEventListener('click', function (event) {
      var button = event.target && event.target.closest ? event.target.closest('[data-job-details]') : null;
      if (!button) return;
      event.preventDefault(); open(button.getAttribute('data-job-details'), button);
    });
    root.addEventListener('omni:state', function (event) {
      var incoming = read(event.detail, 'jobs'), next = new Map(), length = read(incoming, 'length');
      if (Number.isInteger(length) && length >= 0) {
        for (var i = 0; i < Math.min(length, MAX_JOBS); i++) {
          var record = read(incoming, i), id = read(record, 'id');
          if (validId(id) && !next.has(id)) next.set(id, formatJob(record));
        }
      }
      jobs = next; render();
    });
    return true;
  }
  return Object.freeze({ formatJob: formatJob, install: install, mountRows: mountRows, open: open,
    limits: Object.freeze({ jobs: MAX_JOBS, source_characters: MAX_URL, source_utf8_bytes: MAX_URL_BYTES }) });
});
