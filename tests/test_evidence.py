"""Tests for ADR-018 (git-visible files are the truth domain) and ADR-019
(stamp staleness sees uncommitted edits)."""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from claimcheck.cli import main


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write(root, rel, content):
    if os.path.dirname(rel):
        os.makedirs(os.path.join(root, os.path.dirname(rel)), exist_ok=True)
    with open(os.path.join(root, rel), "w") as f:
        f.write(content)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class GitRepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        self._old_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def commit_all(self, msg="c"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)


class TestGitignoredInvisible(GitRepoCase):
    def test_present_gitignored_file_is_not_evidence_but_not_reported(self):
        # The CI-vs-local determinism bug: a gitignored file exists in this
        # checkout but not in a fresh clone. Verdict must match the clone's:
        # not evidence — but also not reportable, so: skipped.
        write(self.root, ".gitignore", "build/\n.claude/\n")
        write(self.root, "build/out.js", "var x;\n")
        write(self.root, ".claude/settings.local.json", "{}\n")
        write(self.root, "README.md",
              "Bundle is `build/out.js`; see `.claude/settings.local.json`.\n")
        code, out, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)
        self.assertIn("2 skipped", out)

    def test_absent_gitignored_file_not_reported_either(self):
        # Same doc in a fresh clone (no build output on disk): same verdict.
        write(self.root, ".gitignore", "build/\n")
        write(self.root, "README.md", "Bundle is `build/out.js`.\n")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)

    def test_untracked_file_is_still_evidence(self):
        # Untracked-but-not-ignored is part of the next commit; docs written
        # alongside new code must pass pre-commit (ADR-012 workflow).
        write(self.root, "src/new_module.py", "x = 1\n")
        write(self.root, "README.md", "See `src/new_module.py`.\n")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)

    def test_gitignored_doc_not_discovered(self):
        write(self.root, ".gitignore", "scratch/\n")
        write(self.root, "scratch/notes.md", "See `nope/gone.py`.\n")
        write(self.root, "README.md", "All fine here.\n")
        code, out, _ = run_cli("check")
        self.assertEqual(code, 0)
        self.assertIn("1 doc(s) scanned", out)

    def test_explicitly_passed_gitignored_doc_is_checked(self):
        write(self.root, ".gitignore", "scratch/\n")
        write(self.root, "scratch/notes.md", "See `nope/gone.py`.\n")
        code, out, _ = run_cli("check", "scratch/notes.md")
        self.assertEqual(code, 1)
        self.assertIn("path-missing", out)

    def test_deleted_but_tracked_file_reported_missing(self):
        write(self.root, "src/app.py", "x = 1\n")
        write(self.root, "README.md", "See `src/app.py`.\n")
        self.commit_all()
        os.remove(os.path.join(self.root, "src/app.py"))
        code, out, _ = run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("path-missing", out)

    def test_gitignored_import_skipped(self):
        write(self.root, ".gitignore", "local-notes.md\n")
        write(self.root, "CLAUDE.md", "@local-notes.md\n")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)


class TestStampSeesWorkingTree(GitRepoCase):
    def test_uncommitted_edit_to_cited_file_goes_stale(self):
        write(self.root, "src/app.py", "x = 1\n")
        write(self.root, "doc.md", "See `src/app.py`.\n")
        self.commit_all()
        code, _, _ = run_cli("stamp", "doc.md")
        self.assertEqual(code, 0)
        self.commit_all("stamp")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)
        # Edit the cited file WITHOUT committing: the stamp's promise is
        # already broken; --strict must catch it before the commit does.
        write(self.root, "src/app.py", "x = 2\n")
        code, out, _ = run_cli("check", "--strict")
        self.assertEqual(code, 1)
        self.assertIn("stamp-stale", out)
