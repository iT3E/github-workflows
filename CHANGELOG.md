# Changelog

Notable changes to this repository, newest first. Each PR adds a Changie
fragment under `.changes/unreleased/`; merging to `main` releases them.

## v1.0.2 - 2026-11-03

### Fixed

* renovate/default.json5: no digest pinning for versions in # renovate: comments. The regex has no digest to replace, so the "pin image postgres" update failed its branch (postgres-version in image.yaml, POSTGRES_VERSION in the rendered Taskfile).

## v1.0.1 - 2026-11-03

### Fixed

* release.yaml: a fragment-kind that is not a kind in the caller's .changie.yaml now fails before anything is written, naming the input, instead of later in changie batch. image.yaml: the header's Postgres and build-arg notes are wrapped as separate paragraphs.

## v1.0.0 - 2026-11-03

### Added

* First release: the reusable workflows (Go, Python, image, privacy, privacy-text, secret scan, actionlint, changelog, labeler, sync-labels, release) and the Renovate presets (default, go, python), moved from iT3E/app-template v0.2.1 with the same names, inputs and jobs. release.yaml gains fragment-kind and fragment-body.
