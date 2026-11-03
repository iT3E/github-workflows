# Changelog

Notable changes to this repository, newest first. Each PR adds a Changie
fragment under `.changes/unreleased/`; merging to `main` releases them.

## v1.2.0 - 2026-11-03

### Added

* node.yaml: Node checks for npm app repos (e.g. Angular). npm ci, then the package's lint, prettier --check, test and build scripts, each switchable, with node-version or node-version-file. renovate/node.json5: npm labels and scopes, lock file maintenance, the Angular packages and the Node runtime as groups, and automerge for patch/digest and non-0.x minors.

## v1.1.0 - 2026-11-03

### Added

* release.yaml: auto-fragment, auto-fragment-kind and ship-paths inputs. With auto-fragment set, a release with no pending fragment still happens when a renovate[bot] or dependabot[bot] commit since the last tag changed ship-paths (default: everything but docs and template-managed repo tooling). renovate/default.json5: app-repo-template (copier) PRs automerge once every check is green, every update type. This repo releases a patch by itself when a Renovate merge changes a reusable workflow or a preset.

## v1.0.2 - 2026-11-03

### Fixed

* renovate/default.json5: no digest pinning for versions in # renovate: comments. The regex has no digest to replace, so the "pin image postgres" update failed its branch (postgres-version in image.yaml, POSTGRES_VERSION in the rendered Taskfile).

## v1.0.1 - 2026-11-03

### Fixed

* release.yaml: a fragment-kind that is not a kind in the caller's .changie.yaml now fails before anything is written, naming the input, instead of later in changie batch. image.yaml: the header's Postgres and build-arg notes are wrapped as separate paragraphs.

## v1.0.0 - 2026-11-03

### Added

* First release: the reusable workflows (Go, Python, image, privacy, privacy-text, secret scan, actionlint, changelog, labeler, sync-labels, release) and the Renovate presets (default, go, python), moved from iT3E/app-template v0.2.1 with the same names, inputs and jobs. release.yaml gains fragment-kind and fragment-body.
