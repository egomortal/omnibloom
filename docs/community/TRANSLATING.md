# Contributing translations

Start by choosing one locale and a small set of IDs, then record your claim in Translations so reviewers do not duplicate work. A review of 25–50 messages is useful. No console is required for wording review, and no such review proves console font rendering.

## Source of truth and scope

The R3-042 package has source-catalog.json with 1,045 stable IDs and locales/<code>.json with exact ID-to-string mappings. Its eleven new locales are zh-Hans, zh-Hant, ru, ar, pl, tr, nl, id, hi, th and vi. All are drafts requiring native-language review. Traditional Chinese is a converted/terminology-reviewed draft and needs its own native review. This snapshot does not include every newly added R3 screen.

R3-019 Setup is a separate catalog: 222 base entries, seven translated locales (es, pt-BR, fr, de, ja, it, ko) plus English. Doctor and migration additions need separate extraction. Never paste keys from one catalog into the other or describe either snapshot as the entire product.

Use the current repository paths supplied by the maintainer. In this handback the references are sibling folders 20261103-r3-042-more-languages and 20261103-r3-019-setup-translations. Keep files UTF-8 and keep stable IDs unchanged. Record the source/catalog hash or commit with your review. Do not upload source strings, screenshots or private data to an external translation service.

## Editing and review

Read the source, screen context and formatter call site. Preserve Omnibloom, Omni, Master Control and Bloom Core as product names unless an approved locale glossary says otherwise. Prefer natural, concise instructions; do not shorten text by removing meaningful warnings or button distinctions. Translate strings as text, never executable expressions.

Preserve placeholder tokens and repetitions, HTML tag sequence, real newline counts, intentional whitespace and escaped newline meaning. Named placeholders can move with their labels. Positional printf arguments need the original semantic order: a token counter cannot prove that a translated sentence still associates the right value with the right noun. Do not add unapproved format syntax. Retained English needs a per-ID reason such as product name, URL or technical token; identical text is not automatically a valid translation.

For example, `%d file%s` is an English suffix construction. Do not remove its `%s`, insert a guessed plural suffix, or claim it works across languages merely because the formatter accepts it. Flag the source ID and call site for a plural-category migration. A maintainer must define complete-message variants, map old IDs and update every locale/call site together. Review representative counts 0, 1, 2, 5, 11, 21 and 101 as applicable; these are test examples, not a universal list of language plural rules. Source plural defects remain open until that migration is implemented and native-reviewed.

## Local validation

From the R3-042 package run:

```text
python validate_catalog.py --locale vi
```

Replace vi with your actual locale. For a genuinely partial draft use --partial only while working. A complete catalog needs all 1,045 IDs, no extra IDs, no format errors and reviewed sameAsSourceReview entries. The tool's complete flag means structural completeness; nativeReviewRequired remains true. Do not relabel that flag as linguistic approval. Re-run existing model/browser checks relevant to any UI changes; translation-only prose review does not require inventing new tests.

Record each ID, old/new wording, rationale, context and reviewer proficiency using templates/translation-review.md. A native reader should approve meaning, tone, terminology and mixed-direction values. Review a locale's whole coverage before calling it native-reviewed; one accepted batch does not approve the remaining messages.

## Visual and native acceptance

Use 1080p and 4K previews to check clipping, 22px body text, 44px targets, D-pad/Cross reachability, visible focus, Circle return, both glyph sets and reduced motion. Check long errors and narrow controls. Arabic needs joining/diacritics and mixed RTL/LTR URLs/numbers; Hindi needs conjuncts; Thai needs marks/line breaking; Chinese needs locale-appropriate forms and punctuation. Do not equate font cmap coverage with correct shaping. Native Tk/SDL consumers need their own font/render checks; WOFF2 web files do not automatically solve native fonts. PS5 hardware tests remain with authorized maintainers under the existing console procedure.

## Review handoff

Submit only the claimed locale/IDs plus the review record. Include source baseline, validator result, unchanged-entry decisions, screenshots when layout changed and open source defects. New source messages belong in a separate reviewed extraction change. Keep licence/provenance notices and use OFL fonts. Follow the existing CONTRIBUTING.md and SECURITY.md. Never include account credentials or a private screenshot in a public PR.
