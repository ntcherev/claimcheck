"""Minimal markdown scanner for the constructs claimcheck cares about.

Hand-rolled on purpose (no CommonMark dependency). Supported subset:
front matter (--- blocks of `key: value` lines), ATX headings, fenced
code blocks (``` / ~~~), inline code spans, and inline links/images.
Content inside fenced blocks is collected but not scanned for inline
constructs — fences usually hold example code, not claims about this
repo. A line containing `claimcheck:ignore` is skipped entirely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*(.*)$")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(\s*<?([^)<>\s]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
_FRONT_MATTER_KV_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")

IGNORE_MARKER = "claimcheck:ignore"
GONE_MARKER = "claimcheck:gone"


@dataclass
class InlineCode:
    text: str
    line: int


@dataclass
class Link:
    text: str
    target: str
    line: int


@dataclass
class Heading:
    text: str
    level: int
    line: int


@dataclass
class FencedBlock:
    info: str
    lines: list[str]
    start_line: int


@dataclass
class Document:
    path: str
    front_matter: dict[str, str] = field(default_factory=dict)
    front_matter_span: tuple[int, int] | None = None  # (first, last) 1-based lines incl. fences
    inline_code: list[InlineCode] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    headings: list[Heading] = field(default_factory=list)
    fences: list[FencedBlock] = field(default_factory=list)
    prose_lines: list[tuple[int, str]] = field(default_factory=list)  # lines outside fences/fm
    gone_lines: set[int] = field(default_factory=set)  # claimcheck:gone — absence claims
    ignore_patterns: dict[int, list[str]] = field(default_factory=dict)  # targeted ignores


def parse(text: str, path: str = "<memory>") -> Document:
    doc = Document(path=path)
    lines = text.splitlines()
    i = 0

    # Front matter: a leading `---` line closed by another `---` line.
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            stripped = lines[j].strip()
            if stripped in ("---", "..."):
                for raw in lines[1:j]:
                    m = _FRONT_MATTER_KV_RE.match(raw.strip())
                    if m:
                        doc.front_matter[m.group(1)] = m.group(2).strip().strip("\"'")
                doc.front_matter_span = (1, j + 1)
                i = j + 1
                break

    fence: FencedBlock | None = None
    fence_marker = ""
    while i < len(lines):
        line = lines[i]
        lineno = i + 1
        i += 1

        if fence is not None:
            m = _FENCE_RE.match(line)
            if m and m.group(2)[0] == fence_marker[0] and len(m.group(2)) >= len(fence_marker) and not m.group(3):
                doc.fences.append(fence)
                fence = None
            else:
                fence.lines.append(line)
            continue

        m = _FENCE_RE.match(line)
        if m:
            fence_marker = m.group(2)
            fence = FencedBlock(info=m.group(3).strip(), lines=[], start_line=lineno)
            continue

        if IGNORE_MARKER in line:
            # Bare marker: the whole line is invisible. With arguments
            # (`claimcheck:ignore <glob>…`) only matching claim targets on
            # this line are dropped — dense KB lines keep their good cites.
            rest = line[line.find(IGNORE_MARKER) + len(IGNORE_MARKER):]
            patterns = rest.replace("-->", " ").split()
            if not patterns:
                continue
            doc.ignore_patterns[lineno] = patterns
        if GONE_MARKER in line:
            # Absence claims: paths/symbols on this line must NOT exist.
            doc.gone_lines.add(lineno)

        doc.prose_lines.append((lineno, line))

        h = _HEADING_RE.match(line)
        if h:
            doc.headings.append(Heading(text=h.group(2), level=len(h.group(1)), line=lineno))

        # Mask inline code before extracting links so `[x](y)` inside code
        # spans is not treated as a link, and record the spans themselves.
        def _record_code(m: re.Match) -> str:
            doc.inline_code.append(InlineCode(text=m.group(2).strip(), line=lineno))
            return " " * len(m.group(0))

        masked = _INLINE_CODE_RE.sub(_record_code, line)
        for lm in _LINK_RE.finditer(masked):
            doc.links.append(Link(text=lm.group(1), target=lm.group(2), line=lineno))

    if fence is not None:  # unterminated fence
        doc.fences.append(fence)
    return doc


def mask_inline_code(line: str) -> str:
    """The line with inline code spans blanked out. Prose-token scans
    (memory imports) must not see code-span content — `` `@x` `` is the
    documented way to write an @ token that is not an import."""
    return _INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)


def anchor_slug(heading_text: str) -> str:
    """GitHub-style anchor slug (approximate: no duplicate-suffix handling)."""
    text = heading_text.strip().lower()
    # Drop inline-code backticks and link syntax, keep the visible text.
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")
