# Native-language review: first 50 Thai catalog messages

Backlog: R3-042. Candidate only; not posted or assigned. Maintainer must confirm this gap is still open and reserve the scope before applying good first issue.

## Starting evidence

- `20261103-r3-042-more-languages/NEEDS.md`
- `20261103-r3-042-more-languages/locales/th.json`
- `20261103-r3-042-more-languages/source-catalog.json`

## Scope

Review exactly the 50 stable IDs below in th.json; preserve all other entries. These drafts already pass structural validation and still need native-language context review.

## Acceptance

- [ ] Complete templates/translation-review.md for all 50 IDs with wording decisions or explicit unchanged approval.
- [ ] Run python validate_catalog.py --locale th from R3-042 and retain zero format errors.
- [ ] Explain retained names/tokens and flag source plural/argument defects separately.
- [ ] State that remaining995 messages and native rendering are not approved by this batch.

## Out of scope

No whole-locale approval, source-ID changes, font replacement, external translation uploads or console deployment.

## Useful skills

Fluent/native Thai; JSON editing. No PS5 required.

## Exact source IDs

ui.44a0f82e9365, ui.328f0c288bc6, ui.362143c63df3, ui.ce2d12fd62aa, ui.6367dd8be5c4, ui.e652e3e588bd, ui.dc7c8e0a9e90, ui.56ae0f34c7da, ui.ecb70afb6a81, ui.05508df673eb, ui.bbca284a3392, ui.9a876cde5e3c, ui.bfa706302e0f, ui.1fed9cb8628a, ui.6eb3edeb8b14, ui.8dc63f5a70f2, ui.7e5adad20f46, ui.35d900116a14, ui.10402f5942dc, ui.b00d3040d483, ui.16cb53e95376, ui.d022cbe4dc18, ui.6cefa4f30ff9, ui.ea48296d20f7, ui.c52340b3a352, ui.1a9bfb992498, ui.b01216e42aaa, ui.30a9c50456a2, ui.47b54e57e081, ui.4234e9c6f3af, ui.b5234d71a330, ui.15fce4f6691a, ui.7e0379d5713f, ui.0d9d9e4e5a8b, ui.49caa46efea5, ui.b9d7789e5d37, ui.355216f46099, ui.ca4d3f5ac43d, ui.f6a3db6117fd, ui.7766e9bd405c, ui.f4e4405240b3, ui.42d71a8f56dd, ui.e64fadae259e, ui.6019533276f5, ui.49f1af7de2d2, ui.b6736deb5b3e, ui.df649604bdf3, ui.22fd6351b6ae, ui.ba1c19d31f8a, ui.60f9207a8c44

Source snapshot SHA-256: 1dd6187f93d009ceca65eb552a2b9576cf37615c10bf6d260f652e3f9055dfbf
