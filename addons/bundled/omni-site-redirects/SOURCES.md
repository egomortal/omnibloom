# Licence and provenance

Original implementation, MIT; no upstream extension code or rule lists are bundled (the idea is the ClearURLs / Redirector kind of add-on, the code is not theirs). No network: nothing is fetched, no remote code or rules run. Checked 2026-11-16.

## Rules

Each rule is its own setting and all three are off by default (the add-on itself is off by default too). Hosts are compared exactly after URL parsing ([WHATWG URL](https://url.spec.whatwg.org/)), never by substring, so `www.reddit.com.evil.com`, `youtube.com@evil.com` or a host with a port or a trailing dot never match. Only `http:` and `https:` pages; addresses with a user name or password are left alone. The target is always `https:`.

- **Reddit → old.reddit.com:** `reddit.com`, `www.reddit.com`, `new.reddit.com`; path, query and fragment kept unchanged (percent-encoding included). Pages old Reddit cannot show and the account/form pages (`/media`, `/settings`, `/chat`, `/notifications`, `/login`, `/register`, `/logout`, `/password`, `/account`, `/api`, `/svc`, `/submit`, `/verification`, `/poll`, `/answers`, `/appeal`, `/premium`, `/coins`, `/user/me`) are left alone.
- **YouTube Shorts → watch page:** `youtube.com`, `www.youtube.com`, `m.youtube.com`, path exactly `/shorts/<id>` or `/shorts/<id>/` with an 11-character video id (`A–Z a–z 0–9 _ -`). Becomes `/watch?v=<id>` on the same host, other query parameters after `v` (a second `v` dropped), fragment kept. YouTube changes pages without loading one, so its `yt-navigate-finish` event is checked as well.
- **AMP → canonical:** two parts.
  - Google's AMP viewer, `google.com/amp/s/<address>` and `www.google.com/amp/s/<address>`, opens `https://<address>`. A fully encoded address (`example.com%2Fstory%3Fid%3D1`) is decoded once; otherwise nothing is decoded. Google's viewer parameters (`usqp`, `amp_js_v`, `amp_gsa`, `amp_ct`, `amp_tf`, `_gsa`, `ampshare`, `aoh`, `csi`, `referrer`, `outputType`) are dropped, others kept. Refused: a scheme-relative, backslash, user-info, encoded, IP, `localhost`, ported or dotless host, and Google's own hosts.
  - A page that marks itself as AMP (`<html amp>` or `<html ⚡>`, [AMP HTML spec](https://amp.dev/documentation/guides-and-tutorials/learn/spec/amphtml)) is sent to its `<link rel="canonical">` when that address is on the same registrable domain (`amp.example.com` → `www.example.com` is fine, `alice.github.io` → `bob.github.io` is not), is not the page itself, keeps the port, does not go from `https` to `http`, and is not the page we just came from (`document.referrer`; a cross-origin referrer cut to its origin counts when it is the canonical's origin). An AMP page opened from its own canonical therefore stays, which also stops any page A ↔ page B loop.

Registrable domain: no Public Suffix List is bundled. A small built-in list of shared-hosting suffixes (`github.io`, `blogspot.com`, `herokuapp.com`, `netlify.app`, `pages.dev`, `s3.amazonaws.com` and others) and the usual country second levels (`co.uk`, `com.au`, `co.jp`, …: a 2-letter TLD under `co`, `com`, `net`, `org`, `gov`, `edu`, `ac` and similar) count as suffixes. Unknown cases come out narrower, never wider, so the worst case is a missed redirect, not a cross-site one.

## Where it runs

Manifest match list only, never `<all_urls>`: the Reddit, YouTube and Google AMP hosts above, plus `*://*/*amp*` for AMP pages (WebKit user-script patterns match the path, so an AMP page whose path has no "amp" is not covered). The path pattern also matches pages such as `/example`; there the script only reads one attribute of `<html>` and stops. Top frame only. `private_safe` is false: Omni does not inject it into private tabs at all (`OmniBlocker.cpp`, OMNI_ADDONS_V1: add-ons go to the private controller only if private_safe).

Runs at `document_start`, so the address rules act before the page renders; the AMP canonical check waits for `DOMContentLoaded`.

## Never looping

- At most one redirect per page load (and per address for YouTube's in-page navigations).
- `location.replace()`, so the redirected page leaves no history entry.
- Only fresh navigations: `PerformanceNavigationTiming.type` must be `navigate`, so reloads and Back/Forward are never redirected.
- Before redirecting, the source address (without fragment) is added to a per-tab list in the source site's `sessionStorage` (key `omni-site-redirects:v1`, last 40 addresses). An address on that list is not redirected again in that tab, so a Back press to it (or the same link again) stays there.
- Every target is a fixed point of the address rules (tested), so a Google AMP link to a Reddit or Shorts page is at most one more navigation.

## POST results

The add-on API and the page do not expose the request method (Navigation Timing has no method field), so a POST result cannot be recognised directly. The guards that cover it: reloads and Back/Forward are skipped, and Reddit's account and form pages are excluded above. YouTube `/shorts/<id>` and Google `/amp/s/` addresses are only reached with GET.

## Stored data

Nothing in add-on storage. The per-tab list lives in `sessionStorage` and ends with the tab.
