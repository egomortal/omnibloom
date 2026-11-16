# Licence and provenance

Original implementation, MIT; no upstream extension code is bundled. No network: nothing is fetched or sent. Checked 2026-11-16.

## What is kept

Text typed into `<textarea>` and `<input>` of type text, search, email or url (a missing or empty type counts as text). Never kept:

- `password`, `hidden`, and every other input type (number, tel, date, checkbox and so on);
- fields whose `autocomplete` has any `cc-*` token, `one-time-code`, `current-password` or `new-password` ([WHATWG HTML autofill](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill));
- fields whose `name` or `id` looks like a password, PIN, card number, CVC, one-time or verification code, IBAN or SSN;
- every field of a `<form>` that also holds a password field (sign-in and sign-up forms);
- read-only and disabled fields, and Omni's own add-on UI.

Only typing counts (trusted `input` events); script-set values are ignored.

## Where and how long

In the page's own `localStorage` (same origin as the page, so the site could read it, the same as its own drafts), one key per page: `omni-form-saver:` + a hash of origin + path (query and fragment are left out). The value is `{"f":{fieldKey:[text, savedAtMs]}}`. Field keys: `i:` + id; else `n:` + tag + name + its place among same-name fields; else `x:` + an XPath-like path from `<body>`.

Writes are debounced (700 ms) and flushed on `pagehide`, so a reload or Back keeps the last keystrokes. Text over 20 KB (UTF-8) is not kept; at most 50 fields per page, oldest dropped. Anything older than 24 h is dropped on read and other pages' stale keys under the prefix are swept when the add-on starts. A page whose `localStorage` is blocked or full gets nothing.

Submitting a form (`submit` event) deletes the page's key.

## Restoring

On a later visit (crash, reload, Back or back/forward cache), if a saved field is found and is still empty, a small bar asks "Restore what you typed?" with Restore and Dismiss. Restore fills only empty fields and fires `input` and `change` so the page notices; Dismiss deletes the page's saved text. Nothing is ever filled without Restore. Forms drawn by script are looked for on DOM changes (debounced 400 ms) for 15 s after load. The buttons are large pointer targets (left stick + Cross); Restore has focus, arrows move, Escape / Circle closes the bar and keeps the text.

## Private tabs

`private_safe` is false, so Omni never injects the add-on into private tabs (the same rule as Resume videos); the runtime also stops if the host reports a private tab.

Off by default.
