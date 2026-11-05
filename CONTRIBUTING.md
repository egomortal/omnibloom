# Contributing to Omnibloom

Start with the README and the build instructions included in your checkout. Use the bug or feature template for ordinary reports. Include the exact app build and console firmware; a screenshot alone does not identify a release. For a large change, discuss the intended user benefit before implementation.

## Build on the shared project

We’d love improvements to come back to the shared project so everyone can benefit from the same maintained baseline. If you have an idea—VR support, for example—talk it through with the maintainers first. Explain what people could do with it and how you would test it.

When it is ready, send a focused pull request through the current maintainer channel. These repositories are currently private, so contributors with access should use the repository’s pull-request flow; if you do not have access, ask the maintainers how to share your proposal. You do not need direct push access. Maintainers review changes before merging, and submitting a change does not guarantee acceptance.

Include the tests you ran, results, documentation and any compatibility limits. Keep the change based on the current shared baseline, and say what still needs testing. If you can, help with follow-up fixes and keeping the feature up to date; contributing does not commit you to ongoing unpaid maintenance.

We prefer collaboration upstream over leaving useful improvements only in permanently separate copies. Forks are welcome too, and this preference does not limit your rights under the project’s GPL license.

Keep pull requests focused. Explain the visible result, provide the checks you actually ran and identify untested behavior. Local fixtures do not establish console compatibility or performance. UI contributions should preserve controller navigation, readable text, reduced-motion behavior and existing language choices. Do not claim a translated draft has native-speaker review unless someone performed it.

Preserve source credits, copyright and license notices. Document the origin, version and license of added dependencies or assets. Follow the license already attached to each file. Do not submit proprietary SDK material, credentials, private logs or unapproved binary artifacts.

For support, provide `/data/omni/native/crash.log`, `boot.log` from the installed build’s documented log location, and `/data/hub/logs/<app>/` (replace `<app>` with the affected app ID). If a file is absent or its location is unknown, say so; do not create an empty log.

Review and redact copies before attaching them. Never send a full unreviewed console folder. If a report may reveal a security problem, use [SECURITY.md](SECURITY.md). Community participation follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). A dedicated confidential reporting contact has not been named yet; ask a maintainer for a private way to talk.

Maintainers review and publish accepted changes. A proposed patch, CI result or draft release note is not release approval.
