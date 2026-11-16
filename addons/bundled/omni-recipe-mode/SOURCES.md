# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. No network: nothing is fetched, no remote code or rules run. Checked 2026-11-16.

## What counts as a recipe

Only what the page itself declares with the schema.org vocabulary ([Recipe](https://schema.org/Recipe), [HowToStep](https://schema.org/HowToStep), [HowToSection](https://schema.org/HowToSection)):

- JSON-LD (`<script type="application/ld+json">`), including `@graph`, top-level arrays, nested objects and `@type` arrays such as `["Recipe","NewsArticle"]`. Raw control characters inside strings are turned into spaces before a second parse. Other broken JSON is skipped.
- Microdata (`itemscope itemtype="https://schema.org/Recipe"`, [WHATWG HTML microdata](https://html.spec.whatwg.org/multipage/microdata.html)): `itemprop` values follow the spec's element rules (`meta` content, `time` datetime and so on). A `recipeInstructions` list (`ol`/`ul`) gives one step per `li`.

There is no fallback. A page without this markup gets no button: the add-on never guesses from headings or class names.

Read: `name`, `recipeIngredient` (or the older `ingredients`), `recipeInstructions` (text, text arrays, HowToStep, HowToSection, ItemList, HowToTip), `recipeYield`, `prepTime`, `cookTime`, `totalTime` and a step's `performTime`/`totalTime`/`timeRequired` (ISO 8601 durations). HTML and entities inside JSON-LD strings become plain text. Everything is drawn with createElement and textContent.

## Servings and timers

The scaler (×½, ×1, ×2) changes only the quantity at the start of an ingredient line: whole numbers, decimals (`1.5`, `1,5`), fractions (`1/2`, `½`, `1½`, `1 ½`, `1 1/2`) and ranges (`2-3`, `3 to 4`). The rest of the line is left alone, so "1 (400 g) tin" becomes "2 (400 g) tin". Lines without a leading number ("salt to taste", "one onion") are not changed.

A step gets a timer button for each duration it mentions ("10 minutes", "10-12 mins", "1 1/2 hours", "1 hour and 15 minutes", "30 seconds", "an hour", "5-minute"), or for its own `performTime` when the text has none. A range starts the shorter time. Timers keep running when you change step or close the view; a finished timer shows a flashing banner (or a toast when the view is closed). No sound: Omni's WebKit is built with Web Audio off (`omni/webkit/configure-cmd.json`).

## Controller

The view asks for full screen from the button press. In page full screen Omni sends pad buttons as keys (`OmniBrowser.cpp`, OMNI_FULLSCREEN_KEYS_V1): L1/R1 arrive as `j`/`l` and the D-pad as arrow keys, so L1/R1 or D-pad left/right step back and forward, D-pad up/down move along the ingredients, Square ticks one, Triangle starts or pauses the step's timer, L3 changes the amounts, Cross clicks under the pointer, Circle leaves full screen and closes the view. If full screen is refused, the view stays as an overlay; Omni's D-pad and L1/R1 then keep their usual browser jobs, so the on-screen buttons (pointer and Cross) do the work and Back closes.

## Keeping the screen on

The Screen Wake Lock API is used only if `navigator.wakeLock` exists. Omni's WebKit configuration does not list it, so expect it to be absent; the console's own screen dimming is not controlled.

## Stored data

One entry per recipe page in the add-on's own storage, keyed by a hash of the cleaned page address (tracking parameters dropped; the address itself is not stored): ticked ingredient numbers, the ingredient count (a changed recipe drops the ticks), the amounts choice, the current step and the time. At most 150 pages; the oldest are dropped. Private tabs: Omni refuses add-on storage writes there, so ticks and the step last only while that page is open.
