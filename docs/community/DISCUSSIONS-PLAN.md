# Discussion categories plan

This is an offline proposal for egomortal/omnibloom. Reuse the round-two contributing/conduct/security files; merge these additions rather than replacing existing issue forms. Master Control-specific bugs belong in its repository; suite integration questions can remain here with a cross-link. No category, label, issue or discussion has been created.

| Category | Slug | Format | Purpose and routing |
|---|---|---|---|
| Announcements | announcements | Announcement | Maintainer release notes and verified project updates; distinguish shipped builds from prototypes. |
| Help | help | Question and answer | Setup and usage questions with version, redacted context and reproduction; mark a verified response as the answer. |
| Ideas | ideas | Open-ended | One user problem and a small proposal; convert accepted, scoped work into an issue with acceptance criteria. |
| Translations | translations | Open-ended | Claim a bounded locale review, discuss terminology and source-language problems; no blanket language approval from one reviewer batch. |
| Accessibility | accessibility | Open-ended | Focus, legibility, input and layout experience; include device/browser evidence and route confirmed defects to issues. |
| Show and tell | show-and-tell | Open-ended | Original themes, compatible add-ons and authorized screenshots with licences/provenance. |

GitHub supports these category formats; announcement posting is restricted to maintain/admin roles. Categories and slugs must exist before their matching forms are activated. See [category administration](https://docs.github.com/en/discussions/managing-discussions-for-your-community/managing-categories-for-discussions) and [discussion form syntax](https://docs.github.com/en/discussions/managing-discussions-for-your-community/syntax-for-discussion-category-forms).

Three ready-to-review forms are under proposed/.github/DISCUSSION_TEMPLATE for Help, Ideas and Translations. They use the JSON subset of YAML so local validation needs no third-party YAML package. They request no automatic labels or assignees. Keep the other categories free-form initially. Category administration is a separate manual maintainer action, not something these files perform.

## Triage practice

A maintainer checks duplicates, chooses the right repository and asks for the smallest useful reproduction. A confirmed defect becomes an issue linked both ways. Keep ideas open until scope and acceptance are agreed. Starter issues require a current source baseline, a maintainer willing to review, and one bounded deliverable; remove the label when the task expands. Do not label engine ports, authentication, update transactions or console deployment as beginner tasks.

Public reports should omit tokens, cookies, device addresses, personal paths and private browsing data. Use the repository's existing SECURITY.md for security reports rather than posting vulnerabilities publicly. Moderation follows CODE_OF_CONDUCT.md; do not invent new enforcement contacts here. No promised response deadline or release date.
