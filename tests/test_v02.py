"""Tests for the v0.2 feature set: fence command claims, --since, --explain,
per-code severity overrides, stamp --all-stale."""

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


class CliCase(unittest.TestCase):
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


class TestFenceClaims(unittest.TestCase):
    def test_extracts_from_bash_fence_only(self):
        doc = parse(
            "```bash\n./scripts/dev.sh --fast\ncp config/a.yml config/b.yml\n```\n"
            "```text\nignored/example.py\n```\n"
            "```\nalso/ignored.py\n```\n", "x.md")
        claims = [c for c in extract(doc) if c.extra.get("fence")]
        self.assertEqual(sorted(c.value for c in claims),
                         ["config/a.yml", "config/b.yml", "scripts/dev.sh"])
        self.assertTrue(all(c.type == ClaimType.PATH for c in claims))

    def test_fence_line_numbers_and_noise(self):
        doc = parse(
            "intro\n\n```sh\n# comment scripts/no.sh\n$ python3 tools/gen.py\n"
            "git clone https://github.com/a/b.git\ncurl -o /tmp/x.bin example.com\n```\n",
            "x.md")
        claims = [c for c in extract(doc) if c.extra.get("fence")]
        self.assertEqual([(c.value, c.line) for c in claims], [("tools/gen.py", 5)])

    def test_fences_can_be_disabled(self):
        doc = parse("```bash\n./scripts/dev.sh\n```\n", "x.md")
        self.assertEqual(extract(doc, fences_enabled=False), [])

    def test_missing_fence_path_warns_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "doc.md", "```bash\n./scripts/gone.sh\n```\n")
            with open(os.path.join(root, "doc.md")) as f:
                claims = extract(parse(f.read(), "doc.md"))
            res = Verifier(root).verify({"doc.md": claims})
            self.assertEqual([(f.code, f.severity) for f in res.findings],
                             [("command-path-missing", "warn")])

    def test_existing_fence_path_resolves(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "scripts/dev.sh", "#!/bin/sh\n")
            write(root, "doc.md", "```bash\n./scripts/dev.sh\n```\n")
            with open(os.path.join(root, "doc.md")) as f:
                claims = extract(parse(f.read(), "doc.md"))
            res = Verifier(root).verify({"doc.md": claims})
            self.assertEqual(res.findings, [])


class TestSince(CliCase):
    def test_scopes_to_changed_docs(self):
        write(self.root, "app.py", "x\n")
        write(self.root, "stale.md", "Bad `gone.py` reference.\n")
        write(self.root, "other.md", "fine\n")
        self.commit_all()
        # Nothing changed since HEAD → the broken doc is not checked.
        code, out, _ = run_cli("check", "--since", "HEAD")
        self.assertEqual(code, 0)
        self.assertIn("nothing to check", out)
        # Touch only the clean doc → still passes, broken doc stays out of scope.
        write(self.root, "other.md", "fine, edited\n")
        code, out, _ = run_cli("check", "--since", "HEAD", "--format", "json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"]["docs_scanned"], 1)
        # Untracked new doc is included and fails.
        write(self.root, "new.md", "Another `missing.py` reference.\n")
        code, out, _ = run_cli("check", "--since", "HEAD")
        self.assertEqual(code, 1)
        self.assertIn("path-missing", out)

    def test_bad_ref_exits_two(self):
        write(self.root, "a.md", "hello\n")
        self.commit_all()
        code, _, err = run_cli("check", "--since", "not-a-ref")
        self.assertEqual(code, 2)
        self.assertIn("cannot resolve ref", err)


class TestSeverityOverrides(CliCase):
    def test_promote_and_silence(self):
        write(self.root, ".claimcheck.toml",
              '[claimcheck]\nsymbols = "warn"\n'
              '[claimcheck.severity]\nanchor-missing = "error"\nsymbol-missing = "off"\n')
        write(self.root, "doc.md",
              "[x](doc.md#nope) and `vanished_thing.zap()`\n")
        code, out, _ = run_cli("check", "--format", "json")
        self.assertEqual(code, 1)  # anchor promoted to error
        data = json.loads(out)
        codes = {f["code"]: f["severity"] for f in data["findings"]}
        self.assertEqual(codes, {"anchor-missing": "error"})  # symbol silenced

    def test_invalid_severity_value_rejected(self):
        write(self.root, ".claimcheck.toml",
              '[claimcheck.severity]\nanchor-missing = "loud"\n')
        write(self.root, "doc.md", "hi\n")
        code, _, err = run_cli("check")
        self.assertEqual(code, 2)
        self.assertIn("severity.anchor-missing", err)


class TestExplain(CliCase):
    def test_shows_resolution_method(self):
        write(self.root, "src/deep/nested/Widget.java", "class W {}\n")
        write(self.root, "doc.md", "See `Widget.java` and `doc.md`.\n")
        code, out, _ = run_cli("check", "--explain", "--no-symbols")
        self.assertEqual(code, 0)
        self.assertIn("Widget.java  →  ok: src/deep/nested/Widget.java (suffix-match)", out)
        self.assertIn("doc.md  →  ok: doc.md (repo-root)", out)

    def test_json_includes_explanations(self):
        write(self.root, "doc.md", "See `doc.md`.\n")
        code, out, _ = run_cli("check", "--explain", "--format", "json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["explanations"])


class TestStampAllStale(CliCase):
    def test_restamps_stale_only_docs(self):
        write(self.root, "app.py", "v1\n")
        write(self.root, "kb.md", "# KB\n\nSee `app.py`.\n")
        write(self.root, "broken.md", "# B\n\nSee `app.py` and `gone.py`.\n")
        self.commit_all()
        run_cli("stamp", "kb.md")
        run_cli("stamp", "broken.md")
        self.commit_all("stamps")
        write(self.root, "app.py", "v2\n")
        self.commit_all("drift")

        code, out, _ = run_cli("stamp", "--all-stale")
        self.assertEqual(code, 0)
        self.assertIn("re-verify kb.md", out)
        self.assertIn("stamped kb.md", out)
        self.assertIn("skipped broken.md", out)  # has path-missing too

        # kb.md is fresh again; broken.md still stale + broken.
        code, out, _ = run_cli("check")
        self.assertEqual(code, 1)
        self.assertNotIn("kb.md", out)
        self.assertIn("broken.md", out)

    def test_noop_when_nothing_stale(self):
        write(self.root, "kb.md", "# KB\n")
        self.commit_all()
        code, out, _ = run_cli("stamp", "--all-stale")
        self.assertEqual(code, 0)
        self.assertIn("no stale-stamped docs", out)

    def test_stamp_requires_paths_or_flag(self):
        code, _, err = run_cli("stamp")
        self.assertEqual(code, 2)
        self.assertIn("--all-stale", err)


if __name__ == "__main__":
    unittest.main()
