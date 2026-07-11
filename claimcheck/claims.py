"""Extract verifiable claims from a parsed markdown document.

Claim types:
  PATH      inline code that looks like a repo path            `api/service.py`
  LINE_REF  a path with a line (or range) suffix               `api/service.py:42`
  LINK      relative markdown link target                      [x](../docs/kb/foo.md)
  ANCHOR    heading anchor in a relative link or same doc      [x](foo.md#setup)
  SYMBOL    inline code that looks like a code identifier      `Planner.run()`
  COMMIT    a git sha cited in prose or front matter           verified at commit ab12cd3
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from enum import Enum

from .markdown import Document


class ClaimType(Enum):
    PATH = "path"
    LINE_REF = "line-ref"
    LINK = "link"
    ANCHOR = "anchor"
    SYMBOL = "symbol"
    COMMIT = "commit"


@dataclass
class Claim:
    type: ClaimType
    value: str
    doc: str
    line: int
    extra: dict = field(default_factory=dict)


# Extensions that make a slash-less token count as a path (`setup.py`).
KNOWN_EXTS = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".java", ".kt",
    ".go", ".rs", ".rb", ".php", ".c", ".h", ".cpp", ".hpp", ".cs", ".swift",
    ".md", ".mdx", ".rst", ".txt", ".toml", ".yml", ".yaml", ".json", ".jsonl",
    ".xml", ".html", ".css", ".scss", ".sql", ".sh", ".bash", ".zsh", ".fish",
    ".ps1", ".bat", ".dockerfile", ".proto", ".graphql", ".gql", ".tf",
    ".gradle", ".properties", ".cfg", ".ini", ".conf", ".env", ".lock",
    ".makefile", ".cmake", ".ipynb", ".vue", ".svelte",
}

_PATH_CHARS_RE = re.compile(r"^[A-Za-z0-9_.@~/\\-]+$")
_MIME_RE = re.compile(r"^(application|text|image|audio|video|font|multipart|message)/[a-z0-9.+-]+$")
_LINE_REF_RE = re.compile(r"^(.*?):(\d+)(?:-(\d+))?$")
_SYMBOL_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:[.#][A-Za-z_][A-Za-z0-9_]*)*(?:\(\))?$"
)
_COMMIT_RE = re.compile(r"\b(?:commit|sha|rev(?:ision)?)\s+`?([0-9a-f]{7,40})\b", re.IGNORECASE)
_FM_COMMIT_KEYS = ("verified-commit", "verified_commit", "verified-at-commit")

# Tokens with shell/glob/placeholder characters are not concrete claims.
_NON_CONCRETE_RE = re.compile(r"[*?{}<>$|=\s]")


_ALL_CAPS_SEG_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def looks_like_path(token: str) -> bool:
    if not token or _NON_CONCRETE_RE.search(token) or not _PATH_CHARS_RE.match(token):
        return False
    if _MIME_RE.match(token):
        return False
    if token.startswith(("http://", "https://", "~", "@")):
        return False
    if "/" in token:
        # `SIGNAL_PENDING/ROUTED/COVERAGE_ONLY` is an enum list, not a path.
        if all(_ALL_CAPS_SEG_RE.match(seg) for seg in token.split("/") if seg):
            return False
        return True
    root, dot, ext = token.rpartition(".")
    return bool(dot) and bool(root) and f".{ext.lower()}" in KNOWN_EXTS


def looks_like_symbol(token: str) -> bool:
    if not _SYMBOL_RE.match(token):
        return False
    # Require a signal that it's an identifier reference, not a plain word:
    # a call suffix, a Class#method / dotted path, or CamelCase-with-lowercase.
    if token.endswith("()") or "#" in token or "." in token:
        return True
    return False


def symbol_search_term(token: str) -> str:
    """The component we actually grep for: the last dotted/# part, sans ()."""
    term = token.removesuffix("()")
    for sep in (".", "#"):
        term = term.rpartition(sep)[2]
    return term


def extract(doc: Document, symbols_enabled: bool = True) -> list[Claim]:
    claims: list[Claim] = []

    for code in doc.inline_code:
        token = code.text.strip().removeprefix("./")
        # Docs abbreviate deep paths: `.../tripwire/TripwireExecutor.java`,
        # `shared/.../RoleType.java`. Keep what follows the last ellipsis;
        # suffix resolution in the verifier finds the file.
        for ellipsis in (".../", "…/"):
            if ellipsis in token:
                token = token.split(ellipsis)[-1]
        if not token:
            continue
        m = _LINE_REF_RE.match(token)
        if m and looks_like_path(m.group(1).removeprefix("./")):
            claims.append(Claim(
                ClaimType.LINE_REF, m.group(1).removeprefix("./"), doc.path, code.line,
                extra={"line_start": int(m.group(2)),
                       "line_end": int(m.group(3) or m.group(2))},
            ))
        elif looks_like_path(token):
            if token.startswith("/"):
                continue  # absolute paths point outside the repo; skip
            claims.append(Claim(ClaimType.PATH, token.rstrip("/"), doc.path, code.line))
        elif symbols_enabled and looks_like_symbol(token):
            term = symbol_search_term(token)
            if len(term) >= 3:
                claims.append(Claim(ClaimType.SYMBOL, token, doc.path, code.line,
                                    extra={"term": term}))

    for link in doc.links:
        target = link.target
        if target.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
            continue
        if target.startswith("#"):
            claims.append(Claim(ClaimType.ANCHOR, target[1:], doc.path, link.line,
                                extra={"in_doc": doc.path}))
            continue
        path_part, _, anchor = target.partition("#")
        path_part = path_part.removeprefix("./")
        if path_part:
            claims.append(Claim(ClaimType.LINK, path_part, doc.path, link.line))
        if anchor:
            claims.append(Claim(ClaimType.ANCHOR, anchor, doc.path, link.line,
                                extra={"in_target": path_part or doc.path}))

    for lineno, line in doc.prose_lines:
        for m in _COMMIT_RE.finditer(line):
            claims.append(Claim(ClaimType.COMMIT, m.group(1), doc.path, lineno))

    for key in _FM_COMMIT_KEYS:
        if key in doc.front_matter:
            claims.append(Claim(
                ClaimType.COMMIT, doc.front_matter[key], doc.path,
                doc.front_matter_span[0] if doc.front_matter_span else 1,
                extra={"stamp": True},
            ))
            break

    return claims


def resolve_candidates(claim_value: str, doc_path: str) -> list[str]:
    """Repo-relative candidate locations for a path-ish claim: as written
    from the repo root, and relative to the doc's directory."""
    root_rel = posixpath.normpath(claim_value)
    doc_dir = posixpath.dirname(doc_path)
    doc_rel = posixpath.normpath(posixpath.join(doc_dir, claim_value)) if doc_dir else root_rel
    out = [root_rel]
    if doc_rel != root_rel:
        out.append(doc_rel)
    return [c for c in out if not c.startswith("..")] or [root_rel]
