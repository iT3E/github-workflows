# github-workflows

Everything app repos run from another repo at CI time:

- **Reusable workflows** (`on: workflow_call`) in
  [`.github/workflows/`](.github/workflows): Go, Python, the image build,
  the privacy and secret scans, actionlint, the changelog check, labels and
  the Changie release. The files without a `self-` prefix are the ones to
  call.
- **Renovate presets** in [`renovate/`](renovate): `default.json5` plus
  `go.json5` or `python.json5`.

App repos don't copy anything from here by hand. Their thin caller
workflows and their `.github/renovate.json5` are rendered by the Copier
template in [iT3E/app-repo-template](https://github.com/iT3E/app-repo-template),
which also pins the release of this repo they use (see
[How updates reach app repos](#how-updates-reach-app-repos)).

Contents: [Calling a workflow](#calling-a-workflow) ·
[Versions and pinning](#versions-and-pinning) ·
[Workflows](#workflows) · [Renovate presets](#renovate-presets) ·
[How updates reach app repos](#how-updates-reach-app-repos) ·
[CI](#ci) · [Releasing](#releasing) · [Privacy](#privacy) ·
[Working on this repo](#working-on-this-repo)

## Calling a workflow

```yaml
jobs:
  privacy:
    name: privacy
    permissions:
      contents: read
    uses: iT3E/github-workflows/.github/workflows/privacy.yaml@<sha> # vX.Y.Z
    secrets:
      PRIVACY_TERMS: ${{ secrets.PRIVACY_TERMS }}
```

- **Pin by commit SHA** with the tag as a comment, as for any action. The
  SHA is the commit the tag points at (`git ls-remote --tags
  https://github.com/iT3E/github-workflows 'vX.Y.Z^{}'`).
- **The caller owns the triggers** (`on:`), `concurrency` and any
  `paths:` filter, and grants the permissions listed for each workflow on
  the calling job. Every workflow here starts from `permissions: {}`.
- **Secrets are passed by name**, never `secrets: inherit`. The only one
  is `PRIVACY_TERMS`.
- **Check names** in the caller are `<caller job name> / <job name>`, e.g.
  `go / lint` or `privacy / privacy`. The job names below are part of the
  interface.
- Commands given as inputs (`test-command` and friends) run as bash
  scripts with `set -euo pipefail`, written to a file first, so a
  multi-line script behaves like a `run:` block.
- The privacy workflows run the **caller's** `bin/privacy-check`
  (app-repo-template renders it), so the matching is whatever the calling
  repo has.

## Versions and pinning

Releases are plain `vX.Y.Z` tags with a GitHub Release, cut by Changie
(see [Releasing](#releasing)). They started at `v1.0.0`: the interface was
already in use (it was `iT3E/app-template` v0.2.1 before the split).

The interface is every workflow's file name, inputs (name, type,
default), secrets, outputs and job names, and the presets' file names.
Semver applies to it:

| Change | Release |
| --- | --- |
| Bug fix, a newer pinned action or tool, a docs fix | patch (`Fixed` or `Security` fragment) |
| A new input with a default that keeps today's behaviour, a new output, a new workflow or preset rule | minor (`Added` or `Changed`) |
| A renamed or removed workflow, input, secret, output or job; a changed default | major (`Breaking`) |

Tags never move and are never deleted: every caller pins a tag's commit.

## Workflows

The defaults marked "(pinned)" are tool versions kept current by Renovate
here (`# renovate:` comments).

### `go.yaml`: Go checks

Jobs `lint` and `test`. Caller grants `contents: read`. No secrets.

- `lint`: `gofmt -l` must be empty, `go vet ./...`, then
  golangci-lint with the repo's `.golangci.yml` (v2 format; on pull
  requests only, reporting only the issues the PR introduces).
- `test`: `test-command`, then `extra-test-command` if set.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `go-version` | string | empty | Go version for setup-go; empty reads `go-version-file` |
| `go-version-file` | string | `go.mod` | file the version comes from, relative to `working-directory` |
| `working-directory` | string | `.` | directory with `go.mod` |
| `golangci-lint-version` | string | `v2.15.0` (pinned) | golangci-lint release (v2.x) |
| `test-command` | string | `go test -race ./...` | test script |
| `extra-test-command` | string | empty | more bash after `test-command`, same job |

### `python.yaml`: Python checks

Job `check`. Caller grants `contents: read`. No secrets.

`python -m compileall` (every file must parse; no dependencies needed),
then `ruff check` and `ruff format --check` if enabled, then
`test-command`. Tests that need the app's environment belong in the image
(`image.yaml`'s `test-command`).

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `python-version` | string | `3.12` | setup-python version |
| `working-directory` | string | `.` | where the checks run |
| `ruff-check` | boolean | `false` | run `ruff check` with the repo's config |
| `ruff-format` | boolean | `false` | run `ruff format --check` |
| `ruff-version` | string | `0.17.3` (pinned) | ruff from PyPI |
| `test-command` | string | empty | test script |

### `image.yaml`: build, test and push the image

Job `image`. Caller grants `contents: read` and `packages: write`.
Secret `PRIVACY_TERMS` (needed only when something is pushed). Output
`digest` (empty when nothing was pushed).

| Event | `push-main: true` | `push-main: false` |
| --- | --- | --- |
| pull request | build only (`pr-<n>` stays local) | build only |
| push to `main` | `:main`, `:sha-<short>` | build only |
| `v*` tag | `:<version>`, `:sha-<short>` | `:<version>`, `:sha-<short>` |
| `workflow_dispatch` | as the ref it runs on | as the ref it runs on |

Never `:latest` (`metadata-action` runs with `latest=false`). Before a
push, the caller's `bin/privacy-check` runs on the exact tree
(`privacy-gate: tree`) or on every commit the tag ships (`history`), and
a missing `PRIVACY_TERMS` fails the push. Build args `VERSION` (the
metadata version: `1.2.3`, `main` or `pr-<n>`) and `REVISION` (the
commit) are always passed. With `test-command`, the image is built
locally first and tested as `$IMAGE_REF`; the push reuses the build
cache.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `image` | string | empty | image name; empty is `ghcr.io/<owner>/<repo>`, lowercased |
| `context` | string | `.` | build context |
| `dockerfile` | string | `Dockerfile` | Dockerfile, relative to the repo root |
| `platforms` | string | empty | comma-separated target platforms; empty is the runner's |
| `build-args` | string | empty | extra `KEY=value` lines |
| `push-main` | boolean | `true` | push `:main` and `:sha-<short>` from `main`; `false` pushes only from `v*` tags |
| `privacy-gate` | string | `tree` | `tree` or `history` |
| `test-command` | string | empty | bash against the local build (`$IMAGE_REF`) before any push |
| `postgres` | boolean | `false` | a throwaway Postgres service (trust auth, user and database `postgres`) on `127.0.0.1:5432`, as `$TEST_POSTGRES_URL`; containers reach it with `--network host` |
| `postgres-version` | string | `18` (pinned) | Postgres image tag |

### `privacy.yaml`: the denylist on the tree, commits and PR text

Job `privacy`. Caller grants `contents: read`. Secret `PRIVACY_TERMS`.

Runs the caller's `bin/privacy-check` on every tracked file and path, on
the commits the event adds (messages, author and committer identities),
and on the PR title and body (a bot's PR body is skipped: it is
third-party release notes). Commit range: a PR checks `base..head`, a
push to `main` checks `before..HEAD`, a `v*` tag checks the whole history.
Hits print as `term #N: <where>`, never the matched text.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `allow-missing-terms` | boolean | `false` | warn and pass when the secret is missing (fork PRs on a public repo) |

Callers trigger it on `pull_request` (types `opened`, `synchronize`,
`reopened`, `edited`) and pushes to `main` (plus `v*` tags for a repo that
ships tags only).

### `privacy-text.yaml`: the denylist on comments, reviews and issues

Job `privacy-text`. Caller grants `contents: read`, `issues: write` and
`pull-requests: write`. Secret `PRIVACY_TERMS`. No inputs.

GitHub can't refuse a comment, so this runs right after one is posted: a
comment with a hit is deleted, a review body is replaced, and an issue
only fails the run (an edit would keep the old text in its history). Bots
are skipped. Callers trigger it on `issue_comment`,
`pull_request_review_comment`, `pull_request_review` and `issues`. Keep it
a separate caller workflow from `privacy.yaml`, so a skipped run here
never stands in for the `privacy` check on a PR head.

### `secret-scan.yaml`: betterleaks

Job `betterleaks`. Caller grants `contents: read`. No secrets.

betterleaks over the commits a PR adds (or a push to `main` adds), with
the caller's config, redacted. The server-side twin of the pre-commit
hook.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `config` | string | `.betterleaks.toml` | config file, relative to the repo root |
| `betterleaks-version` | string | `v1.9.0` (pinned) | betterleaks container tag |

### `actionlint.yaml`: workflow lint

Job `actionlint`. Caller grants `contents: read`. No secrets.

actionlint, with shellcheck on `run:` blocks, over the caller's
workflows. App repos call it only on PRs that touch `.github/workflows/`.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `actionlint-version` | string | `v1.7.12` (pinned) | actionlint container tag, with or without the `v` |

### `changelog.yaml`: a Changie fragment per PR

Job `changelog`. Caller grants `contents: read`. No secrets.

Fails a PR that adds no `.changes/unreleased/*.yaml`, unless it carries
`skip-label` or was opened by Renovate or Dependabot, then checks the
fragments with `changie batch auto --dry-run`. Callers trigger it on
`pull_request` types `opened`, `synchronize`, `reopened`, `labeled` and
`unlabeled`, so adding the label re-runs it.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `skip-label` | string | `skip-changelog` | label that waives the fragment |
| `changie-version` | string | `v1.26.0` (pinned) | Changie release |

### `labeler.yaml`: path labels

Job `labeler`. Caller grants `contents: read` and `pull-requests: write`.
No secrets.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `configuration-path` | string | `.github/labeler.yaml` | actions/labeler config (v5+ match objects) |

### `sync-labels.yaml`: labels from a file

Job `sync-labels`. Caller grants `contents: read` and `issues: write`. No
secrets.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `config-file` | string | `.github/labels.yaml` | labels file |
| `delete-other-labels` | boolean | `true` | delete labels that aren't in the file |

### `release.yaml`: Changie release

Job `release`. Caller grants `contents: write` and, with
`build-workflow`, `actions: write`. No secrets. Output `version` (empty
when nothing was released).

1. Batches `.changes/unreleased/` into `.changes/<version>.md` and
   `CHANGELOG.md`.
2. Commits `chore(release): <version>`, pushes it to `main` (rebasing onto
   a moved `main`, up to 5 tries), tags it (annotated) and pushes the tag.
3. Publishes a GitHub Release with the version's notes.
4. Dispatches `build-workflow` on the tag, since a tag pushed with
   `GITHUB_TOKEN` starts no workflow.

Nothing happens without fragments. The version is Changie's next for
`bump` (`auto`: the highest fragment kind), or `first-version` while
`.changes/` has no `v*.md`. Callers trigger it on pushes to `main` (every
push when `auto-fragment` is set, else those touching
`.changes/unreleased/**`), plus `workflow_dispatch`, with a `concurrency`
group so releases run one at a time. `GITHUB_TOKEN` can push the release
commit only while no ruleset blocks it.

**Automatic releases for bot PRs.** Renovate and Dependabot PRs carry no
fragment (`changelog.yaml` waives it), so on their own they would never
ship. With `auto-fragment` set, when no fragment is pending and a commit
since the last `v*` tag was authored by `renovate[bot]` or
`dependabot[bot]` and changed a path in `ship-paths`, the workflow adds
one `auto-fragment-kind` fragment, `<auto-fragment>: <their commit
subjects>`, and releases (a patch with the default `Fixed`). It looks at
every commit since the tag, not only the pushed one, so a run that
`concurrency` dropped is caught up by the next. A person's commit never
triggers it (a human PR brings its own fragment), and neither does a bot
commit outside `ship-paths`, such as a template update or a CI-only bump.
The default `ship-paths` is every path except the docs (`*.md`),
`.changes/`, `.github/` and the repo tooling app-repo-template manages
(`.copier-answers.yml`, `.pre-commit-config.yaml`, `Taskfile.yml`,
`bin/install-hooks`, `bin/privacy-check` and the dotfiles), which fits an
app repo whose image is built from the rest.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `bump` | string | `auto` | `auto`, `patch`, `minor` or `major` |
| `first-version` | string | `v0.1.0` | the first release |
| `build-workflow` | string | `build.yaml` | caller workflow file to dispatch on the tag; empty: none |
| `changie-version` | string | `v1.26.0` (pinned) | Changie release |
| `fragment-kind` | string | `Changed` | kind of the `fragment-body` fragment |
| `fragment-body` | string | empty | add one fragment with this text before releasing; app-repo-template uses it to release when Renovate moves its pin of this repo |
| `auto-fragment` | string | empty | text of the automatic fragment for bot commits that changed `ship-paths` (see above); empty: off |
| `auto-fragment-kind` | string | `Fixed` | kind of that fragment |
| `ship-paths` | string | every path but docs and repo tooling | git pathspecs, one per line (`:(exclude)` allowed), for what a release ships |

## Renovate presets

An app repo's `.github/renovate.json5` (rendered by app-repo-template):

```json5
extends: [
  "github>iT3E/github-workflows//renovate/default.json5#vX.Y.Z",
  "github>iT3E/github-workflows//renovate/go.json5#vX.Y.Z",   // or python.json5
],
```

The `#vX.Y.Z` is the same release the repo's workflow callers pin.

[`renovate/default.json5`](renovate/default.json5) starts from the same
base as tnwks-ops (`config:best-practices`, `docker:enableMajor`,
`:semanticCommits`, `:enablePreCommit`, `helpers:pinGitHubActionDigests`,
the dashboard) and extends three of its shared presets (`commitMessage`,
`labels`, `semanticCommits`). It adds:

- **The copier manager**, with template updates as their own
  `chore(template): update app-repo-template to vX.Y.Z` PRs, labeled
  `renovate/template`, automerged once every check is green (every update
  type: the template is our own and the PR runs the repo's CI on the new
  callers; the rule is last, so the review tiers don't hold its 0.x
  minors).
- **Template-owned versions off**: no Renovate updates in the files the
  template manages (the caller workflows, `.pre-commit-config.yaml`,
  `Taskfile.yml`), and none for `iT3E/github-workflows` pins (workflow
  `@<sha>` or preset `#vX.Y.Z`) anywhere. The template moves those.
- **Automerge** once every check is green: GitHub Actions
  minor/patch/digest (3 days after release, none for `actions/*`),
  pre-commit hooks, and CI tools pinned with `# renovate:` comments.
- **Reviewed** (left open): majors and 0.x minors.
- `platformAutomerge: false` (GitHub Free has no auto-merge on private
  repos; Renovate merges, squash), `schedule: ["before 7am on monday"]`
  (Actions minutes on private repos are metered), `docker:pinDigests` on.

[`renovate/go.json5`](renovate/go.json5): `renovate/go` labels and `go`
commit scopes, `gomodTidy` and `gomodUpdateImportPaths`, the go directive
and the `golang` image as one "Go toolchain" group, and automerge for Go
module and base image patch/digest and non-0.x minors.

[`renovate/python.json5`](renovate/python.json5): `renovate/python` labels
and `python` scopes, `constraints.txt` as a requirements file, automerge
for package and base image patch/digest and non-0.x package minors, and
Python image minors reviewed.

## How updates reach app repos

A release here reaches each app repo as one Renovate PR, in two hops, and
never conflicts with a later template update:

1. **Here:** a PR with a Changie fragment merges, and `self-release.yaml`
   tags `vX.Y.Z`.
2. **app-repo-template:** its `copier.yml` holds the one pin
   (`github_workflows: "vX.Y.Z@<sha>"`) that every rendered caller and
   preset reference uses, and its own callers use the same one. Its
   Renovate opens one grouped PR moving all of them, which merges itself
   once the template CI is green (majors wait for review). Merging it
   releases the template: the release workflow adds a fragment for the
   bump, since Renovate wrote none.
3. **Each app repo:** Renovate's copier manager opens
   `chore(template): update app-repo-template to vX.Y.Z`. That PR moves
   every caller pin and the preset `#vX.Y.Z` together, and the repo's own
   CI runs the new workflows on it. Renovate merges it once every check is
   green. It changes only repo tooling, so it releases nothing.

App repos never bump these pins themselves (`default.json5` turns that
off). If they did, a repo's pin would differ from the template's old one,
and the next `copier update` 3-way merge would conflict on every caller
line. app-repo-template's README has the details and the proof.

## CI

Every PR runs, with the workflows from the PR itself (local paths):

- `Self: Test`: `go.yaml` on [`tests/go`](tests/go) (Go from `go.mod`, and
  pinned with an `extra-test-command`), `python.yaml` on
  [`tests/python`](tests/python) (ruff and a test command), and
  `image.yaml` on [`tests/image`](tests/image) with and without its
  Postgres service. The test image is never pushed.
- `Self: Lint`: yamllint, shellcheck on `bin/*`, a check that every
  reusable workflow is `workflow_call` only, starts from `permissions:
  {}` and pins actions as `@<sha> # vX.Y.Z`, and
  `renovate-config-validator --strict` on the presets and this repo's
  config.
- `Self: Actionlint`, `Self: Secret Scan` (betterleaks), `Self: Privacy`,
  `Self: Changelog`, `Self: Labeler`.

`Self: Privacy (comments)`, `Self: Sync labels` and `Self: Release` run on
their own events. Merge with `gh-merge-safe.sh <pr> iT3E/github-workflows`
once every check is green. Never push to `main`.

## Releasing

1. In the PR, add a fragment (`changie new`). Pick the kind from
   [Versions and pinning](#versions-and-pinning). A PR that changes nothing
   callers see (this README, the self-tests) carries `skip-changelog`.
2. Merge it. `self-release.yaml` batches the fragments, commits
   `chore(release): vX.Y.Z`, tags it and publishes the GitHub Release.
3. app-repo-template's Renovate picks the tag up (see
   [How updates reach app repos](#how-updates-reach-app-repos)).

Renovate PRs here automerge on the tiers of `renovate/default.json5`
(actions minor/patch/digest, pinned tools minor/patch, hooks; majors and
0.x minors wait for review). They carry no fragment, so `self-release.yaml`
passes `auto-fragment`: a Renovate merge that changed a reusable workflow
(not a `self-*` one) or a preset in `renovate/` releases a patch on its
own, "Dependency updates: <subject>", and flows on to app-repo-template.
One that only touches this repo's own CI, hooks or Taskfile releases
nothing and ships with the next release. `Self: Release` can also be run
by hand with a `note` (it becomes a `Fixed` fragment unless you pick
another kind).

## Privacy

This repo is public, and the privacy rules of tnwks-ops apply in full: no
family names, personal email addresses, store or business names,
household details, or anything else that says who is who. Examples use
`example-*` names.

- The denylist lives only in tnwks-ops (`.github/privacy-terms.sops.yaml`)
  and is never committed or printed. CI reads it from this repo's
  `PRIVACY_TERMS` secret (`task privacy:sync` from a clone next to
  tnwks-ops). Fork PRs get no secrets, so `Self: Privacy` warns instead of
  failing on them.
- `bin/privacy-check` is a copy of app-repo-template's
  `template/bin/privacy-check`, kept in step with it and with tnwks-ops'
  own. Locally it reads `$PRIVACY_TERMS` or decrypts the list from
  `../tnwks-ops`.
- Before posting a PR body or comment, write it to a file, run
  `bin/privacy-check --text < file`, and post with `--body-file`.
- No secrets in any file. The workflows get them only from the caller's
  `secrets:`.

## Working on this repo

- `task precommit:init` installs the hooks (betterleaks, privacy-check on
  staged files, identity and message).
- `task lint` runs actionlint and the Renovate validator locally.
- A new input needs a default that keeps current callers' behaviour, a
  row in this README, and a call in `self-test.yaml` if it changes what a
  build workflow does.
