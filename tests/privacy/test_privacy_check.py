"""Tests for bin/privacy-check: the two forms of the term list, and what it prints.

    python3 -m unittest discover -s tests/privacy -v

Runs the script with bash in throwaway git repositories. The terms are
invented words. privacy-check-1.9.3 is the script as released in v1.9.3,
kept to show what an older copy does with the encoded form.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent.parent / "bin" / "privacy-check"
OLD_SCRIPT = HERE / "privacy-check-1.9.3"
TERMS = ["zorbexa", "quilmarte", "an.example@example.invalid", "Tessaline"]
LEGACY = "# a comment\n" + "\n".join(TERMS) + "\n\n"


def run(script: Path, args: list[str], terms: str | None, cwd: Path, stdin: str = "", env: dict | None = None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("PRIVACY_", "GIT_"))}
    e["TNWKS_OPS_DIR"] = str(cwd / "no-such-dir")
    e.update(GIT_AUTHOR_NAME="Example Person", GIT_AUTHOR_EMAIL="person@example.invalid")
    e.update(GIT_COMMITTER_NAME="Example Person", GIT_COMMITTER_EMAIL="person@example.invalid")
    if terms is not None:
        e["PRIVACY_TERMS"] = terms
    e.update(env or {})
    return subprocess.run(["bash", str(script), *args], input=stdin, capture_output=True, text=True, cwd=cwd, env=e)


def encode(terms: str, cwd: Path) -> str:
    r = run(SCRIPT, ["--encode"], None, cwd, stdin=terms)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.dir)], check=True)
        (self.dir / "clean.txt").write_text("nothing to see\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        e = dict(os.environ, GIT_AUTHOR_NAME="Example Person", GIT_AUTHOR_EMAIL="person@example.invalid")
        e.update(GIT_COMMITTER_NAME="Example Person", GIT_COMMITTER_EMAIL="person@example.invalid")
        subprocess.run(["git", *args], cwd=self.dir, check=True, env=e)

    def check(self, terms, *args, stdin="", env=None, script=SCRIPT):
        return run(script, list(args), terms, self.dir, stdin=stdin, env=env)


class Forms(Repo):
    def test_legacy_list_clean(self):
        r = self.check(LEGACY)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_legacy_list_hit(self):
        (self.dir / "a.txt").write_text("hello Zorbexa\n")
        self.git("add", ".")
        self.assertEqual(self.check(LEGACY).returncode, 1)

    def test_encoded_list_hit_and_clean(self):
        value = encode(LEGACY, self.dir)
        self.assertTrue(value.startswith("#privacy-terms:v1:"))
        self.assertEqual(len(value.splitlines()), 1)
        self.assertEqual(self.check(value).returncode, 0)
        for t in TERMS:
            with self.subTest(term=t):
                r = self.check(value, "--text", stdin=f"text with {t} in it")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_encoded_list_with_surrounding_space(self):
        value = encode(LEGACY, self.dir)
        r = self.check(f"\n  {value}  \r\n", "--text", stdin="quilmarte")
        self.assertEqual(r.returncode, 1)

    def test_encode_accepts_an_encoded_list(self):
        value = encode(LEGACY, self.dir)
        again = encode(value, self.dir)
        self.assertEqual(self.check(again, "--text", stdin="zorbexa").returncode, 1)

    def test_every_encoding_differs(self):
        self.assertNotEqual(encode(LEGACY, self.dir), encode(LEGACY, self.dir))


class Unreadable(Repo):
    """A value that isn't a readable list stops the check (exit 2). It never
    becomes one long term that matches nothing."""

    def assert_stops(self, value):
        (self.dir / "a.txt").write_text("zorbexa\n")
        self.git("add", ".")
        r = self.check(value)
        self.assertEqual(r.returncode, 2, (value[:40], r.stdout, r.stderr))
        self.assertIn("nothing was checked", r.stderr)
        self.assertNotIn("clean", r.stdout)

    def test_empty(self):
        r = self.check("")
        self.assertEqual(r.returncode, 2)

    def test_only_comments(self):
        r = self.check("# nothing\n\n")
        self.assertEqual(r.returncode, 2)

    def test_garbage_after_prefix(self):
        self.assert_stops("#privacy-terms:v1:!!not base64!!")

    def test_base64_that_is_not_gzip(self):
        self.assert_stops("#privacy-terms:v1:aGVsbG8gd29ybGQ=")

    def test_truncated(self):
        value = encode(LEGACY, self.dir)
        self.assert_stops(value[:-12])

    def test_one_flipped_character(self):
        value = encode(LEGACY, self.dir)
        i = len(value) // 2
        flipped = value[:i] + ("A" if value[i] != "A" else "B") + value[i + 1 :]
        self.assert_stops(flipped)

    def test_unknown_version(self):
        value = encode(LEGACY, self.dir)
        self.assert_stops(value.replace(":v1:", ":v2:"))

    def test_prefix_without_hash(self):
        value = encode(LEGACY, self.dir)
        self.assert_stops(value[1:])

    def test_bare_base64(self):
        value = encode(LEGACY, self.dir)
        self.assert_stops(value.split(":", 2)[2])

    def test_encoded_plus_a_second_line(self):
        value = encode(LEGACY, self.dir)
        self.assert_stops(value + "\nzorbexa")


class OlderCopy(Repo):
    """What the released script (v1.9.3) does with the encoded form: it reads
    the line as a comment, finds no terms, and stops with exit 2. So a repo
    whose secret moved before its script fails its checks; it doesn't pass
    them without checking."""

    def test_old_script_stops_on_encoded_value(self):
        value = encode(LEGACY, self.dir)
        (self.dir / "a.txt").write_text("zorbexa\n")
        self.git("add", ".")
        for args, stdin in (([], ""), (["--text"], "zorbexa"), (["--commits", "HEAD"], "")):
            with self.subTest(args=args):
                r = self.check(value, *args, stdin=stdin, script=OLD_SCRIPT)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("clean", r.stdout)

    def test_old_script_reads_legacy(self):
        (self.dir / "a.txt").write_text("zorbexa\n")
        self.git("add", ".")
        self.assertEqual(self.check(LEGACY, script=OLD_SCRIPT).returncode, 1)


class Output(Repo):
    """No term, no term number and no count in anything it prints."""

    def assert_quiet(self, r):
        out = r.stdout + r.stderr
        for t in TERMS:
            self.assertNotIn(t.lower(), out.lower())
        self.assertNotRegex(out, r"#\s*\d")
        self.assertNotRegex(out, r"(?i)\bterms?\b[^.\n]*\d|\d+[ \t]+(terms?|hits?)")

    def test_text_hit(self):
        value = encode(LEGACY, self.dir)
        r = self.check(value, "--text", stdin="zorbexa and quilmarte and an.example@example.invalid")
        self.assertEqual(r.returncode, 1)
        self.assert_quiet(r)
        self.assertEqual(r.stdout.strip().splitlines(), ["hit: text"] * 3)
        self.assertNotRegex(r.stdout + r.stderr, r"\d")

    def test_file_commit_and_pr_text_hits(self):
        (self.dir / "notes.txt").write_text("one\nQuilmarte here\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "about tessaline")
        (self.dir / "more.txt").write_text("zorbexa\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "plain")
        value = encode(LEGACY, self.dir)
        r = self.check(value, "--commits", "HEAD~2..HEAD", env={"PRIVACY_EXTRA_TEXT": "title zorbexa"})
        self.assertEqual(r.returncode, 1)
        self.assert_quiet(r)
        hits = sorted(r.stdout.strip().splitlines())
        self.assertIn("hit: notes.txt:2", hits)
        self.assertIn("hit: more.txt:1", hits)
        self.assertIn("hit: PR title or body", hits)
        self.assertEqual(sum(1 for h in hits if h.startswith("hit: commit ")), 1)
        self.assertNotIn("null byte", r.stderr)

    def test_path_hit_names_the_path(self):
        # A path is reported as it is: it is already in the PR for anyone to see.
        (self.dir / "zorbexa-notes.txt").write_text("one\n")
        self.git("add", ".")
        r = self.check(encode(LEGACY, self.dir))
        self.assertEqual(r.returncode, 1)
        self.assertIn("hit: path zorbexa-notes.txt", r.stdout)

    def test_bad_range_stops(self):
        r = self.check(encode(LEGACY, self.dir), "--commits", "no-such-ref..HEAD")
        self.assertEqual(r.returncode, 2)

    def test_clean_prints_no_count(self):
        r = self.check(encode(LEGACY, self.dir))
        self.assertEqual(r.stdout.strip(), "privacy-check: clean")

    def test_encode_prints_only_the_value(self):
        r = run(SCRIPT, ["--encode"], None, self.dir, stdin=LEGACY)
        self.assertEqual(r.stderr, "")
        self.assertEqual(len(r.stdout.splitlines()), 1)

    def test_encoded_value_holds_no_term(self):
        short = ["ab", "zorbexa", "Kim", "xq"]
        for _ in range(20):
            value = encode("\n".join(short), self.dir)
            for t in short:
                self.assertNotIn(t.lower(), value.lower())


class FailedSearch(Repo):
    """A search tool that fails stops the check with exit 2 and prints
    nothing it was given."""

    def test_grep_error_stops(self):
        bindir = self.dir / "fakebin"
        bindir.mkdir()
        real = subprocess.run(["bash", "-c", "command -v grep"], capture_output=True, text=True).stdout.strip()
        fake = bindir / "grep"
        fake.write_text(f'#!/bin/sh\ncase " $* " in *" -P "*) echo "grep: error in $*" >&2; exit 2;; esac\nexec {real} "$@"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        path = f"{bindir}:{os.environ['PATH']}"
        value = encode(LEGACY, self.dir)
        r = self.check(value, "--text", stdin="zorbexa", env={"PATH": path})
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing was checked", r.stderr)
        self.assertNotIn("zorbexa", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main()
