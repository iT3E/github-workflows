# Changelog

Notable changes to this repository, newest first. Each PR adds a Changie
fragment under `.changes/unreleased/`; merging to `main` releases them.

## v1.9.3 - 2026-11-14

### Fixed

* release.yaml finishes a half-made release by itself. Every run tags, builds and publishes what the two newest versions on main still lack, so a run that died after its commit push (a rejected tag push, an API error) needs no hand work: the next run, a re-run or a dispatch on main finishes it. The tag push retries with a backoff and never moves a tag, the build is dispatched only when the tag has no run of it, the GitHub Release comes last, and the API calls use curl instead of the gh CLI. auto-fragment counts bot commits from the last release commit instead of the last tag, so a release whose tag is missing does not ship them twice. build-workflow must be a workflow file name or a numeric workflow id (a display name now fails), and the job needs curl and python3 instead of gh

## v1.9.2 - 2026-11-13

### Fixed

* Dependency updates: fix(github-release): update betterleaks/betterleaks to v1.10.1 (#30)

## v1.9.1 - 2026-11-13

### Fixed

* Dependency updates: chore(deps): update ruff to 0.17.5 (#29)

## v1.9.0 - 2026-11-12

### Changed

* secret-scan and actionlint run their release binaries instead of a container, and privacy-text calls the API with curl instead of the gh CLI, so they run on a self-hosted runner with no Docker and no gh. actionlint has a new input, shellcheck-version

## v1.8.1 - 2026-11-08

### Fixed

* Dependency updates: chore(deps): update zizmor to 1.32.0 (#20)

## v1.8.0 - 2026-11-08

### Added

* Composite actions in actions/: setup-flate (flate and the flate-guard hang guard), sticky-comment, terraform (plan/apply with redacted logs) and workflow-conformance; and a reusable zizmor.yaml workflow. Each has a self-test job.

## v1.7.0 - 2026-11-08

### Added

* `image.yaml`: `attest: true` attaches a mode=max SLSA provenance and an SBOM to the pushed image (off by default for now). PR builds read the Actions cache but no longer write it

## v1.6.0 - 2026-11-08

### Added

* `python.yaml`: `uv: true` sets Python up with uv (an activated .venv, `uv sync --locked` when there is a uv.lock, uv's cache) instead of setup-python. Off by default

## v1.5.0 - 2026-11-08

### Added

* Every reusable workflow takes `runs-on` (default `ubuntu-latest`) and `timeout-minutes` (a per-workflow default) inputs, so no job runs for the 6-hour default any more. Self-lint runs zizmor and checks that every job has a timeout

## v1.4.3 - 2026-11-08

### Fixed

* Dependency updates: feat(github-action): update docker/login-action action to v4.8.0 (#15)

## v1.4.2 - 2026-11-06

### Fixed

* Dependency updates: chore(deps): update ruff to 0.17.4 (#11)

## v1.4.1 - 2026-11-05

### Fixed

* Dependency updates: feat(github-release): update betterleaks/betterleaks to v1.10.0 (#10)

## v1.4.0 - 2026-11-05

### Added

* changelog.yaml: input exempt-paths, for paths a PR may change without a fragment.
* release.yaml: input app-client-id and secret RELEASE_APP_PRIVATE_KEY, so a GitHub App can push the release to a main behind a ruleset GITHUB_TOKEN can't bypass.

## v1.3.0 - 2026-11-03

### Changed

* renovate/default.json5: app-repo-template update PRs open and automerge at any time instead of the weekly window, so template releases reach app repos the same day.

## v1.2.1 - 2026-11-03

### Fixed

* actionlint.yaml: the header comment says how to run the same check locally (task lint). No behavior change.

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
