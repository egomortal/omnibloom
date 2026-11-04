#pragma once
static constexpr const char omniLinkSnapshotSource[] = R"OMNISNAP((function(){'use strict';const globalThis={};const module=undefined;
/* Isolated candidate policy experiment. Detection is not downloadability. No I/O. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.OmniCandidateLab = api;
})(typeof globalThis === 'object' ? globalThis : window, function () {
  'use strict';
  const TYPES = Object.freeze({ 'media-current': 90, 'media-source': 75, 'og-video': 60,
    'anchor-media': 35, 'page-video': 55, 'media-blob': 55, iframe: 25,
    // downloader-1: manifests/media files the page actually fetched (Resource Timing).
    'resource-manifest': 90, 'resource-media': 75 });
  const LIMITS = Object.freeze({ candidates: 8, observations: 64, evidence: 4, urlCharacters: 4096,
    urlBytes: 8192, retainedUrlBytes: 32768, ttlMs: 600000 });
  const SEGMENT = /\.(?:m4s|cmfa|cmfv|ts)$/i;
  const MEDIA = /\.(?:mp4|m4v|webm|mov|mkv|mp3|m4a|aac|ogg|opus|flac|wav)$/i;
  const MANIFEST = /\.(?:m3u8|mpd)$/i;
  // Manifests served without a file extension (e.g. /manifest(format=m3u8-aapl), ?format=mpd).
  const MANIFEST_HINT = /(?:m3u8|\.mpd(?:$|[?&#/])|format=mpd)/i;
  function isManifest(parsed, kind) { return MANIFEST.test(parsed.pathname) || (kind === 'resource-manifest' && MANIFEST_HINT.test(parsed.pathname + parsed.search)); }
  function utf8Bytes(value) {
    let n = 0;
    for (let i = 0; i < value.length; i++) {
      const c = value.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff) {
        const d = value.charCodeAt(++i);
        if (!(d >= 0xdc00 && d <= 0xdfff)) return -1;
        n += 4;
      } else if (c >= 0xdc00 && c <= 0xdfff) return -1;
      else n += c < 128 ? 1 : c < 2048 ? 2 : 3;
    }
    return n;
  }
  function validateUrl(value, base) {
    if (typeof value !== 'string' || value.length > LIMITS.urlCharacters) return null;
    const raw = value.trim();
    if (!raw || /[\s\\\u0000-\u001f\u007f]/u.test(raw)) return null;
    const bytes = utf8Bytes(raw);
    if (bytes < 0 || bytes > LIMITS.urlBytes) return null;
    try {
      const absolute = /^https?:\/\//i.test(raw);
      if (!absolute && (!base || /^[a-z][\w+.-]*:/i.test(raw))) return null;
      if (absolute || raw.startsWith('//')) {
        const authority = raw.match(/^(?:https?:)?\/\/([^/?#]+)/i);
        if (!authority || authority[1].includes('@')) return null;
      }
      const parsed = new URL(raw, base || undefined);
      if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password || parsed.port === '0') return null;
      // Keep the absolute request text byte-for-byte after trim. Do not strip,
      // reorder, decode, recase or re-encode signed query/fragment parameters.
      const requestUrl = absolute ? raw : parsed.href;
      if (requestUrl.length > LIMITS.urlCharacters || utf8Bytes(requestUrl) > LIMITS.urlBytes) return null;
      return { requestUrl, duplicateKey: requestUrl, bytes: utf8Bytes(requestUrl), parsed };
    } catch (_) { return null; }
  }
  function cap(value, fallback, max) { return Number.isInteger(value) && value > 0 ? Math.min(value, max) : fallback; }
  function createCollector(options) {
    options = options || {};
    const capacity = cap(options.capacity, LIMITS.candidates, 32);
    const observationLimit = cap(options.observationLimit, LIMITS.observations, 128);
    const ttlMs = cap(options.ttlMs, LIMITS.ttlMs, 3600000);
    const clock = typeof options.clock === 'function' ? options.clock : Date.now;
    let generation = 0, page = null, records = [], notified = false, disposed = false, lastNow = 0;
    let diagnostics = { examined: 0, ignored: 0, truncated: false, retainedUrlBytes: 0 };
    function now() { const value = clock(); if (!Number.isFinite(value) || value < 0) throw new TypeError('Clock must be finite and non-negative.'); return (lastNow = Math.max(lastNow, value)); }
    function clear() { records = []; notified = false; diagnostics = { examined: 0, ignored: 0, truncated: false, retainedUrlBytes: 0 }; }
    function reset() { generation++; page = null; clear(); return generation; }
    function startPage(context) {
      reset();
      if (disposed || !context || context.private === true || context.blocked === true) return generation;
      // Privacy/ownership checks intentionally precede reading context.url.
      const url = validateUrl(context.url);
      if (url) page = { url: url.requestUrl, token: generation };
      return generation;
    }
    function expire() {
      const time = now();
      records = records.filter(record => time - record.lastSeen < ttlMs);
      diagnostics.retainedUrlBytes = records.reduce((sum, record) => sum + record.urlBytes, 0);
    }
    function replaceSnapshot(token, observations) {
      if (disposed || !page || token !== generation || !Array.isArray(observations)) return { accepted: false, reason: 'inactive-or-stale-page' };
      const time = now(), pool = new Map();
      const count = Math.min(observationLimit, observations.length);
      diagnostics = { examined: count, ignored: 0, truncated: observations.length > count, retainedUrlBytes: 0 };
      for (let i = 0; i < count; i++) {
        try {
        const observation = observations[i];
        if (!observation || !Object.prototype.hasOwnProperty.call(TYPES, observation.kind)) { diagnostics.ignored++; continue; }
        const kind = observation.kind;
        const encrypted = observation.encrypted === true;
        const blob = typeof observation.url === 'string' && /^blob:/i.test(observation.url);
        const fallback = encrypted || blob || ['media-blob', 'page-video', 'iframe'].includes(kind);
        const safe = validateUrl(fallback ? page.url : observation.url, page.url);
        if (!safe) { diagnostics.ignored++; continue; }
        const path = safe.parsed.pathname;
        const manifest = !fallback && isManifest(safe.parsed, kind);
        if (!fallback && ((SEGMENT.test(path) && !manifest) || ((kind === 'anchor-media' || kind === 'resource-media') && !MEDIA.test(path) && !manifest)
            || (kind === 'resource-manifest' && !manifest))) { diagnostics.ignored++; continue; }
        const type = fallback ? 'source-page' : manifest ? 'manifest' : kind === 'og-video' ? 'metadata-url' : 'media-url';
        // The first fetched manifest is usually the master playlist; later ones are variants.
        const score = encrypted ? 45 : fallback ? Math.min(TYPES[kind], 55) : kind === 'resource-manifest' && observation.rank > 0 ? 75
          : TYPES[kind] + (observation.playing === true && kind === 'media-current' ? 5 : 0);
        const sourceId = typeof observation.sourceId === 'string' ? observation.sourceId.slice(0, 96) : 'anonymous';
        const reason = encrypted ? 'encrypted-media-page-fallback' : blob ? 'blob-is-not-a-network-file'
          : kind === 'resource-manifest' || kind === 'resource-media' ? 'resource-timing'
          : observation.via === 'iframe-media' && kind !== 'iframe' ? 'iframe-media' : kind;
        const evidenceKey = sourceId + '\u0000' + reason;
        let record = pool.get(safe.duplicateKey);
        if (!record) {
          record = { requestUrl: safe.requestUrl, duplicateKey: safe.duplicateKey, urlBytes: safe.bytes, type,
            score, confidence: '', evidence: [], caveats: ['Candidate only: no server request, engine extraction, completeness or downloadability was tested.'], lastSeen: time };
          pool.set(safe.duplicateKey, record);
        }
        if (score > record.score) { record.score = score; record.type = type; }
        if (record.evidence.length < LIMITS.evidence && !record.evidence.some(item => item.key === evidenceKey)) record.evidence.push({ key: evidenceKey, sourceId, kind: reason });
        if (encrypted && !record.caveats.includes('Encrypted media observed; no clear downloadable stream is claimed.')) record.caveats.push('Encrypted media observed; no clear downloadable stream is claimed.');
        if (fallback && !record.caveats.includes('This is the source PAGE URL, not media bytes.')) record.caveats.push('This is the source PAGE URL, not media bytes.');
        if (kind === 'iframe' && !record.caveats.includes('Frame contents were not inspected; embedded content may be unrelated or inaccessible.')) record.caveats.push('Frame contents were not inspected; embedded content may be unrelated or inaccessible.');
        if (reason === 'resource-timing' && !record.caveats.includes('Seen in the page\'s own network requests; it may be a sub-playlist, an ad, or expire.')) record.caveats.push('Seen in the page\'s own network requests; it may be a sub-playlist, an ad, or expire.');
        if (type === 'metadata-url' && !record.caveats.includes('Open Graph may describe an embed/player rather than a media file.')) record.caveats.push('Open Graph may describe an embed/player rather than a media file.');
        } catch (_) { diagnostics.ignored++; }
      }
      records = [];
      for (const record of Array.from(pool.values()).sort((a, b) => b.score - a.score || a.requestUrl.localeCompare(b.requestUrl))) {
        if (records.length >= capacity || diagnostics.retainedUrlBytes + record.urlBytes > LIMITS.retainedUrlBytes) { diagnostics.truncated = true; continue; }
        record.confidence = record.score >= 85 ? 'high' : record.score >= 50 ? 'medium' : 'low';
        diagnostics.retainedUrlBytes += record.urlBytes; records.push(record);
      }
      return { accepted: true, count: records.length };
    }
    function list() {
      expire();
      return records.map(record => ({ requestUrl: record.requestUrl, duplicateKey: record.duplicateKey, type: record.type,
        confidence: record.confidence, score: record.score, downloadability: 'unverified', lastSeen: record.lastSeen,
        evidence: record.evidence.map(item => ({ sourceId: item.sourceId, kind: item.kind })), caveats: record.caveats.slice() }));
    }
    function takeNotice(mayShow) {
      const candidates = list();
      if (disposed || !mayShow || notified || !candidates.some(item => item.score >= 50)) return null;
      notified = true;
      return { token: generation, text: 'Media candidates found — review links', count: candidates.length };
    }
    return Object.freeze({ startPage, replaceSnapshot, list, takeNotice, reset,
      stats: function () { expire(); return Object.assign({ count: records.length, generation, active: !!page && !disposed, notified, ttlMs }, diagnostics); },
      dispose: function () { reset(); disposed = true; } });
  }
  return Object.freeze({ createCollector, validateUrl, LIMITS });
});

/* Optional explicit installation only. No network, media loads or worker calls. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./candidates.js'));
  else root.OmniCandidateDomLab = factory(root.OmniCandidateLab);
})(typeof globalThis === 'object' ? globalThis : window, function (policy) {
  'use strict';
  const MANIFEST_HINT_DOM = /(?:\.m3u8|\.mpd)(?:$|[?&#])|m3u8|format=mpd/i;
  const MEDIA_DOM = /\.(?:mp4|m4v|webm|mov|mkv|mp3|m4a|aac|ogg|opus|flac|wav)$/i;
  function createAdapter(document, options) {
    options = options || {};
    if (!document || !document.defaultView || typeof options.contextProvider !== 'function') throw new TypeError('A document and explicit public/private context provider are required.');
    const view = document.defaultView;
    const collector = policy.createCollector(options.collectorOptions);
    const observeRoot = options.observeRoot || document.documentElement;
    let disposed = false, suspended = false, timer = null, expiryTimer = null, token = 0, contextKey = null, nodes = new WeakMap(), encryptedNodes = new WeakSet(), sequence = 0;
    let observer = null, signature = '[]', scanCount = 0, lastVisited = 0, scanTruncated = false, readErrors = 0, callbackErrors = 0;
    const events = ['loadedmetadata', 'loadstart', 'emptied', 'encrypted'];
    function context(force) {
      let value, next = null, blocked = true;
      try {
        value = options.contextProvider();
        blocked = !value || value.private === true || value.blocked === true;
        if (!blocked) next = value.url;
      } catch (_) { readErrors++; }
      // A private or owned/blocked page is rejected before reading its URL.
      if (force || next !== contextKey) {
        contextKey = next; nodes = new WeakMap(); encryptedNodes = new WeakSet(); sequence = 0;
        token = collector.startPage(blocked ? { private: true } : { url: next });
        if (expiryTimer !== null) { view.clearTimeout(expiryTimer); expiryTimer = null; }
        publish();
      }
      return collector.stats().active;
    }
    function id(node) { if (!nodes.has(node)) nodes.set(node, 'node-' + (++sequence)); return nodes.get(node); }
    function encrypted(node) { try { return encryptedNodes.has(node) || !!node.mediaKeys; } catch (_) { return encryptedNodes.has(node); } }
    function publish() {
      const items = collector.list();
      const next = JSON.stringify(items.map(item => ({ requestUrl: item.requestUrl, type: item.type, score: item.score, evidence: item.evidence, caveats: item.caveats })));
      if (next !== signature) {
        signature = next;
        if (typeof options.onChange === 'function') {
          try { options.onChange(items); } catch (_) { callbackErrors++; }
        }
      }
      return items;
    }
    function armExpiry() {
      if (expiryTimer !== null) { view.clearTimeout(expiryTimer); expiryTimer = null; }
      if (!disposed && !suspended && collector.stats().count) expiryTimer = view.setTimeout(function () {
        expiryTimer = null;
        if (!disposed && !suspended) { context(false); publish(); }
      }, collector.stats().ttlMs);
    }
    function scan() {
      if (disposed || suspended) return [];
      if (timer !== null) { view.clearTimeout(timer); timer = null; }
      if (!context(false)) return publish();
      const buckets = { current: [], source: [], metadata: [], frame: [], anchor: [], resource: [] };
      const quotas = { current: 24, source: 16, metadata: 8, frame: 4, anchor: 12, resource: 16 };
      const frames = [];
      let protectedMedia = false;
      let truncated = false;
      function add(bucket, node, kind, url, extra) {
        if (buckets[bucket].length >= quotas[bucket]) { truncated = true; return; }
        buckets[bucket].push(Object.assign({ sourceId: id(node), kind, url }, extra || {}));
      }
      // Bounded DOM traversal avoids an unbounded querySelectorAll NodeList.
      // downloader-1: the same walk continues into SAME-ORIGIN iframes (a
      // cross-origin frame's contentDocument is null and stays a weak PAGE
      // fallback). Frame URLs are resolved against the frame's own baseURI.
      let node = observeRoot, visited = 0;
      function absolute(value, doc) { try { return value && doc !== document ? new URL(value, doc.baseURI).href : value; } catch (_) { return ''; } }
      function walk(rootNode, doc, depth) {
        const inFrame = doc !== document, via = inFrame ? { via: 'iframe-media' } : {};
        let current = rootNode;
        const walker = doc.createTreeWalker(rootNode, 1);
        while (current && visited < 2048) {
          visited++;
          try {
          const tag = String(current.localName || '').toLowerCase();
          if (tag === 'video' || tag === 'audio') {
            const selected = current.currentSrc || '';
            const url = selected || absolute(current.getAttribute('src') || '', doc);
            if (encrypted(current)) protectedMedia = true;
            if (url) add(selected ? 'current' : 'source', current, /^blob:/i.test(url) ? 'media-blob' : selected ? 'media-current' : 'media-source', url, Object.assign({ encrypted: encrypted(current), playing: selected && current.paused === false }, via));
            else if (tag === 'video' && encrypted(current)) add('current', current, 'page-video', '', { encrypted: true });
          } else if (tag === 'source') {
            const parent = current.parentElement;
            if (parent && /^(video|audio)$/i.test(parent.localName)) add('source', current, 'media-source', absolute(current.getAttribute('src') || '', doc), Object.assign({ encrypted: encrypted(parent) }, via));
          } else if (tag === 'meta' && !inFrame && /^og:video(?::url|:secure_url)?$/i.test(current.getAttribute('property') || '')) {
            add('metadata', current, 'og-video', current.getAttribute('content') || '');
          } else if (tag === 'iframe') {
            // The frame element itself stays a weak PAGE fallback. Only a
            // same-origin frame (readable contentDocument) is inspected.
            add('frame', current, 'iframe', '');
            if (depth < 2 && frames.length < 4) {
              let child = null;
              try { child = current.contentDocument; } catch (_) { child = null; }
              if (child && child.documentElement) frames.push({ doc: child, depth: depth + 1 });
            }
          } else if (tag === 'a' && current.hasAttribute('href')) add('anchor', current, 'anchor-media', absolute(current.getAttribute('href'), doc), via);
          } catch (_) { readErrors++; }
          current = walker.nextNode();
        }
        return current;
      }
      // Resource Timing lists what the page (and its same-origin frames)
      // actually fetched: the manifest behind a blob: MediaSource player, or
      // a progressive file. URLs only; no request is made and no body read.
      function resources(doc) {
        try {
          const win = doc.defaultView, perf = win && win.performance;
          if (!perf || typeof perf.getEntriesByType !== 'function') return;
          const entries = perf.getEntriesByType('resource');
          const count = Math.min(entries.length, 512);
          let rank = 0;
          const files = [];
          for (let i = 0; i < count; i++) {
            const name = String(entries[i].name || '');
            if (!/^https?:/i.test(name)) continue;
            let parsed; try { parsed = new URL(name); } catch (_) { continue; }
            const text = parsed.pathname + parsed.search;
            if (MANIFEST_HINT_DOM.test(text)) add('resource', perf, 'resource-manifest', name, Object.assign({ rank: rank++ }, doc !== document ? { via: 'iframe-media' } : {}));
            else if (MEDIA_DOM.test(parsed.pathname)) files.push(name);
          }
          // With a manifest present, fetched .mp4/.m4a files are init/segment
          // pieces of that stream (e.g. HLS fMP4 init_0.mp4), not whole files.
          if (!rank) for (const name of files) add('resource', perf, 'resource-media', name, doc !== document ? { via: 'iframe-media' } : {});
          if (entries.length > count) truncated = true;
        } catch (_) { readErrors++; }
      }
      try {
        node = walk(observeRoot, document, 0);
        for (let i = 0; i < frames.length && visited < 2048; i++) {
          try { if (walk(frames[i].doc.documentElement, frames[i].doc, frames[i].depth)) truncated = true; } catch (_) { readErrors++; }
        }
        // A protected (EME) player is never paired with network suggestions.
        if (!protectedMedia) { resources(document); for (const frame of frames) resources(frame.doc); }
      } catch (_) { readErrors++; truncated = true; }
      lastVisited = visited; scanTruncated = truncated || !!node;
      const observations = [].concat(buckets.current, buckets.resource, buckets.source, buckets.metadata, buckets.frame, buckets.anchor);
      collector.replaceSnapshot(token, observations); scanCount++;
      armExpiry();
      return publish();
    }
    function schedule() {
      if (!disposed && !suspended && timer === null) timer = view.setTimeout(scan, 250);
    }
    function mediaEvent(event) {
      try {
        const node = event.target;
        if (!node || !/^(video|audio)$/i.test(node.localName || '')) return;
        if (event.type === 'encrypted') encryptedNodes.add(node);
        schedule();
      } catch (_) { readErrors++; }
    }
    function navigate() { if (!disposed) { suspended = false; context(true); schedule(); } }
    function pageHide() {
      suspended = true;
      if (timer !== null) { view.clearTimeout(timer); timer = null; }
      if (expiryTimer !== null) { view.clearTimeout(expiryTimer); expiryTimer = null; }
      collector.reset(); contextKey = null; nodes = new WeakMap(); encryptedNodes = new WeakSet(); publish();
    }
    context(true);
    for (const event of events) document.addEventListener(event, mediaEvent, true);
    for (const event of ['popstate', 'hashchange', 'pageshow']) view.addEventListener(event, navigate);
    view.addEventListener('pagehide', pageHide);
    if (typeof view.MutationObserver === 'function' && observeRoot) {
      observer = new view.MutationObserver(schedule);
      observer.observe(observeRoot, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'content', 'property', 'href'] });
    }
    schedule();
    return Object.freeze({ scan, navigate,
      list: function () { if (!disposed && !suspended) context(false); return publish(); },
      takeNotice: function (mayShow) { if (!disposed && !suspended) context(false); publish(); return collector.takeNotice(!disposed && !suspended && mayShow); },
      reset: function () { pageHide(); },
      stats: function () { if (!disposed && !suspended) context(false); return Object.assign(collector.stats(), { scanCount, lastVisited, scanTruncated, readErrors, callbackErrors, pendingTimer: timer !== null, expiryTimer: expiryTimer !== null,
        installedListeners: disposed ? 0 : 8, observerConnected: !disposed && !!observer, disposed, suspended }); },
      dispose: function () {
        if (disposed) return;
        disposed = true;
        try { pageHide(); } finally {
          collector.dispose();
          for (const event of events) document.removeEventListener(event, mediaEvent, true);
          for (const event of ['popstate', 'hashchange', 'pageshow']) view.removeEventListener(event, navigate);
          view.removeEventListener('pagehide', pageHide);
          if (observer) { observer.disconnect(); observer = null; }
          contextKey = null;
        }
      } });
  }
  return Object.freeze({ createAdapter });
});

let adapter;try{const p=document.URL;adapter=globalThis.OmniCandidateDomLab.createAdapter(document,{contextProvider:()=>({url:p,private:false})});const list=adapter.scan();const stats=adapter.stats();const wire={v:1,g:'__OMNI_DOCUMENT_GENERATION__',p,rows:list.map(item=>({u:item.requestUrl,k:item.type,s:item.score,e:Array.from(new Set(item.evidence.map(e=>e.kind)))})),t:!!(stats.truncated||stats.scanTruncated||stats.readErrors)};const encodedSize=value=>encodeURIComponent(value).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase()).length;while(encodedSize(JSON.stringify(wire))>16384&&wire.rows.length){wire.rows.pop();wire.t=true;}return encodedSize(JSON.stringify(wire))<=16384?JSON.stringify(wire):'';}finally{if(adapter)adapter.dispose();}})())OMNISNAP";
