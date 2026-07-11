import unittest

from claimcheck.markdown import anchor_slug, parse

SAMPLE = """\
---
verified-commit: abc1234def
verified-date: 2026-07-11
---
# Title

Some prose with `inline/code.py` and ``double `tick` span``.

See [the guide](docs/guide.md#setup) and ![img](assets/x.png).

```python
ignored_link = "[x](fenced/ignored.md)"
`fenced/ignored.py`
```

## Second Heading ##

`skipped/by/marker.py` <!-- claimcheck:ignore -->
"""


class TestParse(unittest.TestCase):
    def setUp(self):
        self.doc = parse(SAMPLE, "sample.md")

    def test_front_matter(self):
        self.assertEqual(self.doc.front_matter["verified-commit"], "abc1234def")
        self.assertEqual(self.doc.front_matter_span, (1, 4))

    def test_headings(self):
        self.assertEqual([(h.text, h.level) for h in self.doc.headings],
                         [("Title", 1), ("Second Heading", 2)])

    def test_inline_code(self):
        texts = [c.text for c in self.doc.inline_code]
        self.assertIn("inline/code.py", texts)
        self.assertIn("double `tick` span", texts)
        self.assertNotIn("fenced/ignored.py", texts)
        self.assertNotIn("skipped/by/marker.py", texts)

    def test_links(self):
        targets = [l.target for l in self.doc.links]
        self.assertIn("docs/guide.md#setup", targets)
        self.assertIn("assets/x.png", targets)
        self.assertNotIn("fenced/ignored.md", targets)

    def test_fences_collected(self):
        self.assertEqual(len(self.doc.fences), 1)
        self.assertEqual(self.doc.fences[0].info, "python")
        self.assertEqual(len(self.doc.fences[0].lines), 2)

    def test_line_numbers(self):
        title = next(h for h in self.doc.headings if h.text == "Title")
        self.assertEqual(title.line, 5)


class TestNoFrontMatter(unittest.TestCase):
    def test_plain_doc(self):
        doc = parse("# Hi\n\ntext `a/b.py`\n", "x.md")
        self.assertIsNone(doc.front_matter_span)
        self.assertEqual(doc.front_matter, {})
        self.assertEqual(len(doc.inline_code), 1)

    def test_unterminated_fence(self):
        doc = parse("```\ncode\nmore\n", "x.md")
        self.assertEqual(len(doc.fences), 1)
        self.assertEqual(doc.fences[0].lines, ["code", "more"])


class TestAnchorSlug(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(anchor_slug("Hello World!"), "hello-world")
        self.assertEqual(anchor_slug("Setup & Config"), "setup--config")
        self.assertEqual(anchor_slug("`code` stuff"), "code-stuff")
        self.assertEqual(anchor_slug("With [link](x.md) text"), "with-link-text")


if __name__ == "__main__":
    unittest.main()
