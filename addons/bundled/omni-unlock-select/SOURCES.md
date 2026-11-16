# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled (the idea is the same as "Allow Copy" / "Enable Right Click" style extensions, written from scratch for Omni's isolated add-on world). No network, no storage: nothing is fetched, sent or kept. Checked 2026-11-16.

## Why it exists

Omni's L2 text select uses the page's own selection: it starts a selection, extends it and copies it. Sites that "protect" their text cancel `selectstart`, `copy`, `contextmenu`, `dragstart` or `mousedown`, or set `user-select: none`, so text select silently selects nothing or copies nothing. With this add-on on for such a site, the page's normal selection and copy work again, and L2 text select with them.

## What it does (only while on for the site)

1. **Style.** `addon.css` is a user-level stylesheet, so its `!important` wins over the page's. Under `<html class="omni-unlock-select">` (set by the runtime, removed when off) page text gets `user-select: text`. Never changed: inputs, text areas, selects, buttons, `role=button` / slider / tab / menu item and similar controls, contenteditable regions, canvas, video, audio, svg, frames, draggable items and Omni's own add-on UI.
2. **Events.** Omni runs add-ons in their own JavaScript world, so the page's `addEventListener` cannot be wrapped (and a page-world `<script>` would fail under strict CSP and expose Omni). Instead a capture listener on `window`, added at `document_start` before any page script, sees the five events first. After each trusted event on plain text it checks `defaultPrevented` (inline `return false` and `returnValue = false` set it too). Once the page has cancelled that event type on text (twice for `mousedown`), later events of that type on plain text are stopped with `stopImmediatePropagation`, so the page's blocker never runs and the browser's default (select, copy, menu, drag) happens. A synthetic `selectstart` on `<body>` at load finds whole-page selection blockers before the first try; `copy` and `contextmenu` are never probed, since sites may answer with alerts or menus. Events on text fields and controls are never stopped; `mousedown` only for the main button, and a setting turns the `mousedown` part off.
3. **Inline handlers.** `onselectstart`, `oncopy`, `oncut`, `oncontextmenu`, `ondragstart` and (on plain text only) `onmousedown` attributes whose code cancels the event (`return false`, `preventDefault(`, `returnValue = false`) are removed at load and again on DOM changes (throttled to one scan per 500 ms). Switching the add-on off puts them back.

## Never

- Pages whose main content is a `<canvas>` covering at least half the viewport (games, maps, drawing apps, canvas editors): nothing is applied, and anything already applied is undone when such a canvas appears.
- Text fields, editable regions, buttons and Omni's own UI.

Off by default; turn it on for a site from Options > Add-ons ("this site"). Safe in private tabs: it stores nothing.
