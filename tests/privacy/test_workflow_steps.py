"""Tests for the steps of privacy.yaml and secret-scan.yaml that pick what checks a branch.

    python3 -m unittest discover -s tests/privacy -v

Each test takes the shell of one step out of the workflow file and runs it
with bash in a throwaway clone, with the env that GitHub would give it. A
branch of an author or an actor that is not the owner or Renovate must not
change what checks it: the checker, the allow file and the scan config come
from the default branch, and a new allow marker fails. The owner and
Renovate keep the files of their branch. The terms are invented words.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = ROOT / "bin" / "privacy-check"
OWNER = "example-owner"
TERM = "zorbexa"


def step(workflow: str, name: str) -> str:
    """The run block of the step with this name, as plain shell."""
    lines = (ROOT / ".github" / "workflows" / workflow).read_text().splitlines()
    start = lines.index(f"      - name: {name}")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for line in lines[run + 1:]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


def env_for(**extra: str) -> dict:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("PRIVACY_", "GIT_", "GITHUB_"))}
    e.update(GIT_AUTHOR_NAME="Example Person", GIT_AUTHOR_EMAIL="person@example.invalid")
    e.update(GIT_COMMITTER_NAME="Example Person", GIT_COMMITTER_EMAIL="person@example.invalid")
    e.update(extra)
    return e


class Clone(unittest.TestCase):
    """A repository with a default branch `main`, cloned, and a branch in the clone."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.origin, self.dir, self.temp = base / "origin", base / "clone", base / "runner"
        self.temp.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.origin)], check=True)
        (self.origin / "bin").mkdir()
        (self.origin / "bin" / "privacy-check").write_bytes(CHECKER.read_bytes())
        (self.origin / "bin" / "privacy-check").chmod(0o755)
        (self.origin / ".github").mkdir()
        (self.origin / ".github" / "privacy-allow").write_text("# globs\n")
        (self.origin / ".betterleaks.toml").write_text("# the config of main\n")
        (self.origin / ".betterleaksignore").write_text("# no fingerprint\n")
        (self.origin / "clean.txt").write_text("nothing to see\n")
        self.git(self.origin, "add", ".")
        self.git(self.origin, "commit", "-q", "-m", "init")
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.dir)], check=True, env=env_for())
        self.base = self.git(self.dir, "rev-parse", "HEAD").strip()
        self.git(self.dir, "checkout", "-q", "-b", "agent/work")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, where: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True, text=True,
                              env=env_for()).stdout

    def commit(self, path: str, text: str, message: str = "change"):
        f = self.dir / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        self.git(self.dir, "add", "-A")
        self.git(self.dir, "commit", "-q", "-m", message)

    def pr_env(self, author: str, actor: str | None = None, base: str = "main") -> dict:
        return dict(EVENT="pull_request", REF_TYPE="branch", REF_NAME="1/merge", DEFAULT_BRANCH="main",
                    BASE_REF=base, BASE_SHA=self.base, HEAD_SHA=self.git(self.dir, "rev-parse", "HEAD").strip(),
                    BEFORE_SHA="", OWNER=OWNER, AUTHOR=author, ACTOR=actor or author)

    def push_env(self, actor: str, before: str = "0" * 40) -> dict:
        return dict(EVENT="push", REF_TYPE="branch", REF_NAME="agent/work", DEFAULT_BRANCH="main",
                    BASE_REF="", BASE_SHA="", HEAD_SHA="", BEFORE_SHA=before, OWNER=OWNER, AUTHOR="", ACTOR=actor)

    def run_step(self, workflow: str, name: str, env: dict, **more: str):
        output = self.temp / "output"
        output.write_text("")
        e = env_for(RUNNER_TEMP=str(self.temp), GITHUB_OUTPUT=str(output), **env, **more)
        r = subprocess.run(["bash", "-e", "-c", step(workflow, name)], capture_output=True, text=True,
                           cwd=self.dir, env=e)
        outputs = dict(line.split("=", 1) for line in output.read_text().splitlines() if "=" in line)
        return r, outputs

    def marker_then_delete(self, marker: str):
        """A commit that adds a line with the marker, and a commit that deletes it again."""
        self.commit("notes.txt", f"token = x # {marker}\n")
        self.commit("notes.txt", "nothing here\n")

    def drop_default_branch(self):
        self.git(self.dir, "update-ref", "-d", "refs/remotes/origin/main")


class PrivacyCheck(Clone):
    def check(self, env: dict):
        return self.run_step("privacy.yaml", "Check", env, PRIVACY_TERMS=TERM, ALLOW_MISSING="false",
                             PRIVACY_EXTRA_TEXT="a title")

    def test_an_app_can_not_switch_off_the_checker_of_its_branch(self):
        self.commit("bin/privacy-check", "#!/usr/bin/env bash\nexit 0\n")
        self.commit("notes.txt", f"{TERM}\n")
        r = self.check(self.pr_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("hit: notes.txt:1", r[0].stdout)

    def test_an_actor_that_is_not_the_owner_gets_the_checker_of_main_too(self):
        self.commit("bin/privacy-check", "#!/usr/bin/env bash\nexit 0\n")
        self.commit("notes.txt", f"{TERM}\n")
        r = self.check(self.pr_env(OWNER, actor="example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)

    def test_an_app_can_not_widen_the_allow_file(self):
        self.commit(".github/privacy-allow", "# globs\nnotes.txt\n")
        self.commit("notes.txt", f"{TERM}\n")
        r = self.check(self.pr_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("hit: notes.txt:1", r[0].stdout)

    def test_a_new_marker_of_an_app_fails_even_with_no_term(self):
        self.commit("notes.txt", "a line privacy:allow\n")
        r = self.check(self.pr_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("privacy:allow marker", r[0].stdout)

    def test_the_owner_and_renovate_keep_the_files_of_their_branch(self):
        self.commit(".github/privacy-allow", "# globs\nnotes.txt\n")
        self.commit("notes.txt", f"{TERM}\n")
        self.commit("other.txt", "a line privacy:allow\n")
        for who in (OWNER, "renovate[bot]"):
            r = self.check(self.pr_env(who))
            self.assertEqual(r[0].returncode, 0, who + r[0].stdout + r[0].stderr)

    def test_a_clean_branch_of_an_app_passes(self):
        self.commit("notes.txt", "nothing here\n")
        r = self.check(self.pr_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 0, r[0].stdout + r[0].stderr)

    def test_a_new_branch_with_no_pr_is_checked_from_the_default_branch(self):
        # The term is in the message of the first commit of two; the old
        # range (HEAD~1..HEAD) saw the tip only.
        self.commit("a.txt", "one\n", message=f"first {TERM}")
        self.commit("b.txt", "two\n", message="second")
        r = self.check(self.push_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("(message or author/committer)", r[0].stdout)

    def test_a_push_to_an_existing_branch_checks_what_it_adds(self):
        self.commit("a.txt", "one\n")
        before = self.git(self.dir, "rev-parse", "HEAD").strip()
        self.commit("b.txt", f"{TERM}\n")
        r = self.check(self.push_env("example-app[bot]", before=before))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)

    def test_a_pr_of_an_app_to_another_base_fails(self):
        # The checks of base x stay green on the head when the base changes
        # to main later, so a base that is not main fails at once.
        self.commit("notes.txt", "nothing here\n")
        r = self.check(self.pr_env("example-app[bot]", base="x"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("the base of this PR is not main", r[0].stdout)

    def test_a_pr_of_the_owner_to_another_base_passes(self):
        self.commit("notes.txt", "nothing here\n")
        r = self.check(self.pr_env(OWNER, base="x"))
        self.assertEqual(r[0].returncode, 0, r[0].stdout + r[0].stderr)

    def test_a_marker_that_a_later_commit_deletes_still_fails(self):
        self.marker_then_delete("privacy:allow")
        for env in (self.pr_env("example-app[bot]"), self.push_env("example-app[bot]")):
            r = self.check(env)
            self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
            self.assertIn("privacy:allow marker", r[0].stdout)

    def test_a_marker_before_a_long_diff_still_fails(self):
        # grep reads all of its input, so a long diff after the marker can
        # not end the pipe early.
        self.commit("big.txt", "".join(f"line {i}\n" for i in range(40000)))
        self.commit("notes.txt", "a line privacy:allow\n")
        r = self.check(self.pr_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)

    def test_an_attributes_file_of_the_branch_can_not_hide_a_marker(self):
        self.commit(".gitattributes", "* -diff\n")
        self.commit("notes.txt", "a line privacy:allow\n")
        r = self.check(self.pr_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("privacy:allow marker", r[0].stdout)

    def test_no_default_branch_fails_for_an_app(self):
        self.commit("notes.txt", "nothing here\n")
        self.drop_default_branch()
        r = self.check(self.push_env("example-app[bot]"))
        self.assertEqual(r[0].returncode, 1, r[0].stdout + r[0].stderr)
        self.assertIn("no main branch", r[0].stdout)

    def test_the_body_of_each_author_but_renovate_is_checked(self):
        text = (ROOT / ".github" / "workflows" / "privacy.yaml").read_text()
        self.assertIn("github.event.pull_request.user.login != 'renovate[bot]' && github.event.pull_request.body", text)
        self.assertNotIn("user.type != 'Bot'", text)


class SecretScanConfig(Clone):
    def config(self, env: dict):
        return self.run_step("secret-scan.yaml", "Config of the default branch", env, CONFIG=".betterleaks.toml")

    def test_an_app_scans_with_the_config_and_ignore_file_of_main(self):
        self.commit(".betterleaks.toml", "# a branch that allows everything\n")
        self.commit(".betterleaksignore", "deadbeef:notes.txt:generic-api-key:1\n")
        r, out = self.config(self.pr_env("example-app[bot]"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(Path(out["config"]).read_text(), "# the config of main\n")
        self.assertEqual((self.dir / ".betterleaksignore").read_text(), "# no fingerprint\n")

    def test_an_ignore_file_that_main_does_not_have_goes(self):
        self.commit(".gitleaksignore", "deadbeef:notes.txt:generic-api-key:1\n")
        r, _ = self.config(self.pr_env("example-app[bot]"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.dir / ".gitleaksignore").exists())

    def test_a_new_allow_marker_of_an_app_fails(self):
        for marker in ("betterleaks:allow", "gitleaks:allow"):
            self.commit("notes.txt", f"token = x # {marker}\n")
            r, _ = self.config(self.pr_env("example-app[bot]"))
            self.assertEqual(r.returncode, 1, marker + r.stdout + r.stderr)

    def test_the_owner_and_renovate_keep_the_config_of_their_branch(self):
        self.commit(".betterleaks.toml", "# the owner's change\n")
        for who in (OWNER, "renovate[bot]"):
            r, out = self.config(self.pr_env(who))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(out["config"], ".betterleaks.toml")

    def test_a_push_of_an_app_reads_the_default_branch(self):
        self.commit(".betterleaks.toml", "# a branch that allows everything\n")
        r, out = self.config(self.push_env("example-app[bot]"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(Path(out["config"]).read_text(), "# the config of main\n")

    def test_a_pr_of_an_app_to_another_base_fails(self):
        r, _ = self.config(self.pr_env("example-app[bot]", base="x"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("the base of this PR is not main", r.stdout)

    def test_a_marker_that_a_later_commit_deletes_still_fails(self):
        self.marker_then_delete("gitleaks:allow")
        r, _ = self.config(self.pr_env("example-app[bot]"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_an_attributes_file_of_the_branch_can_not_hide_a_marker_or_a_diff(self):
        self.commit(".gitattributes", "* -diff\n")
        self.commit("notes.txt", "token = x # gitleaks:allow\n")
        r, _ = self.config(self.pr_env("example-app[bot]"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        # The scan after this step reads the clone with the same rule.
        log = self.git(self.dir, "log", "-p", "-1", "--format=", "--", "notes.txt")
        self.assertIn("+token = x", log)

    def test_no_default_branch_fails_for_an_app(self):
        self.drop_default_branch()
        r, _ = self.config(self.push_env("example-app[bot]"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_no_config_of_the_branch_reaches_the_scan(self):
        # main has no config here, so the scan runs with no --config; a
        # config file of the branch must not be in the folder either.
        self.git(self.origin, "rm", "-q", ".betterleaks.toml")
        self.git(self.origin, "commit", "-q", "-m", "no config")
        self.git(self.dir, "fetch", "-q", "origin")
        self.commit(".betterleaks.toml", "# a branch that allows everything\n")
        self.commit(".gitleaks.toml", "# a branch that allows everything\n")
        r, out = self.config(self.pr_env("example-app[bot]"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out["config"], "")
        self.assertFalse((self.dir / ".betterleaks.toml").exists())
        self.assertFalse((self.dir / ".gitleaks.toml").exists())

    def test_a_new_branch_scans_each_commit_it_adds(self):
        self.commit("a.txt", "one\n")
        self.commit("b.txt", "two\n")
        r, out = self.run_step("secret-scan.yaml", "Determine commit range", self.push_env("example-app[bot]"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out["log_opts"], "--no-merges refs/remotes/origin/main..HEAD")
        r, out = self.run_step("secret-scan.yaml", "Determine commit range", dict(self.push_env("x"), REF_TYPE="tag"))
        self.assertEqual(out["log_opts"], "-1")

    def test_the_scan_uses_the_config_of_the_step(self):
        text = (ROOT / ".github" / "workflows" / "secret-scan.yaml").read_text()
        self.assertIn("CONFIG: ${{ steps.config.outputs.config }}", text)


if __name__ == "__main__":
    unittest.main()
