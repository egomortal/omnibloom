# Shared UI

The look every Omnibloom app shares on the TV.

- `design-system/`: `tokens.css` and `tokens.json` (colour, type, spacing, radius, motion, focus, elevation), `components.css` (buttons, lists, tiles, tabs, toggles, dialogs, toasts, the hint bar), `controller.js` (D-pad focus, Cross/Circle, L1/R1 tabs, and `window.omniMediaController`), and a preview page (`index.html`). Fonts: Inter and Rajdhani (SIL OFL 1.1), in `design-system/fonts/`.
- `glyphs/`: original Xbox-style and PlayStation-style button symbols (generic letters and shapes, no trademarked logos) as SVGs, `sprite.svg` and `mapping.json`. The setting only changes labels; the button mapping stays the same.
- `accessibility/tv-accessibility.css`: the TV readability layer (22 px minimum text at 1080p, 56 px targets, a 4 px focus outline, reduced motion, caption styling).

Text must stay at least 22 px at 1080p, everything must work with the D-pad and Cross, and focus must always be visible.
