# AGENTS.md

How to work in this repo: the reusable GitHub Actions workflows and
Renovate presets every app repo runs (README.md documents each one). It
is public, and every app repo's CI runs code from it.

## Change workflow

- Every change goes through a PR, squash-merged, with every check green
  (`gh-merge-safe.sh <pr> iT3E/github-workflows`). Never push to `main`.
- A PR adds a Changie fragment (`changie new`) or carries `skip-changelog`.
  Merging a fragment tags a release (`self-release.yaml`). App repos get
  it through app-repo-template (README "How updates reach app repos").
- The workflows without a `self-` prefix are called by app repos pinned to
  a release commit. Their file names, inputs, secrets, outputs and job
  names are an interface: adding an input with a default is minor,
  renaming, removing or changing a default is Breaking (a major release).
- A change to a build workflow (`go`, `python`, `image`) gets a call in
  `self-test.yaml` that exercises it, on the fixtures in `tests/`.
- Keep every reusable workflow `workflow_call` only, starting from
  `permissions: {}`, with actions pinned `@<sha> # vX.Y.Z`
  (`self-lint.yaml` checks).
- `bin/privacy-check` is a copy of app-repo-template's
  `template/bin/privacy-check`; change both together.

## Privacy

This repo is public. No family names, personal email addresses, store or
business names, household details, or anything else that says who is who
or where, in any file, path, commit message, PR or issue text, or comment.
Examples use `example-*` names.

- `bin/privacy-check` checks the tnwks-ops denylist: CI reads the
  `PRIVACY_TERMS` secret, locally it reads `$PRIVACY_TERMS` or a tnwks-ops
  checkout at `../tnwks-ops`. Never commit or print the list.
- Before posting a PR body, comment or review, write it to a file, run
  `bin/privacy-check --text < file`, and post with `--body-file`.
- No secrets in any file. Workflows get them only as `secrets:` from the
  caller.

## Writing

Plain prose, short sentences. No emdashes (use a comma, colon or
parentheses). No AI-attribution trailers in commits.
