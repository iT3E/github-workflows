#!/usr/bin/env bash
# Tests the "Finish the release" step of .github/workflows/release.yaml
# without GitHub: the step's run: script, taken from the workflow with yq,
# runs in a clone of a throwaway bare repo, with curl and sleep stubbed
# (fake-curl serves the API from a directory). The bare repo's hooks can
# reject tag pushes, race another run to the tag, or start a build run as
# a tag push with an app token would. At the end, the "Add auto-fragment"
# step counts bot commits from the last release commit, not the last tag.
#
#   tests/release/finish-test.sh [path/to/release.yaml]
#
# Needs bash, git, python3 and yq. Self: Test runs it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workflow="${1:-$here/../../.github/workflows/release.yaml}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

script="$work/finish.sh"
yq '.jobs.release.steps[] | select(.name == "Finish the release") | .run' "$workflow" > "$script"
if [ ! -s "$script" ] || ! grep -q 'finish()' "$script"; then
  echo "no 'Finish the release' step in $workflow" >&2
  exit 1
fi

mkdir -p "$work/bin"
cp "$here/fake-curl" "$work/bin/curl"
printf '#!/bin/sh\nexit 0\n' > "$work/bin/sleep"
chmod +x "$work/bin/curl" "$work/bin/sleep"

export GIT_AUTHOR_NAME=example GIT_AUTHOR_EMAIL=example@example.invalid
export GIT_COMMITTER_NAME=example GIT_COMMITTER_EMAIL=example@example.invalid
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

failures=0
case_name=""

# A new origin with a release commit (adding .changes/<v>.md), then one more
# commit, per version given. Leaves $origin, $api and $clone (made by run).
setup() {
  case_name="$1"
  shift
  local dir seed v
  dir="$work/$case_name"
  origin="$dir/origin.git"
  api="$dir/api"
  seed="$dir/seed"
  clone="$dir/clone"
  mkdir -p "$api"
  git init -q --bare -b main "$origin"
  cat > "$origin/hooks/pre-receive" <<'HOOK'
#!/bin/sh
# Test switches in $FAKE_API: reject-tags (how many tag pushes to refuse),
# race-tag (a commit: another run tags it first, then this push is refused).
rc=0
while read -r old new ref; do
  case "$ref" in refs/tags/*) ;; *) continue ;; esac
  echo "$ref" >> "$FAKE_API/tag-pushes"
  if [ -s "$FAKE_API/race-tag" ]; then
    commit="$(cat "$FAKE_API/race-tag")"; rm "$FAKE_API/race-tag"
    env -u GIT_QUARANTINE_PATH -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
      git tag -a "${ref#refs/tags/}" -m "made by another run" "$commit"
    rc=1
  elif [ -s "$FAKE_API/reject-tags" ] && [ "$(cat "$FAKE_API/reject-tags")" -gt 0 ]; then
    echo $(( $(cat "$FAKE_API/reject-tags") - 1 )) > "$FAKE_API/reject-tags"
    rc=1
  fi
done
exit "$rc"
HOOK
  cat > "$origin/hooks/post-receive" <<'HOOK'
#!/bin/sh
# push-starts-build: a tag push starts build-workflow (an app token's push).
while read -r old new ref; do
  case "$ref" in refs/tags/*) ;; *) continue ;; esac
  if [ -f "$FAKE_API/push-starts-build" ]; then
    mkdir -p "$FAKE_API/runs"; echo push >> "$FAKE_API/runs/${ref#refs/tags/}"
  fi
done
HOOK
  chmod +x "$origin/hooks/pre-receive" "$origin/hooks/post-receive"
  git clone -q "$origin" "$seed" 2> /dev/null
  echo "# example-app" > "$seed/README.md"
  git -C "$seed" add README.md
  git -C "$seed" commit -q -m "feat: start"
  for v in "$@"; do
    mkdir -p "$seed/.changes"
    printf '## %s - 2026-01-01\n\n### Fixed\n\n* a fix in %s\n' "$v" "$v" > "$seed/.changes/$v.md"
    git -C "$seed" add .changes
    git -C "$seed" commit -q -m "chore(release): $v"
    echo "$v" >> "$seed/README.md"
    git -C "$seed" commit -q -am "feat: after $v"
  done
  git -C "$seed" push -q origin main
}

# The commit on origin's main that added .changes/<v>.md.
added() { git -C "$origin" log -1 --format=%H --diff-filter=A main -- ".changes/$1.md"; }

# Make the state an earlier run left: tag (at the release commit, or $2),
# GitHub Release, build run.
tag() { git -C "$origin" tag -a "$1" -m "$1" "${2:-$(added "$1")}"; }
release() { mkdir -p "$api/releases"; echo "{\"tag_name\": \"$1\", \"made_by\": \"an earlier run\"}" > "$api/releases/$1.json"; }
build_ran() { mkdir -p "$api/runs"; echo push >> "$api/runs/$1"; }

# run NEW_VERSION BUILD_WORKFLOW APP_PUSH: clone origin (as the checkout
# does) and run the step. Sets $status and $output.
run() {
  rm -rf "$clone"
  git clone -q "$origin" "$clone"
  : > "$api/summary"
  set +e
  output="$(cd "$clone" && env PATH="$work/bin:$PATH" FAKE_API="$api" \
    NEW_VERSION="$1" BUILD_WORKFLOW="$2" APP_PUSH="$3" \
    GH_TOKEN=contents-token ACTIONS_TOKEN=actions-token \
    GITHUB_REPOSITORY=example-org/example-app GITHUB_API_URL=https://api.example.invalid \
    GITHUB_STEP_SUMMARY="$api/summary" bash "$script" 2>&1)"
  status=$?
  set -e
}

remote_tag() { git -C "$origin" rev-parse -q --verify "refs/tags/$1^{commit}" || true; }
count() { if [ -f "$1" ]; then grep -c -- "${2:-}" "$1" || true; else echo 0; fi; }
writes() { if [ -f "$api/log" ]; then grep -c '^POST' "$api/log" || true; else echo 0; fi; }

expect() {
  local what="$1"
  shift
  if "$@"; then
    echo "  ok    $what"
  else
    echo "  FAIL  $what"
    failures=$((failures + 1))
  fi
}
eq() { [ "$1" = "$2" ]; }
has() { grep -q -- "$2" <<< "$1"; }
latest() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("make_latest"))' "$api/releases/$1.json"; }
done_case() {
  if [ "$status" -ne 0 ] || [ -n "${VERBOSE:-}" ]; then
    while IFS= read -r line; do echo "        | $line"; done <<< "$output"
  fi
}

echo "== no version on main yet"
setup no-versions
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "says there is nothing to finish" has "$output" "No version on main yet"
expect "makes no API call" eq "$(count "$api/log")" 0
done_case

echo "== all present: tag, GitHub Release and build for the two newest"
setup all-present v0.1.0 v0.1.1 v0.1.2
for v in v0.1.0 v0.1.1 v0.1.2; do tag "$v"; release "$v"; build_ran "$v"; done
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "reads only the two newest releases" eq "$(cat "$api/log")" "$(printf 'GET /repos/example-org/example-app/releases/tags/v0.1.1\nGET /repos/example-org/example-app/releases/tags/v0.1.2')"
expect "pushes no tag" eq "$(count "$api/tag-pushes")" 0
expect "writes no step summary" eq "$(count "$api/summary")" 0
done_case

echo "== the incident: release commit on main, tag push rejected, nothing else made"
setup tag-missing v0.1.3 v0.1.4
tag v0.1.3; release v0.1.3; build_ran v0.1.3
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "tags v0.1.4 at the commit that added .changes/v0.1.4.md, not main's tip" eq "$(remote_tag v0.1.4)" "$(added v0.1.4)"
expect "dispatches build.yaml on v0.1.4 once" eq "$(cat "$api/dispatches")" "build.yaml v0.1.4"
expect "publishes the release as latest" eq "$(latest v0.1.4)" "true"
expect "uses .changes/v0.1.4.md as the notes" has "$(cat "$api/releases/v0.1.4.json")" "a fix in v0.1.4"
expect "logs it in the step summary" has "$(cat "$api/summary")" "Finished v0.1.4"
run "" build.yaml false
expect "a second run succeeds" eq "$status" 0
expect "and does nothing: no write" eq "$(count "$api/log" '^POST')" 2
done_case

echo "== tag present at the release commit, release missing, build ran"
setup tag-no-release v0.2.0
tag v0.2.0; build_ran v0.2.0
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "pushes no tag" eq "$(count "$api/tag-pushes")" 0
expect "dispatches no build" eq "$(count "$api/dispatches")" 0
expect "publishes the release" eq "$(latest v0.2.0)" "true"
done_case

echo "== tag present, release missing, no build yet"
setup tag-no-build v0.2.0
tag v0.2.0
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "dispatches the build" eq "$(cat "$api/dispatches")" "build.yaml v0.2.0"
expect "publishes the release" eq "$(latest v0.2.0)" "true"
done_case

echo "== tag at another commit"
setup tag-elsewhere v0.3.0
first="$(git -C "$origin" rev-list --max-parents=0 main)"
tag v0.3.0 "$first"
run "" build.yaml false
expect "fails" eq "$status" 1
expect "says why" has "$output" "the remote tag is at $first"
expect "leaves the tag where it was" eq "$(remote_tag v0.3.0)" "$first"
expect "changes nothing: no API write" eq "$(writes)" 0
expect "pushes no tag" eq "$(count "$api/tag-pushes")" 0
done_case

echo "== the first release of a repo"
setup first-release v0.1.0
run v0.1.0 build.yaml false
expect "succeeds" eq "$status" 0
expect "tags v0.1.0" eq "$(remote_tag v0.1.0)" "$(added v0.1.0)"
expect "dispatches build.yaml once" eq "$(cat "$api/dispatches")" "build.yaml v0.1.0"
expect "publishes v0.1.0 as latest" eq "$(latest v0.1.0)" "true"
done_case

echo "== a release refused for another reason"
setup release-refused v0.9.0
tag v0.9.0; build_ran v0.9.0
touch "$api/refuse-release"
run "" build.yaml false
expect "fails" eq "$status" 1
expect "shows the refusal" has "$output" "HTTP 422 .*refused by the fake"
done_case

echo "== a run that just released, previous version complete"
setup new-release v1.0.0 v1.1.0
tag v1.0.0; release v1.0.0; build_ran v1.0.0
run v1.1.0 build.yaml false
expect "succeeds" eq "$status" 0
expect "tags v1.1.0" eq "$(remote_tag v1.1.0)" "$(added v1.1.0)"
expect "dispatches build.yaml once" eq "$(cat "$api/dispatches")" "build.yaml v1.1.0"
expect "publishes v1.1.0 as latest" eq "$(latest v1.1.0)" "true"
expect "summary says released" has "$(cat "$api/summary")" "Released v1.1.0"
done_case

echo "== a run that just released, previous version left half made"
setup previous-half-made v1.0.0 v1.1.0
run v1.1.0 build.yaml false
expect "succeeds" eq "$status" 0
expect "tags both" eq "$(remote_tag v1.0.0) $(remote_tag v1.1.0)" "$(added v1.0.0) $(added v1.1.0)"
expect "builds both, oldest first" eq "$(cat "$api/dispatches")" "$(printf 'build.yaml v1.0.0\nbuild.yaml v1.1.0')"
expect "only the newest is latest" eq "$(latest v1.0.0) $(latest v1.1.0)" "false true"
done_case

echo "== the new version is not the newest on main"
setup not-newest v1.0.0 v1.1.0
tag v1.0.0; release v1.0.0; tag v1.1.0; release v1.1.0
run v1.0.0 build.yaml false
expect "fails" eq "$status" 1
expect "says why" has "$output" "newest version on main is v1.1.0"
done_case

echo "== no build workflow"
setup no-build v0.1.0
run "" "" false
expect "succeeds" eq "$status" 0
expect "never asks about runs" eq "$(count "$api/log" actions)" 0
expect "publishes the release" eq "$(latest v0.1.0)" "true"
done_case

echo "== tag push rejected twice, then accepted"
setup transient v0.4.0
echo 2 > "$api/reject-tags"
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "pushed three times" eq "$(count "$api/tag-pushes")" 3
expect "tags v0.4.0" eq "$(remote_tag v0.4.0)" "$(added v0.4.0)"
expect "publishes the release" eq "$(latest v0.4.0)" "true"
done_case

echo "== tag push rejected every time"
setup rejected v0.4.0
echo 99 > "$api/reject-tags"
run "" build.yaml false
expect "fails" eq "$status" 1
expect "gave up after five pushes" eq "$(count "$api/tag-pushes")" 5
expect "no build, no release" eq "$(writes)" 0
run "" build.yaml false
expect "while it is rejected, the next run fails too" eq "$status" 1
echo 0 > "$api/reject-tags"
run "" build.yaml false
expect "the next run once it is accepted finishes it" eq "$status:$(remote_tag v0.4.0):$(latest v0.4.0)" "0:$(added v0.4.0):true"
done_case

echo "== another run pushes the same tag first"
setup race-tag v0.5.0
added v0.5.0 > "$api/race-tag"
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "the tag is at the release commit" eq "$(remote_tag v0.5.0)" "$(added v0.5.0)"
expect "its tag object was kept, not replaced" eq "$(git -C "$origin" for-each-ref --format='%(contents:subject)' refs/tags/v0.5.0)" "made by another run"
done_case

echo "== another run publishes the release first"
setup race-release v0.6.0
tag v0.6.0; build_ran v0.6.0
touch "$api/race-release"
run "" build.yaml false
expect "succeeds" eq "$status" 0
expect "the other run's release stands" has "$(cat "$api/releases/v0.6.0.json")" "another run"
done_case

echo "== app token: the tag push starts the build"
setup app-push-builds v0.7.0
touch "$api/push-starts-build"
run "" build.yaml true
expect "succeeds" eq "$status" 0
expect "dispatches nothing" eq "$(count "$api/dispatches")" 0
expect "one build run" eq "$(count "$api/runs/v0.7.0")" 1
done_case

echo "== app token: build-workflow does not trigger on tags"
setup app-push-no-trigger v0.8.0
run "" build.yaml true
expect "succeeds" eq "$status" 0
expect "waits six times, then dispatches once" eq "$(count "$api/log" 'runs?branch=v0.8.0'):$(cat "$api/dispatches")" "7:build.yaml v0.8.0"
done_case

# The "Add auto-fragment" step, in a repo where it runs before the finish
# step: the newest release commit has no tag yet.
auto="$work/auto.sh"
yq '.jobs.release.steps[] | select(.name == "Add auto-fragment") | .run' "$workflow" > "$auto"
autorun() {
  set +e
  output="$(cd "$1" && env KIND=Fixed BODY="Dependency updates" SHIP_PATHS="." bash "$auto" 2>&1)"
  status=$?
  set -e
}
botcommit() {
  echo "$2" >> "$1/deps.txt"
  git -C "$1" add deps.txt
  GIT_AUTHOR_NAME="renovate[bot]" git -C "$1" commit -q -m "$2"
}

echo "== auto-fragment after a release whose tag is missing"
repo="$work/auto-fragment"
git init -q -b main "$repo"
printf 'kinds:\n  - label: Fixed\n    auto: patch\n' > "$repo/.changie.yaml"
mkdir -p "$repo/.changes"
echo "## v0.1.0" > "$repo/.changes/v0.1.0.md"
git -C "$repo" add -A
git -C "$repo" commit -q -m "chore(release): v0.1.0"
git -C "$repo" tag -a v0.1.0 -m v0.1.0
botcommit "$repo" "chore(deps): update example-lib to v2"
echo "## v0.1.1" > "$repo/.changes/v0.1.1.md"
git -C "$repo" add -A
git -C "$repo" commit -q -m "chore(release): v0.1.1"
echo "docs" > "$repo/notes.md"
git -C "$repo" add -A
git -C "$repo" commit -q -m "docs: a person's change"
autorun "$repo"
expect "succeeds" eq "$status" 0
expect "adds no fragment for a bot commit v0.1.1 shipped" eq "$(find "$repo/.changes" -name '*.yaml' | wc -l)" 0
expect "counts from the v0.1.1 release commit" has "$output" "chore(release): v0.1.1"
botcommit "$repo" "chore(deps): update example-lib to v3"
autorun "$repo"
expect "a bot commit after it still adds a fragment" eq "$(find "$repo/.changes/unreleased" -name '*.yaml' 2> /dev/null | wc -l)" 1
expect "naming only the new commit" has "$(cat "$repo"/.changes/unreleased/*.yaml)" "to v3$"
done_case

echo
if [ "$failures" -gt 0 ]; then
  echo "$failures check(s) failed"
  exit 1
fi
echo "all checks passed"
