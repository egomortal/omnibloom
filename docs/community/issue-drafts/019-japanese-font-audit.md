# Record Japanese Setup font fallback on one desktop OS

Backlog: R3-019. Candidate only; not posted or assigned. Maintainer must confirm this gap is still open and reserve the scope before applying good first issue.

## Starting evidence

- `20261103-r3-019-setup-translations/NEEDS.md`

## Scope

On one explicitly named Windows/macOS/Linux environment, run the existing Setup translation preview with ja. Inspect three long Japanese controls/help/error strings and document the actual resolved font/fallback. Use fixtures only.

## Acceptance

- [ ] Record OS/version, preview baseline and three exact message keys.
- [ ] Attach redacted geometry/screenshots and list any clipped or missing glyphs.
- [ ] State that other OSes, Korean and PS5 rendering remain untested.

## Out of scope

No installer execution, real console connection, system-font installation, packaging/signing or changing unrelated locales.

## Useful skills

Japanese reading plus access to one desktop OS; maintainer provides fixture launch steps.
