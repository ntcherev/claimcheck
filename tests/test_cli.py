import io
import json
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


class TestCheck(CliCase):
    def test_clean_repo_exits_zero(self):
        write(self.root, "app.py", "x = 1\n")
        write(self.root, "README.md", "See `app.py`.\n")
        code, out, _ = run_cli("check")
        self.assertEqual(code, 0)
        self.assertIn("0 error(s)", out)

    def test_drift_exits_one(self):
        write(self.root, "README.md", "See `gone.py`... wait, `nope/missing.md`.\n")
        code, out, _ = run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("path-missing", out)

    def test_strict_promotes_warnings(self):
        write(self.root, "README.md", "[x](README.md#absent-heading)\n")
        code, _, _ = run_cli("check")
        self.assertEqual(code, 0)
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 1)

    def test_json_format(self):
        write(self.root, "README.md", "See `gone.py`.\n")
        code, out, _ = run_cli("check", "--format", "json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["summary"]["errors"], 1)
        self.assertEqual(data["findings"][0]["code"], "path-missing")

    def test_no_symbols_flag(self):
        write(self.root, "README.md", "Call `vanished_thing.zap()`.\n")
        code, out, _ = run_cli("check", "--strict")
        self.assertEqual(code, 1)
        code, _, _ = run_cli("check", "--strict", "--no-symbols")
        self.assertEqual(code, 0)

    def test_config_ignore(self):
        write(self.root, ".claimcheck.toml",
              '[claimcheck]\nignore = ["legacy/*"]\nsymbols = "off"\n')
        write(self.root, "README.md", "Old `legacy/gone.py` is fine.\n")
        code, _, _ = run_cli("check")
        self.assertEqual(code, 0)

    def test_config_exclude_docs(self):
        write(self.root, ".claimcheck.toml", '[claimcheck]\nexclude = ["archive/**"]\n')
        write(self.root, "archive/old.md", "Totally `broken/path.py`.\n")
        write(self.root, "README.md", "hello\n")
        code, _, _ = run_cli("check")
        self.assertEqual(code, 0)

    def test_empty_dir_exits_two(self):
        code, _, err = run_cli("check")
        self.assertEqual(code, 2)
        self.assertIn("no markdown", err)


class TestStamp(CliCase):
    def test_stamp_then_check_stale_cycle(self):
        write(self.root, "app.py", "v1\n")
        write(self.root, "kb.md", "# KB\n\nSee `app.py`.\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c1")

        code, out, _ = run_cli("stamp", "kb.md")
        self.assertEqual(code, 0)
        self.assertIn("stamped kb.md", out)
        with open("kb.md") as f:
            self.assertIn("verified-commit:", f.read())

        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "stamp")
        code, _, _ = run_cli("check", "--strict")
        self.assertEqual(code, 0)

        write(self.root, "app.py", "v2\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "drift")
        code, out, _ = run_cli("check", "--strict")
        self.assertEqual(code, 1)
        self.assertIn("stamp-stale", out)

    def test_restamp_replaces_old_stamp(self):
        write(self.root, "kb.md", "---\nowner: me\nverified-commit: 0000000\n---\n# KB\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c1")
        code, _, _ = run_cli("stamp", "kb.md")
        self.assertEqual(code, 0)
        with open("kb.md") as f:
            content = f.read()
        self.assertIn("owner: me", content)
        self.assertNotIn("0000000", content)
        self.assertEqual(content.count("verified-commit:"), 1)


class TestClaimsCommand(CliCase):
    def test_lists_claims(self):
        write(self.root, "README.md", "See `app.py` and call `Foo.bar()`.\n")
        code, out, _ = run_cli("claims")
        self.assertEqual(code, 0)
        self.assertIn("path  app.py", out)
        self.assertIn("symbol  Foo.bar()", out)


if __name__ == "__main__":
    unittest.main()
