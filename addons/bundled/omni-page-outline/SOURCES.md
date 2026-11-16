# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. No network, no storage, no remote rules.

What is listed: `h1`–`h4` and `role="heading"` with `aria-level` 1–4, plus landmarks (`main`, `nav`, `article`, and `section` / `role="region"` only when it has an accessible name, following the WAI-ARIA landmark rules). Hidden entries are dropped (`hidden`, `inert`, `aria-hidden="true"`, no layout boxes, `visibility: hidden`), as are empty headings and Omni's own add-on UI. At most 300 entries; the count shows "300+" when a page has more. Primary sources: [WAI-ARIA 1.2 landmark roles](https://www.w3.org/TR/wai-aria-1.2/#landmark_roles), [HTML headings](https://html.spec.whatwg.org/multipage/sections.html#headings-and-outlines), [IntersectionObserver](https://www.w3.org/TR/intersection-observer/). Checked 2026-11-16.

Current section: one IntersectionObserver over the listed elements, its box the top 35 % of the viewport; the current entry is the last one that has reached that band. No timers or scroll polling.

Controller: in Omni the D-pad (up/down) and right stick reach the page as wheel events, Cross is a click at the pointer and Circle is history Back. While the outline is open it takes wheel events to move the selection, covers the page with a see-through layer so Cross anywhere goes to the selected entry (Cross on an entry goes to that one), and adds one history entry so Circle closes it. Going scrolls the page with `scrollIntoView` (smooth, or instant under `prefers-reduced-motion`) and leaves the panel open; the page stays visible to the left of the panel. Keyboard: arrows, Page Up/Down, Home/End, Enter, Escape, Alt+Shift+O.

Off by default. Switching it on from the quick switch while a page is open opens the outline straight away.
