/* Optional, local-only link hints. No requests, extraction, submission, or engine changes. */
(function (root, factory) {
  'use strict';
  var tools = factory(root);
  if (typeof module === 'object' && module && module.exports) module.exports = tools;
  else root.OmniLinkTools = tools;
  if (root.document && typeof root.document.addEventListener === 'function') tools.install(root.document);
})(typeof globalThis !== 'undefined' ? globalThis : window, function (root) {
  'use strict';
  var MAX_URL_CHARACTERS = 4096;
  var MAX_URL_BYTES = 8192;
  var MAX_RECORDS = 128;
  var INSTALL_KEY = '__omniLinkToolsInstalled';
  var currentState = { jobs: [], saved_links: [] };
  var documentRef = null;
  var pendingTimer = null;
  var categories = {
    video: ['mp4', 'mkv', 'webm', 'mov', 'avi', 'm4v', 'mpeg', 'mpg', 'ts', 'm2ts', 'flv', 'wmv', '3gp', 'ogv'],
    audio: ['mp3', 'm4a', 'aac', 'flac', 'wav', 'ogg', 'opus', 'wma', 'aiff', 'aif', 'alac'],
    archive: ['zip', '7z', 'rar', 'gz', 'bz2', 'xz', 'tgz', 'zst', 'tar'],
    document: ['pdf', 'epub', 'txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'odt', 'rtf', 'md', 'csv'],
    image: ['png', 'jpg', 'jpeg', 'webp', 'gif', 'avif', 'svg', 'bmp', 'tif', 'tiff', 'ico'],
    file: ['iso', 'img', 'bin', 'exe', 'msi', 'apk', 'deb', 'rpm', 'pkg', 'elf', 'appimage']
  };
  var labels = { video: 'Video', audio: 'Audio', archive: 'Archive', document: 'Document', image: 'Image', file: 'File', unknown: 'Link' };
  var statusLabels = { downloading: 'downloading', queued: 'queued', paused: 'paused', completed: 'completed', cancelled: 'cancelled', failed: 'needs another try' };
  var statusPriority = { downloading: 0, queued: 1, paused: 2, completed: 3, failed: 4, cancelled: 5 };

  function invalid(reason) { return { ok: false, canonical: null, reason: reason }; }

  function utf8Length(value) {
    var bytes = 0;
    for (var index = 0; index < value.length; index++) {
      var point = value.charCodeAt(index);
      if (point >= 0xD800 && point <= 0xDBFF) {
        var next = value.charCodeAt(index + 1);
        if (!(next >= 0xDC00 && next <= 0xDFFF)) return -1;
        index++;
        bytes += 4;
      } else if (point >= 0xDC00 && point <= 0xDFFF) return -1;
      else bytes += point <= 0x7F ? 1 : point <= 0x7FF ? 2 : 3;
    }
    return bytes;
  }

  function normalizeUrl(value) {
    if (typeof value !== 'string') return invalid('Enter an HTTP or HTTPS link.');
    if (value.length > MAX_URL_CHARACTERS) return invalid('This link is a little too long for the preview.');
    value = value.trim();
    if (!value) return invalid('Paste a link to see a helpful hint.');
    var bytes = utf8Length(value);
    if (bytes < 0) return invalid('This link contains invalid text.');
    if (bytes > MAX_URL_BYTES) return invalid('This link is a little too long for the preview.');
    if (!/^https?:\/\//i.test(value) || /[\u0000-\u0020\u007F\\]/.test(value)) return invalid('Use an HTTP or HTTPS link without spaces.');
    try {
      var authority = value.match(/^https?:\/\/([^/?#]*)/i);
      if (!authority || authority[1].indexOf('@') !== -1) return invalid('Use a link without an embedded username or password.');
      var parsed = new root.URL(value);
      if (!parsed.hostname || (parsed.protocol !== 'https:' && parsed.protocol !== 'http:')) return invalid('Enter an HTTP or HTTPS link.');
      if (parsed.username || parsed.password) return invalid('Use a link without an embedded username or password.');
      parsed.hash = '';
      var canonical = parsed.href;
      if (canonical.length > MAX_URL_CHARACTERS * 3) return invalid('This link is a little too long for the preview.');
      return { ok: true, canonical: canonical, reason: null };
    } catch (_) { return invalid('This link does not look complete yet.'); }
  }

  function classifyUrl(value) {
    var normalized = normalizeUrl(value);
    var result = { valid: normalized.ok, category: 'unknown', label: 'Link', extension: null,
      source: 'url-extension', uncertain: true, normalizedUrl: normalized.canonical };
    if (!normalized.ok) return result;
    var pathname = new root.URL(normalized.canonical).pathname;
    if (!pathname || pathname.charAt(pathname.length - 1) === '/') return result;
    var leaf = pathname.slice(pathname.lastIndexOf('/') + 1);
    try { leaf = decodeURIComponent(leaf); } catch (_) { /* A readable extension can still be a hint. */ }
    if (/[\/\\\u0000-\u001F\u007F]/.test(leaf)) return result;
    var match = leaf.toLowerCase().match(/\.([a-z0-9]{1,12})$/);
    if (!match) return result;
    var extension = match[1];
    result.extension = extension;
    if (extension === 'm3u8' || extension === 'mpd') {
      result.category = 'video'; result.label = 'Video playlist';
      return result;
    }
    var keys = Object.keys(categories);
    for (var index = 0; index < keys.length; index++) {
      if (categories[keys[index]].indexOf(extension) !== -1) {
        result.category = keys[index]; result.label = labels[keys[index]];
        return result;
      }
    }
    if (extension !== 'html' && extension !== 'htm' && extension !== 'php' && extension !== 'aspx') {
      result.category = 'file'; result.label = 'File';
    }
    return result;
  }

  function safeRecord(record, saved) {
    if (!record || typeof record !== 'object') return null;
    var normalized = normalizeUrl(record.url);
    if (!normalized.ok) return null;
    return { id: typeof record.id === 'string' ? record.id.slice(0, 128) : null,
      url: normalized.canonical, status: !saved && Object.prototype.hasOwnProperty.call(statusLabels, record.status) ? record.status : 'unknown' };
  }

  function compact(records, saved) {
    if (!Array.isArray(records)) return [];
    var result = [];
    for (var index = 0; index < Math.min(records.length, MAX_RECORDS); index++) {
      var record = safeRecord(records[index], saved);
      if (record) result.push(record);
    }
    return result;
  }

  function findDuplicates(value, jobs, savedLinks) {
    var normalized = normalizeUrl(value);
    var result = { canonical: normalized.canonical, job: null, saved: null, job_count: 0, saved_count: 0 };
    if (!normalized.ok) return result;
    var jobRecords = compact(jobs, false);
    var savedRecords = compact(savedLinks, true);
    for (var index = 0; index < jobRecords.length; index++) {
      var job = jobRecords[index];
      if (job.url !== normalized.canonical) continue;
      result.job_count++;
      if (!result.job || (statusPriority[job.status] === undefined ? 99 : statusPriority[job.status]) <
          (statusPriority[result.job.status] === undefined ? 99 : statusPriority[result.job.status])) result.job = job;
    }
    for (var savedIndex = 0; savedIndex < savedRecords.length; savedIndex++) {
      if (savedRecords[savedIndex].url !== normalized.canonical) continue;
      result.saved_count++;
      if (!result.saved) result.saved = savedRecords[savedIndex];
    }
    return result;
  }

  function getInsight(value, state) {
    var normalized = normalizeUrl(value);
    if (!normalized.ok) return { text: value && typeof value === 'string' && value.trim() ? normalized.reason : '', route: null, category: 'unknown' };
    var classification = classifyUrl(value);
    var duplicates = findDuplicates(value, state && state.jobs, state && state.saved_links);
    var text = classification.category === 'unknown' ? 'A link worth exploring. The format will be checked by the downloader.' :
      classification.label + ' hint from the link; the actual format may differ.';
    var route = null;
    if (duplicates.job) {
      var status = statusLabels[duplicates.job.status];
      text += status ? ' You already have this in downloads (' + status + ').' : ' You already have this in downloads.';
      text += ' You can still add it again.';
      route = 'queue';
    } else if (duplicates.saved) {
      text += ' This is already in your saved links.';
      route = 'library';
    }
    return { text: text, route: route, category: classification.category };
  }

  function renderHint(input) {
    if (!documentRef || !input || !input.isConnected || (input.id !== 'quick-url' && input.id !== 'download-url')) return;
    var hintId = input.id + '-link-insight';
    var hint = documentRef.getElementById(hintId);
    if (!hint) {
      hint = documentRef.createElement('div');
      hint.id = hintId;
      hint.className = 'link-insight helper-line';
      hint.setAttribute('role', 'status');
      hint.setAttribute('aria-live', 'polite');
      hint.setAttribute('aria-atomic', 'true');
      var wrapper = input.closest('.input-combo') || input;
      wrapper.insertAdjacentElement('afterend', hint);
      var described = (input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
      if (described.indexOf(hintId) === -1) described.push(hintId);
      input.setAttribute('aria-describedby', described.join(' '));
    }
    var insight = getInsight(input.value, currentState);
    hint.hidden = !insight.text;
    var signature = insight.text + '|' + (insight.route || '');
    if (hint.getAttribute('data-insight-signature') === signature) return;
    hint.setAttribute('data-insight-signature', signature);
    while (hint.firstChild) hint.removeChild(hint.firstChild);
    if (!insight.text) return;
    var description = documentRef.createElement('span');
    description.className = 'link-insight-description';
    description.textContent = insight.text;
    hint.appendChild(description);
    if (insight.route) {
      var button = documentRef.createElement('button');
      button.type = 'button';
      button.className = 'text-button link-insight-action';
      button.setAttribute('data-link-insight-route', insight.route);
      button.textContent = 'View existing';
      hint.appendChild(button);
    }
  }

  function refresh() {
    if (!documentRef) return;
    renderHint(documentRef.getElementById('quick-url'));
    renderHint(documentRef.getElementById('download-url'));
  }

  function install(document) {
    if (!document || document[INSTALL_KEY]) return false;
    document[INSTALL_KEY] = true;
    documentRef = document;
    document.addEventListener('focusin', function (event) { renderHint(event.target); });
    document.addEventListener('input', function (event) {
      var input = event.target;
      if (!input || (input.id !== 'quick-url' && input.id !== 'download-url')) return;
      if (pendingTimer !== null) root.clearTimeout(pendingTimer);
      pendingTimer = root.setTimeout(function () { pendingTimer = null; renderHint(input); }, 160);
    });
    document.addEventListener('click', function (event) {
      var target = event.target && event.target.closest ? event.target.closest('[data-link-insight-route]') : null;
      if (!target) return;
      var route = target.getAttribute('data-link-insight-route');
      if (route !== 'queue' && route !== 'library') return;
      event.preventDefault();
      root.dispatchEvent(new root.CustomEvent('omni:navigate', { detail: { route: route } }));
    });
    root.addEventListener('omni:state', function (event) {
      var state = event.detail || {};
      currentState = { jobs: compact(state.jobs, false), saved_links: compact(state.saved_links, true) };
      refresh();
    });
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', refresh, { once: true });
    else refresh();
    return true;
  }

  return Object.freeze({ normalizeUrl: normalizeUrl, classifyUrl: classifyUrl, findDuplicates: findDuplicates,
    getInsight: getInsight, refresh: refresh, install: install,
    limits: Object.freeze({ url_characters: MAX_URL_CHARACTERS, url_utf8_bytes: MAX_URL_BYTES, records_per_collection: MAX_RECORDS }) });
});
