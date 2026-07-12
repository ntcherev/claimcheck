"""Tests for v0.3 agent-file awareness: @import claims in CLAUDE.md /
CLAUDE.local.md / AGENTS.md, and skills-directory doc coverage."""

import io
import json
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


def imports_of(text, path="CLAUDE.md"):
    return [c for c in extract(parse(text, path)) if c.type == ClaimType.IMPORT]


class TestImportExtraction(unittest.TestCase):
    def test_line_start_and_mid_sentence(self):
        claims = imports_of("@AGENTS.md\n\nSee @docs/style.md for details.\n")
        self.assertEqual([c.value for c in claims], ["AGENTS.md", "docs/style.md"])

    def test_only_agent_file_basenames(self):
        for path in ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "sub/dir/CLAUDE.md"):
            self.assertEqual(len(imports_of("@AGENTS.md\n", path)), 1, path)
        for path in ("README.md", "docs/guide.md", "SKILL.md"):
            self.assertEqual(imports_of("@AGENTS.md\n", path), [], path)

    def test_code_spans_and_fences_are_not_imports(self):
        text = "Write `@AGENTS.md` to import.\n\n```markdown\n@fenced/example.md\n```\n"
        self.assertEqual(imports_of(text), [])

    def test_punctuation_stripped(self):
        claims = imports_of("First read @AGENTS.md, then (@docs/style.md).\n")
        self.assertEqual([c.value for c in claims], ["AGENTS.md", "docs/style.md"])

    def test_handles_and_emails_are_not_imports(self):
        text = "Ping @octocat or mail a@b.com about @deprecated code.\n"
        self.assertEqual(imports_of(text), [])

    def test_home_and_absolute_marked_outside_repo(self):
        claims = imports_of("Load @~/.claude/me.md and @/etc/notes.md.\n")
        self.assertEqual([c.value for c in claims],
                         ["~/.claude/me.md", "/etc/notes.md"])
        self.assertTrue(all(c.extra.get("outside_repo") for c in claims))

    def test_scoped_package_extracted_for_skip_accounting(self):
        # `@scope/pkg` has a slash so it is extracted; the verifier skips
        # it when missing (no known extension) rather than reporting.
        claims = imports_of("Uses @anthropic-ai/sdk under the hood.\n")
        self.assertEqual([c.value for c in claims], ["anthropic-ai/sdk"])


class ImportVerifyCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _verify(self, doc_path, text):
        doc = parse(text, doc_path)
        return Verifier(self.root).verify({doc_path: extract(doc)})

    def test_missing_import_is_error(self):
        res = self._verify("CLAUDE.md", "@AGENTS.md\n")
        self.assertEqual([(f.code, f.severity) for f in res.findings],
                         [("import-missing", "error")])

    def test_existing_import_is_clean(self):
        write(self.root, "AGENTS.md", "# agents\n")
        res = self._verify("CLAUDE.md", "@AGENTS.md\n")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_checked, 1)

    def test_no_suffix_match_rescue(self):
        # The file exists elsewhere in the tree, but not where the runtime
        # would resolve the import — that import is still broken.
        write(self.root, "elsewhere/style.md", "# style\n")
        res = self._verify("CLAUDE.md", "@docs/style.md\n")
        self.assertEqual([f.code for f in res.findings], ["import-missing"])

    def test_resolves_relative_to_importing_file(self):
        write(self.root, "sub/notes.md", "# notes\n")
        res = self._verify("sub/CLAUDE.md", "@notes.md\n")
        self.assertEqual(res.findings, [])
        res = self._verify("CLAUDE.md", "@notes.md\n")
        self.assertEqual([f.code for f in res.findings], ["import-missing"])

    def test_outside_repo_counted_skipped(self):
        res = self._verify("CLAUDE.md", "@~/.claude/me.md and @../up.md\n")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 2)

    def test_missing_without_known_ext_skipped(self):
        res = self._verify("AGENTS.md", "Uses @anthropic-ai/sdk internally.\n")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 1)


class TestImportsCli(unittest.TestCase):
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

    def test_dangling_import_fails_check(self):
        write(self.root, "CLAUDE.md", "@AGENTS.md\n")
        code, out, _ = run_cli("check", "--format", "json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["findings"][0]["code"], "import-missing")

    def test_valid_import_passes(self):
        write(self.root, "CLAUDE.md", "@AGENTS.md\n")
        write(self.root, "AGENTS.md", "# orientation\n")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)

    def test_severity_override_off(self):
        write(self.root, ".claimcheck.toml",
              "[claimcheck.severity]\n\"import-missing\" = \"off\"\n")
        write(self.root, "CLAUDE.md", "@AGENTS.md\n")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)

    def test_explain_shows_resolution(self):
        write(self.root, "CLAUDE.md", "@AGENTS.md\n")
        write(self.root, "AGENTS.md", "# orientation\n")
        code, out, _ = run_cli("check", "--explain")
        self.assertEqual(code, 0)
        self.assertIn("import", out)
        self.assertIn("doc-relative", out)


class TestSkillsDirCoverage(unittest.TestCase):
    """Skills are ordinary markdown to claimcheck; these lock in that
    `.claude/skills/**/SKILL.md` is discovered and checked like any doc."""

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

    def test_skill_doc_discovered_and_broken_ref_reported(self):
        write(self.root, ".claude/skills/demo/SKILL.md",
              "---\ndescription: demo skill\n---\n"
              "Read [the reference](references/gone.md) first.\n")
        code, out, _ = run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("link-broken", out)
        self.assertIn(".claude/skills/demo/SKILL.md", out)

    def test_healthy_skill_passes(self):
        write(self.root, ".claude/skills/demo/SKILL.md",
              "---\ndescription: demo skill\n---\n"
              "Read [the reference](references/notes.md) first.\n")
        write(self.root, ".claude/skills/demo/references/notes.md", "# notes\n")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)

    def test_stale_agent_worktree_is_not_evidence(self):
        # `.claude/worktrees` holds full agent-checkout copies of the repo;
        # a file deleted from the tree but surviving in a stale worktree
        # must still be reported missing, and worktree docs are not scanned.
        write(self.root, ".claude/worktrees/agent-abc123/src/gone.py", "x = 1\n")
        write(self.root, ".claude/worktrees/agent-abc123/README.md",
              "Stale copy citing `also/gone.py`.\n")
        write(self.root, "README.md", "See `src/gone.py`.\n")
        code, out, _ = run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("path-missing", out)
        self.assertNotIn("worktrees", out)
        self.assertIn("1 doc(s) scanned", out)
