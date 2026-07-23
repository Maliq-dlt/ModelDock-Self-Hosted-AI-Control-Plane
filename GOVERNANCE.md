# Governance

ModelDock is maintainer-led. `@Maliq-dlt` owns release decisions, security response, and compatibility policy.

## Decision Rules

- Bug fixes and tests: maintainer can merge after CI.
- New provider adapters: require contract test and credential handling review.
- Schema/API changes: require migration or explicit compatibility note.
- Security changes: require threat model note and regression test.
- Architecture changes: require roadmap update and rollback plan.

## Release

Release uses SemVer. Breaking API/schema changes require a major version or compatibility layer. Every release updates `CHANGELOG.md`, image tags, chart version, and migration notes.
