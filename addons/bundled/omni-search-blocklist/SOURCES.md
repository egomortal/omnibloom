# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. No network: nothing is fetched or sent. Checked 2026-11-16.

## Where it runs

Injected on `*://*/search*` and DuckDuckGo pages, then the runtime stops at once unless the page is a result page:

- Google: `google.<tld>` or `google.co.<cc>` / `google.com.<cc>` (with or without `www.`), path `/search`;
- DuckDuckGo: `duckduckgo.com/?q=…` and `html.duckduckgo.com/html/`;
- Bing: `bing.com/search` (with or without `www.`).

## Finding results and their real site

Result blocks (outermost only): Google `div.MjjYud` / `div.g` whose link holds an `<h3>`; DuckDuckGo `article[data-testid=result]` (script version) and `div.result.results_links` / `.web-result` (html version, ads `result--ad` skipped); Bing `li.b_algo` with the title link in its `<h2>`. Blocks without a usable http(s) link are left alone.

Redirect links are unwrapped before the host is read (up to 3 levels): Google `/url?q=` or `url=` (also `/interstitial`), DuckDuckGo `/l/?uddg=`, Bing `/ck/a?u=a1<base64url>`. A Bing redirect in any other form is not guessed at. Hosts come from the browser's URL parser, so international names are compared as punycode (`xn--`).

## The list

Stored in the add-on's own storage (key `blocked-v1`, a JSON array), at most 200 domains. Each entry is normalised: lowercase, punycode, no scheme, user, port, path, query, trailing dot, leading `*.` or `www.`; at least two labels, each a valid DNS label. An entry blocks itself and its subdomains (`example.com` blocks `www.example.com` and `news.example.com`, never `evil-example.com` or `example.com.evil.net`).

The add-on loader accepts only bool / choice settings, so the list is edited from the results page itself: **Block this site** on a result adds its host without `www.`; with blocked results shown, the same button reads **Unblock <entry>** and removes the entry that matched. When the list is full (200) nothing is added and the line says so. Private tabs cannot write add-on storage; a block made there lasts for that page only.

## On the page

Blocked results get `display:none`; one line before the first result says "N results hidden" with **Show** (they come back dimmed, with Unblock) / **Hide**. All controls are real `<button>` elements, so D-pad focus and the pointer reach them; after blocking, focus moves to Show. The setting "Show a Block this site button" (on by default) removes the per-result buttons. Results added later (more results, infinite scroll) are picked up by a `MutationObserver`, looked at no more than every 300 ms; the add-on's own nodes do not wake it. Turning the add-on off removes everything it added.

Off by default.
