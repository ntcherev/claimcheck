import os
import subprocess
import tempfile
import unittest

from claimcheck.claims import extract
from claimcheck.markdown import parse
from claimcheck.verify import Verifier


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write(root, rel, content):
    full = os.path.join(root, rel)
    if os.path.dirname(rel):
        os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@t")
        git(self.root, "config", "user.name", "t")

    def tearDown(self):
        self._tmp.cleanup()

    def commit_all(self, msg="c"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)

    def head(self):
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root,
                           capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def check_doc(self, rel, symbol_severity="warn"):
        with open(os.path.join(self.root, rel)) as f:
            doc = parse(f.read(), rel)
        claims = extract(doc)
        v = Verifier(self.root, symbol_severity=symbol_severity)
        return v.verify({rel: claims})

    def codes(self, result):
        return [f.code for f in result.findings]


class TestPathClaims(RepoCase):
    def test_existing_and_missing(self):
        write(self.root, "src/app.py", "print('hi')\n")
        write(self.root, "doc.md", "Good `src/app.py`, bad `src/gone.py`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["path-missing"])
        self.assertIn("src/gone.py", res.findings[0].message)

    def test_doc_relative_resolution(self):
        write(self.root, "docs/kb/pipeline.md", "See `helpers.py`.\n")
        write(self.root, "docs/kb/helpers.py", "x = 1\n")
        res = self.check_doc("docs/kb/pipeline.md")
        self.assertEqual(res.findings, [])

    def test_ambiguous_extensionless_skipped(self):
        write(self.root, "doc.md",
              "It's a `key/value` store with `supportsCount/latestSupportDate`, "
              "see `docs/kb`.\n")
        os.makedirs(os.path.join(self.root, "docs/kb"))
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 2)  # docs/kb exists → checked

    def test_parent_relative_resolved_doc_relatively(self):
        write(self.root, "api/pom.xml", "<project/>\n")
        write(self.root, "api/docs/setup.md", "Copy `../pom.xml` first.\n")
        res = self.check_doc("api/docs/setup.md")
        self.assertEqual(res.findings, [])

    def test_escaping_parent_cite_skipped_not_reported(self):
        # `../credentials.properties` in a multi-repo workspace points at a
        # sibling checkout — unverifiable here, so skip; and an in-tree file
        # with the same basename must NOT pose as evidence (ADR-016).
        write(self.root, "credentials.properties", "k=v\n")
        write(self.root, "doc.md",
              "Copy `../credentials.properties` and `../shared/pom.xml`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 2)

    def test_escaping_line_ref_skipped(self):
        write(self.root, "doc.md", "See `../sibling/Main.java:40`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])
        self.assertEqual(res.claims_skipped, 1)

    def test_bare_filename_resolved_by_suffix(self):
        write(self.root, "src/main/java/deep/AgentManager.java", "class A {}\n")
        write(self.root, "doc.md", "See `AgentManager.java` and `deep/AgentManager.java`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])

    def test_ellipsis_path_resolved_by_suffix(self):
        write(self.root, "src/deep/tripwire/TripwireExecutor.java", "class T {}\n")
        write(self.root, "doc.md", "See `.../tripwire/TripwireExecutor.java`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])

    def test_line_ref(self):
        write(self.root, "src/app.py", "a\nb\nc\n")
        write(self.root, "doc.md", "Ok `src/app.py:2`, bad `src/app.py:99`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["line-out-of-range"])


class TestLinksAndAnchors(RepoCase):
    def test_broken_link(self):
        write(self.root, "doc.md", "[x](missing.md)\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["link-broken"])

    def test_anchor(self):
        write(self.root, "target.md", "# Real Heading\n")
        write(self.root, "doc.md", "[ok](target.md#real-heading) [bad](target.md#nope)\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["anchor-missing"])
        self.assertEqual(res.findings[0].severity, "warn")

    def test_same_doc_anchor(self):
        write(self.root, "doc.md", "# Intro\n\n[jump](#intro) [bad](#outro)\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["anchor-missing"])


class TestSymbols(RepoCase):
    def test_found_and_missing(self):
        write(self.root, "src/app.py", "def frobnicate_widgets():\n    pass\n")
        write(self.root, "doc.md",
              "Call `frobnicate_widgets()` then `vanished_thing.zap()`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["symbol-missing"])
        self.assertIn("vanished_thing.zap()", res.findings[0].message)

    def test_doc_mention_is_not_evidence(self):
        # The symbol appears ONLY in markdown — must still be flagged.
        write(self.root, "other.md", "mentions frobnicate_widgets here\n")
        write(self.root, "doc.md", "Call `frobnicate_widgets()`.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["symbol-missing"])

    def test_severity_off(self):
        write(self.root, "doc.md", "Call `vanished_thing.zap()`.\n")
        res = self.check_doc("doc.md", symbol_severity="off")
        self.assertEqual(res.findings, [])


class TestCommits(RepoCase):
    def test_missing_commit(self):
        write(self.root, "doc.md", "Verified at commit `deadbeefcafe1234`.\n")
        self.commit_all()
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["commit-missing"])

    def test_existing_commit_ok(self):
        write(self.root, "doc.md", "placeholder\n")
        self.commit_all()
        sha = self.head()
        write(self.root, "doc.md", f"Verified at commit {sha}.\n")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])

    def test_stamp_stale(self):
        write(self.root, "src/app.py", "v1\n")
        write(self.root, "doc.md", "stub\n")
        self.commit_all()
        sha = self.head()
        write(self.root, "doc.md",
              f"---\nverified-commit: {sha}\n---\n# KB\n\nSee `src/app.py`.\n")
        self.commit_all("stamp doc")
        write(self.root, "src/app.py", "v2 changed\n")
        self.commit_all("change cited file")
        res = self.check_doc("doc.md")
        self.assertEqual(self.codes(res), ["stamp-stale"])
        self.assertIn("src/app.py", res.findings[0].message)

    def test_stamp_ignores_doc_to_doc_changes(self):
        # Stamped docs citing other docs must not go stale when only those
        # docs change (e.g. the commit that adds everyone's stamps).
        write(self.root, "src/app.py", "v1\n")
        write(self.root, "other.md", "# Other\n")
        write(self.root, "doc.md", "stub\n")
        self.commit_all()
        sha = self.head()
        write(self.root, "doc.md",
              f"---\nverified-commit: {sha}\n---\nSee `other.md` and `src/app.py`.\n")
        write(self.root, "other.md", "# Other, edited after the stamp\n")
        self.commit_all("docs-only change")
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])

    def test_stamp_fresh(self):
        write(self.root, "src/app.py", "v1\n")
        self.commit_all()
        sha = self.head()
        write(self.root, "doc.md",
              f"---\nverified-commit: {sha}\n---\nSee `src/app.py`.\n")
        self.commit_all("stamp doc")  # cited file untouched since stamp
        res = self.check_doc("doc.md")
        self.assertEqual(res.findings, [])


class TestNonGit(unittest.TestCase):
    def test_commit_claims_skipped_outside_git(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "doc.md", "Verified at commit abcdef1234567.\nSee `app.py`.\n")
            write(root, "app.py", "x\n")
            with open(os.path.join(root, "doc.md")) as f:
                claims = extract(parse(f.read(), "doc.md"))
            res = Verifier(root).verify({"doc.md": claims})
            self.assertEqual([f.code for f in res.findings], [])
            self.assertEqual(res.claims_skipped, 1)


if __name__ == "__main__":
    unittest.main()
