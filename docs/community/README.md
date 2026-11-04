# Community handback

- DISCUSSIONS-PLAN.md: six-category plan and triage rules.
- TRANSLATING.md: catalog-specific contributor guide and native/source-plural review boundaries.
- proposed/.github/DISCUSSION_TEMPLATE/: Help, Ideas and Translations forms; JSON syntax within YAML files.
- proposed/.github/ISSUE_TEMPLATE/translation-review.md: additive Markdown issue template.
- templates/translation-review.md: reusable evidence record for a bounded review.
- GOOD-FIRST-ISSUES.md, starter-issues.json and issue-drafts/: eight unposted starter candidates, each tied to existing backlog evidence.
- generate.py and validate.py: offline reproducible draft generation/structural checks; validation.json records the result.

Run python generate.py, then python validate.py. The generator reads the sibling R3-042 source snapshot and local backlog references. It does not modify that snapshot or any repository, does not contact GitHub and does not post issues. These files supplement the round-two community files; they do not replace existing conduct, security, bug-report or contribution policy.
