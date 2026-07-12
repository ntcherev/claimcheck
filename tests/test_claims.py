import unittest

from claimcheck.claims import (
    ClaimType, extract, looks_like_path, looks_like_symbol,
    resolve_candidates, symbol_search_term,
)
from claimcheck.markdown import parse


class TestPathHeuristic(unittest.TestCase):
    def test_positive(self):
        for token in ("src/main.py", "docs/kb", "setup.py", "a/b/c.ts",
                      ".claimcheck.toml", "Makefile.toml", "deep/nested/dir/file.java"):
            self.assertTrue(looks_like_path(token), token)

    def test_negative(self):
        for token in ("application/json", "text/html", "hello", "e.g", "v1.2.3",
                      "http://x.com/a", "~", "~/notes", "a b.py", "glob/*.py",
                      "{placeholder}/x.py", "<path>/y.py", "$HOME/z.py", "",
                      "SIGNAL_PENDING/ROUTED/COVERAGE_ONLY/STREAM_PROPOSED",
                      "-implementation-contract.md", "-suffix/part.py"):
            self.assertFalse(looks_like_path(token), token)

    def test_leading_hyphen_is_suffix_shorthand(self):
        # Docs write `spec.md` + `-implementation-contract.md` to mean
        # "same prefix"; the fragment must not become a path claim.
        claims = extract(parse("See `a-spec.md` + `-impl-contract.md`.\n", "x.md"))
        self.assertEqual([(c.type, c.value) for c in claims],
                         [(ClaimType.PATH, "a-spec.md")])

    def test_ellipsis_prefix_stripped(self):
        claims = extract(parse("See `.../tripwire/TripwireExecutor.java`.\n", "x.md"))
        self.assertEqual([(c.type, c.value) for c in claims],
                         [(ClaimType.PATH, "tripwire/TripwireExecutor.java")])

    def test_mid_path_ellipsis(self):
        claims = extract(parse("See `shared/.../RoleType.java`.\n", "x.md"))
        self.assertEqual([(c.type, c.value) for c in claims],
                         [(ClaimType.PATH, "RoleType.java")])


class TestSymbolHeuristic(unittest.TestCase):
    def test_positive(self):
        for token in ("Planner.run()", "Foo#bar", "handleClick()",
                      "com.example.api.Node", "os.walk"):
            self.assertTrue(looks_like_symbol(token), token)

    def test_negative(self):
        for token in ("hello", "CamelCase", "--strict", "a.b.", "x()"[:2] + ")("):
            self.assertFalse(looks_like_symbol(token), token)

    def test_search_term(self):
        self.assertEqual(symbol_search_term("Planner.run()"), "run")
        self.assertEqual(symbol_search_term("Foo#bar"), "bar")
        self.assertEqual(symbol_search_term("handleClick()"), "handleClick")


class TestExtract(unittest.TestCase):
    def _claims(self, text):
        return extract(parse(text, "docs/x.md"))

    def test_path_and_line_ref(self):
        claims = self._claims("See `src/app.py` and `src/app.py:42` and `src/app.py:10-20`.\n")
        types = [(c.type, c.value) for c in claims]
        self.assertIn((ClaimType.PATH, "src/app.py"), types)
        line_refs = [c for c in claims if c.type == ClaimType.LINE_REF]
        self.assertEqual(len(line_refs), 2)
        self.assertEqual(line_refs[1].extra, {"line_start": 10, "line_end": 20})

    def test_absolute_paths_skipped(self):
        claims = self._claims("Run `/usr/bin/python3` here.\n")
        self.assertEqual(claims, [])

    def test_link_and_anchor(self):
        claims = self._claims("[a](../README.md#setup) [b](#local) [c](https://x.com/y.md)\n")
        kinds = [(c.type, c.value) for c in claims]
        self.assertIn((ClaimType.LINK, "../README.md"), kinds)
        self.assertIn((ClaimType.ANCHOR, "setup"), kinds)
        self.assertIn((ClaimType.ANCHOR, "local"), kinds)
        self.assertEqual(len([c for c in claims if c.type == ClaimType.LINK]), 1)

    def test_commit_in_prose(self):
        claims = self._claims("Verified against code at commit `62b3d3f6` earlier.\n")
        self.assertEqual([(c.type, c.value) for c in claims],
                         [(ClaimType.COMMIT, "62b3d3f6")])

    def test_commit_stamp_front_matter(self):
        claims = self._claims("---\nverified-commit: abcdef1234567\n---\n# T\n")
        stamp = [c for c in claims if c.type == ClaimType.COMMIT]
        self.assertEqual(len(stamp), 1)
        self.assertTrue(stamp[0].extra.get("stamp"))

    def test_symbols_can_be_disabled(self):
        text = "Call `Planner.execute()` now.\n"
        with_syms = extract(parse(text, "x.md"), symbols_enabled=True)
        without = extract(parse(text, "x.md"), symbols_enabled=False)
        self.assertEqual([c.type for c in with_syms], [ClaimType.SYMBOL])
        self.assertEqual(without, [])


class TestResolveCandidates(unittest.TestCase):
    def test_root_and_doc_relative(self):
        self.assertEqual(resolve_candidates("src/a.py", "docs/x.md"),
                         ["src/a.py", "docs/src/a.py"])
        self.assertEqual(resolve_candidates("../README.md", "docs/x.md"),
                         ["README.md"])

    def test_root_doc(self):
        self.assertEqual(resolve_candidates("src/a.py", "x.md"), ["src/a.py"])


if __name__ == "__main__":
    unittest.main()
