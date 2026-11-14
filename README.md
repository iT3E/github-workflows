# github-workflows

Everything app repos run from another repo at CI time:

- **Reusable workflows** (`on: workflow_call`) in
  [`.github/workflows/`](.github/workflows): Go, Python, Node, the image build,
  the privacy and secret scans, actionlint, the changelog check, labels and
  the Changie release. The files without a `self-` prefix are the ones to
  call.
- **Renovate presets** in [`renovate/`](renovate): `default.json5` plus
  `go.json5`, `python.json5` or `node.json5`.

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
- **Secrets are passed by name**, never `secrets: inherit`. There are
  two: `PRIVACY_TERMS`, and `release.yaml`'s optional
  `RELEASE_APP_PRIVATE_KEY`.
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

Every workflow also takes two inputs that its tables don't repeat:

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `runs-on` | string | `ubuntu-latest` | runner label for every job |
| `timeout-minutes` | number | per workflow, below | timeout for each job |

`actionlint`, `changelog`, `labeler`, `privacy`, `privacy-text`,
`release`, `secret-scan` and `sync-labels` need no Docker and no gh CLI:
they run on a self-hosted runner image such as `ghcr.io/actions/actions-runner`
(bash, git, curl, tar, perl and python3).

The `timeout-minutes` defaults are 5 for `changelog`, `labeler`,
`privacy`, `privacy-text` and `sync-labels`; 10 for `actionlint`,
`secret-scan` and `zizmor`; 15 for `release`; 30 for `go`, `python` and `node`; and
60 for `image`.

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
| `python-version` | string | `3.12` | Python version (setup-python, or uv's managed Python with `uv`) |
| `working-directory` | string | `.` | where the checks run |
| `uv` | boolean | `false` | set Python up with uv: an activated `.venv` (`python` on PATH, no `pip`), `uv sync --locked` when `working-directory` has a `uv.lock`, uv's cache saved from the default branch only. `test-command` can use `uv run` |
| `ruff-check` | boolean | `false` | run `ruff check` with the repo's config |
| `ruff-format` | boolean | `false` | run `ruff format --check` |
| `ruff-version` | string | `0.17.3` (pinned) | ruff from PyPI |
| `test-command` | string | empty | test script |

### `node.yaml`: Node checks

Job `check`. Caller grants `contents: read`. No secrets.

`npm ci` (a `package-lock.json` is required), then the package's own
scripts: `npm run lint` and `prettier --check .` if enabled, `npm test`
and `npm run build` unless disabled, then `test-command`. Nothing is
framework specific: an Angular app's `package.json` scripts run `ng
lint`, `ng test --watch=false` and `ng build`. `npm test` must exit on
its own (no watch mode). The format check uses the repo's own prettier,
so it must be a devDependency.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `node-version` | string | `24` | setup-node version, unless `node-version-file` is set |
| `node-version-file` | string | empty | file setup-node reads the version from (e.g. `.nvmrc`), relative to `working-directory` |
| `working-directory` | string | `.` | where the checks run (the directory with `package.json`) |
| `lint` | boolean | `false` | run `npm run lint` |
| `format-check` | boolean | `false` | run `prettier --check .` |
| `test` | boolean | `true` | run `npm test` |
| `build` | boolean | `true` | run `npm run build` |
| `test-command` | string | empty | extra test script, after the build |

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
| `attest` | boolean | `false` | attach a mode=max SLSA provenance and an SBOM attestation to the pushed image |

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
`pull-requests: write`. Secret `PRIVACY_TERMS`. No inputs besides
`runs-on` and `timeout-minutes`.

GitHub can't refuse a comment, so this runs right after one is posted: a
comment with a hit is deleted, a review body is replaced, and an issue
only fails the run (an edit would keep the old text in its history). Bots
are skipped. The API calls use curl. Callers trigger it on `issue_comment`,
`pull_request_review_comment`, `pull_request_review` and `issues`. Keep it
a separate caller workflow from `privacy.yaml`, so a skipped run here
never stands in for the `privacy` check on a PR head.

### `secret-scan.yaml`: betterleaks

Job `betterleaks`. Caller grants `contents: read`. No secrets.

betterleaks over the commits a PR adds (or a push to `main` adds), with
the caller's config, redacted. The server-side twin of the pre-commit
hook. It runs the release binary, checked against the release's checksums.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `config` | string | `.betterleaks.toml` | config file, relative to the repo root |
| `betterleaks-version` | string | `v1.10.0` (pinned) | betterleaks release tag, with or without the `v` |

### `actionlint.yaml`: workflow lint

Job `actionlint`. Caller grants `contents: read`. No secrets.

actionlint, with shellcheck on `run:` blocks, over the caller's
workflows. App repos call it only on PRs that touch `.github/workflows/`.
It runs the actionlint release binary, checked against the release's
checksums, and the shellcheck release by its tag (shellcheck publishes no
checksums).

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `actionlint-version` | string | `v1.7.12` (pinned) | actionlint release tag, with or without the `v` |
| `shellcheck-version` | string | `v0.11.0` (pinned) | shellcheck release tag, with or without the `v` |

### `zizmor.yaml`: workflow security audit

Job `zizmor`. Caller grants `contents: read`. No secrets.

[zizmor](https://docs.zizmor.sh) over the caller's workflows and actions.
Findings are PR annotations; nothing is uploaded to code scanning. The
caller's `.github/zizmor.yml` applies if it has one, and single findings are
waived with a `# zizmor: ignore[<audit>] <reason>` comment on the line.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `zizmor-version` | string | `1.31.1` (pinned) | zizmor version |

### `changelog.yaml`: a Changie fragment per PR

Job `changelog`. Caller grants `contents: read`. No secrets.

Fails a PR that adds no `.changes/unreleased/*.yaml`, unless it carries
`skip-label`, was opened by Renovate or Dependabot, or changes nothing
outside `exempt-paths`, then checks the
fragments with `changie batch auto --dry-run`. Callers trigger it on
`pull_request` types `opened`, `synchronize`, `reopened`, `labeled` and
`unlabeled`, so adding the label re-runs it.

| Input | Type | Default | Meaning |
| --- | --- | --- | --- |
| `skip-label` | string | `skip-changelog` | label that waives the fragment |
| `exempt-paths` | string | empty | paths, one per line (a file, a directory or a glob, no `:(magic)`), a PR may change without a fragment; a PR that changes nothing else needs none |
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

Job `release`. Caller grants `contents: write` and `actions: write`.
Secret `RELEASE_APP_PRIVATE_KEY`, only with `app-client-id`. Output
`version` (empty when nothing was released).

1. Batches `.changes/unreleased/` into `.changes/<version>.md` and
   `CHANGELOG.md`.
2. Commits `chore(release): <version>` and pushes it to `main` (rebasing
   onto a moved `main`, up to 5 tries).
3. Tags the commit that added `.changes/<version>.md` (annotated) and
   pushes the tag (up to 5 tries, with a backoff).
4. Dispatches `build-workflow` on the tag, unless the tag already has a
   run of it, since a tag pushed with `GITHUB_TOKEN` starts no workflow.
5. Publishes a GitHub Release with the version's notes.

**A half-made release finishes itself.** Steps 3 to 5 run on every run,
for the two newest `.changes/v*.md` on `main`, and do only what is
missing. The GitHub Release comes last, so a version that has one is
finished: checking costs one API call per version, so two per run. If a
run dies after the commit push (a rejected tag push, an API error), the
next run finishes the version. To recover, dispatch the caller's Release
workflow on `main` with no note (`gh workflow run release.yaml --ref
main`), or wait for the next push to `main`. Re-run the failed run only
when it had no `fragment-body` (no note): a re-run reuses its inputs, so
it adds that fragment again and cuts one more release. app-repo-template
passes `fragment-body` when Renovate moves its pin, so don't re-run those.
No hand work is needed: do not tag, release or dispatch the build by
hand. The step summary lists what it finished. Its guards:

- Each version is finished on its own: a failure on the older one does
  not stop the newer one. The run then fails and names the version it
  could not finish.
- It never moves a tag. A remote tag at another commit fails that version
  and changes nothing for it; that one needs a person.
- It tags only the commit on `main` that added the version file, and
  releases only a version whose file is on `main`. A release is made only
  once its tag is on the remote.
- A tag push that another run beat, and a release that another run made,
  count as done. The build is dispatched only when the tag has no run of
  `build-workflow` (from any event), so a tag is not built twice. A tag
  the app token pushes does start workflows: the run waits up to 30
  seconds for that run before it dispatches.
- The newest version is the latest release; an older one it finishes is
  not marked latest.

It looks at two versions, not one, because in a repo that runs the release
only on pushes that add fragments, the next run that comes is a release
run. With no versions yet (a new repo), it does nothing.

What changed for callers in v1.9.3:

- The build is dispatched before the GitHub Release. A dispatch that
  fails (for example, a `build-workflow` without `workflow_dispatch`)
  stops the release of that version until it is fixed, and every run
  fails until then.
- A run with no fragments can now fail: an API error, or a tag at
  another commit, for one of the two newest versions.
- `build-workflow` must be a file name (`build.yaml`) or a numeric
  workflow id. A display name (`Build`), which `gh workflow run` used to
  accept, now fails every run.
- The job needs `curl` and `python3`, and no longer the gh CLI.
- The steps "Commit, tag, push", "GitHub Release" and "Build for the tag"
  are gone: now "Git identity", "Commit and push" and "Finish the
  release".

Nothing new is released without fragments. The version is Changie's next for
`bump` (`auto`: the highest fragment kind), or `first-version` while
`.changes/` has no `v*.md`. Callers trigger it on pushes to `main` (every
push when `auto-fragment` is set, else those touching
`.changes/unreleased/**`), plus `workflow_dispatch`, with a `concurrency`
group so releases run one at a time. `GITHUB_TOKEN` can push the release
commit only while no ruleset blocks it. When one does, set `app-client-id`
and pass `RELEASE_APP_PRIVATE_KEY`: a GitHub App the ruleset lets bypass
it pushes the commit and tag and publishes the release, with a token
scoped to `contents: write` on the calling repo. The commit is authored
by `<app-slug>[bot]`. The API calls use curl, not the gh CLI.

**Automatic releases for bot PRs.** Renovate and Dependabot PRs carry no
fragment (`changelog.yaml` waives it), so on their own they would never
ship. With `auto-fragment` set, when no fragment is pending and a commit
since the last release commit (the one that added the newest
`.changes/v*.md`) was authored by `renovate[bot]` or `dependabot[bot]`
and changed a path in `ship-paths`, the workflow adds one
`auto-fragment-kind` fragment, `<auto-fragment>: <their commit
subjects>`, and releases (a patch with the default `Fixed`). It looks at
every commit since that release commit, not only the pushed one, so a run
that `concurrency` dropped is caught up by the next. It counts from the
commit, not the tag, so a release whose tag is still missing doesn't ship
its bot commits a second time. A person's commit never
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
| `build-workflow` | string | `build.yaml` | caller workflow file name, or numeric workflow id, to dispatch on the tag (not a display name); empty: none |
| `changie-version` | string | `v1.26.0` (pinned) | Changie release |
| `fragment-kind` | string | `Changed` | kind of the `fragment-body` fragment |
| `fragment-body` | string | empty | add one fragment with this text before releasing; app-repo-template uses it to release when Renovate moves its pin of this repo |
| `auto-fragment` | string | empty | text of the automatic fragment for bot commits that changed `ship-paths` (see above); empty: off |
| `auto-fragment-kind` | string | `Fixed` | kind of that fragment |
| `ship-paths` | string | every path but docs and repo tooling | git pathspecs, one per line (`:(exclude)` allowed), for what a release ships |
| `app-client-id` | string | empty | client ID of a GitHub App that pushes the release, for a `main` behind a ruleset; needs `RELEASE_APP_PRIVATE_KEY`; empty: `GITHUB_TOKEN` pushes |

## Actions

Composite actions in `actions/`, for steps that live inside a caller's own
job rather than a whole workflow. Call them like any action, pinned to a
release commit:

```yaml
      - uses: iT3E/github-workflows/actions/setup-flate@<sha> # vX.Y.Z
        with:
          version: "0.6.5"
```

Their inputs and outputs are part of the interface, with the same semver
rules as the workflows. Each one has a job in `self-test.yaml`.

### `actions/setup-flate`

Installs [flate](https://github.com/home-operations/flate) (renders and
diffs Flux trees offline) to `/usr/local/bin` after checking the release's
SHA-256, and `flate-guard` next to it. `flate-guard <flate args>` caps each
run at `RENDER_TIMEOUT` (default `2m`) and retries a hang up to
`RENDER_ATTEMPTS` times (default 2), printing flate's process state and the
tail of its debug log before it kills a hung attempt. Use it in CI instead of
calling `flate` directly: flate occasionally hangs with no output.

| Input | Default | Meaning |
| --- | --- | --- |
| `version` | (required) | flate version without the `v`; pin it in the caller with a Renovate comment |

### `actions/sticky-comment`

Creates or updates one PR comment, found by a hidden marker at the start of
its body, so each run edits the same comment. The job needs
`pull-requests: write`. It uses only `curl` and `jq`, so it also runs on
lean self-hosted images without `gh`.

| Input | Default | Meaning |
| --- | --- | --- |
| `marker` | (required) | e.g. `<!-- plan-dns -->`; prepended if the body doesn't start with it |
| `body-file` | (required) | Markdown file with the body |
| `number` | the event's PR | PR number |
| `only-update` | `false` | update an existing comment but never create one (for "no changes" runs) |
| `author` | `github-actions[bot]` | whose comments count (the token's identity) |
| `token` | `github.token` | token to post with |

Output `comment-id`: the comment created or updated, empty if none.

### `actions/terraform`

Plans one Terraform root, and with `mode: apply` applies it when the plan
has changes. Written for public repos: the plan body never reaches the log,
only counts and the changed addresses (including moves), and on failure only
Terraform's error blocks. Needs `jq` (on GitHub's images) and whatever
credentials the root's backend and providers read from the environment.

| Input | Default | Meaning |
| --- | --- | --- |
| `working-directory` | (required) | the root module's directory |
| `mode` | (required) | `plan` or `apply` |
| `terraform-version` | `1.17.1` | for hashicorp/setup-terraform |
| `tf-api-token` | empty | HCP Terraform token, set as `TF_TOKEN_app_terraform_io` |
| `tf-vars` | empty | `TF_VAR_<name>=<value>` lines for non-secret overrides; anything else fails the step |

Outputs `summary` (Markdown, also in the job summary) and `changes`
(`true`/`false`). Post the summary with `actions/sticky-comment`.

### `actions/workflow-conformance`

The workflow conventions actionlint and zizmor don't check, over
`.github/workflows/`, `.github/actions/*/` and `actions/*/`: every job has a
`timeout-minutes` (15 at most on `ubuntu-slim`, where GitHub stops jobs at
15 minutes); `runs-on` is an allowed hosted label, a self-hosted label from
`.github/actionlint.yaml`, or an expression; a self-hosted job in a
`pull_request` workflow checks the PR comes from the same repo; remote
`uses:` are SHA-pinned and `docker://` images digest-pinned; every workflow
sets top-level `permissions`; every checkout sets `persist-credentials`
(false, or an explicit true for a job that pushes). Needs a checkout, plus
`python3` and `yq` (on every Ubuntu image, `ubuntu-slim` included).

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | repo root |
| `hosted-labels` | `ubuntu-26.04 ubuntu-slim` | space-separated hosted labels jobs may use |

## Renovate presets

An app repo's `.github/renovate.json5` (rendered by app-repo-template):

```json5
extends: [
  "github>iT3E/github-workflows//renovate/default.json5#vX.Y.Z",
  "github>iT3E/github-workflows//renovate/go.json5#vX.Y.Z",   // or python.json5, node.json5
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

[`renovate/node.json5`](renovate/node.json5): `renovate/node` labels and
`node` scopes, lock file maintenance (automerged), the Angular packages
(`@angular/*`, `@angular-devkit/*`, `@schematics/angular`, angular-eslint)
as one "Angular" group, `.nvmrc` and the `node` image as one "Node
runtime" group, and automerge for package and base image patch/digest and
non-0.x package minors.

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
  [`tests/python`](tests/python) (ruff and a test command), `node.yaml` on
  [`tests/node`](tests/node) (every check with `node-version`, then the
  defaults with `node-version-file`), and
  `image.yaml` on [`tests/image`](tests/image) with and without its
  Postgres service. The test image is never pushed. And
  [`tests/release/finish-test.sh`](tests/release/finish-test.sh): the
  script of `release.yaml`'s "Finish the release" step, taken from the
  workflow with yq, run against a throwaway bare repo with the API
  stubbed, for each half-made release case, plus the `auto-fragment`
  baseline. It runs locally too.
- `Self: Lint`: yamllint, shellcheck on `bin/*` and the release test, a
  check that every reusable workflow is `workflow_call` only, starts from
  `permissions: {}` and pins actions as `@<sha> # vX.Y.Z`, and
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
another kind). If a release run fails after its commit reached `main`,
start a new `Self: Release` run with no note: it finishes the tag and the
GitHub Release (see [`release.yaml`](#releaseyaml-changie-release)).
Re-run the failed run only if it had no note: a re-run reuses the note,
adds it as a fragment again and cuts one more release.

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
