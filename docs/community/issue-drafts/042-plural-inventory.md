# Document three English file-suffix messages before plural migration

Backlog: R3-042. Candidate only; not posted or assigned. Maintainer must confirm this gap is still open and reserve the scope before applying good first issue.

## Starting evidence

- `20261103-r3-042-more-languages/NEEDS.md`
- `20261103-r3-042-more-languages/source-catalog.json`

## Scope

Produce an evidence table for these 3 source messages and locate their current formatter call sites. Record argument meaning, caller source path/line and source-count semantics. Mark missing call sites unresolved; do not invent them.

## Acceptance

- [ ] Cover each listed ID, exact source text and caller evidence or explicit unresolved note.
- [ ] Explain why token-preserving translation does not repair English suffix composition.
- [ ] Propose complete-message plural variants for maintainer review without changing IDs or runtime code.

## Out of scope

Actual plural engine, migration, locale rewrites and linguistically approved category rules are a separate experienced-maintainer task.

## Useful skills

Source search and documentation; formatter familiarity.

## Exact messages

- `ui.d022cbe4dc18` — `%s %s: checking %d file%s…`
- `ui.ddefdd2447d2` — `JDownloader 2 from this computer: %d file%s copied, %d already there.`
- `ui.f982fb200f82` — `Moved %d old JDownloader file%s aside (kept in setup-backup/%s).`
