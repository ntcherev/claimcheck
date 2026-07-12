"""Tests for the v0.4 feedback round: `../` survives ellipsis trimming,
absence claims (claimcheck:gone), targeted inline ignore, root-mismatch note."""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from claimcheck.claims import ClaimType, extract
from claimcheck.cli import main
from claimcheck.markdown import parse
from claimcheck.verify import Verifier


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


class RepoCase(unittest.TestCase):
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

    def check_doc(self, rel):
        with open(os.path.join(self.root, rel)) as f:
            doc = parse(f.read(), rel)
        return Verifier(self.root).verify({rel: extract(doc)})


class TestEllipsisKeepsEscape(RepoCase):
    def test_escaping_ellipsis_cite_is_skipped_not_reported(self):
        # `../genai/.../Provider.java` explicitly points outside the repo;
        # trimming the ellipsis must not turn it into an in-repo claim.
        write(self.root, "docs/kb/infra.md",
              "See `../genai/genai-api/.../anthropic/Provider.java`.\n")
        res = self.check_doc("docs/kb/infra.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 1)

    def test_escaping_ellipsis_gets_no_suffix_rescue(self):
        # Same-basename file inside the repo must not satisfy the sibling cite.
        write(self.root, "src/anthropic/Provider.java", "class P {}\n")
        write(self.root, "docs/kb/infra.md",
              "See `../genai/.../anthropic/Provider.java`.\n")
        res = self.check_doc("docs/kb/infra.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 1)

    def test_in_repo_ellipsis_still_resolves(self):
        write(self.root, "src/deep/tripwire/TripwireExecutor.java", "class T {}\n")
        write(self.root, "doc.md", "See `.../tripwire/TripwireExecutor.java`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_checked, 1)


class TestGoneClaims(RepoCase):
    def test_gone_and_absent_is_clean(self):
        write(self.root, "doc.md",
              "`old/Removed.java` was deleted in the v2 rewrite. "
              "<!-- claimcheck:gone -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_checked, 1)

    def test_gone_but_present_is_error(self):
        write(self.root, "old/Removed.java", "class R {}\n")
        write(self.root, "doc.md",
              "`old/Removed.java` was deleted. <!-- claimcheck:gone -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual([(f.code, f.severity) for f in res.findings],
                         [("gone-still-exists", "error")])

    def test_gone_finds_reappearance_by_suffix(self):
        # A bare-name gone claim errors if any same-named file exists.
        write(self.root, "src/main/deep/BraveTool.java", "class B {}\n")
        write(self.root, "doc.md",
              "`BraveTool.java` no longer exists. <!-- claimcheck:gone -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual([f.code for f in res.findings], ["gone-still-exists"])
        self.assertIn("src/main/deep/BraveTool.java", res.findings[0].message)

    def test_gone_symbol_still_in_code_warns(self):
        write(self.root, "src/app.py", "def legacy_hook():\n    pass\n")
        write(self.root, "doc.md",
              "`legacy_hook()` was removed. <!-- claimcheck:gone -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual([(f.code, f.severity) for f in res.findings],
                         [("gone-still-exists", "warn")])

    def test_gone_symbol_absent_is_clean_not_symbol_missing(self):
        write(self.root, "doc.md",
              "`legacy_hook()` was removed. <!-- claimcheck:gone -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])


class TestTargetedIgnore(RepoCase):
    def test_pattern_ignores_only_matching_target(self):
        # The broken cite matching the pattern is dropped; the OTHER broken
        # cite on the same line must still be reported.
        write(self.root, "doc.md",
              "See `src/real.py` and `weird/pseudo.py`. "
              "<!-- claimcheck:ignore weird/* -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual([f.code for f in res.findings], ["path-missing"])
        self.assertIn("src/real.py", res.findings[0].message)

    def test_good_cites_on_ignoring_line_still_verified(self):
        write(self.root, "src/real.py", "x = 1\n")
        write(self.root, "doc.md",
              "See `src/real.py` and `weird/pseudo.py`. "
              "<!-- claimcheck:ignore weird/* -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_checked, 1)

    def test_bare_marker_still_skips_whole_line(self):
        write(self.root, "doc.md",
              "See `gone/one.py` and `gone/two.py`. <!-- claimcheck:ignore -->\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_checked, 0)


class TestRootMismatchNote(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")
        self._old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def test_note_when_config_root_is_not_git_toplevel(self):
        write(self.root, "module/.claimcheck.toml", "[claimcheck]\n")
        write(self.root, "module/README.md", "Hello.\n")
        os.chdir(os.path.join(self.root, "module"))
        code, _, err = run_cli("check")
        self.assertEqual(code, 0)
        self.assertIn("git's toplevel", err)

    def test_no_note_when_roots_agree(self):
        write(self.root, "README.md", "Hello.\n")
        os.chdir(self.root)
        code, _, err = run_cli("check")
        self.assertEqual(code, 0)
        self.assertNotIn("git's toplevel", err)
