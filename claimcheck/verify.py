"""Verify extracted claims against the repository state."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import gitinfo
from .claims import KNOWN_EXTS, Claim, ClaimType, resolve_candidates
from .markdown import anchor_slug, parse

# Directories never scanned for the symbol-search corpus.
EXCLUDE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "target",
    "dist", "build", "out", ".idea", ".vscode", ".gradle", ".mvn", ".next",
    ".cache", "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
_MAX_SYMBOL_FILE_BYTES = 1_000_000


def _has_known_ext(value: str) -> bool:
    base = value.rstrip("/").rpartition("/")[2]
    _, dot, ext = base.rpartition(".")
    return bool(dot) and f".{ext.lower()}" in KNOWN_EXTS


@dataclass
class Finding:
    doc: str
    line: int
    severity: str  # "error" | "warn"
    code: str
    message: str


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    claims_checked: int = 0
    claims_skipped: int = 0


class Verifier:
    def __init__(self, root: str, symbol_severity: str = "warn"):
        self.root = os.path.abspath(root)
        self.symbol_severity = symbol_severity  # "off" | "warn" | "error"
        self.git = gitinfo.is_git_repo(self.root)
        self._heading_cache: dict[str, set[str]] = {}
        self._basename_index: dict[str, list[str]] | None = None

    # -- helpers -------------------------------------------------------

    def _exists(self, rel: str) -> str | None:
        """Return the first existing candidate repo-relative path, if any."""
        full = os.path.join(self.root, rel)
        return rel if os.path.exists(full) else None

    def _resolve(self, claim: Claim) -> str | None:
        for cand in resolve_candidates(claim.value, claim.doc):
            if self._exists(cand):
                return cand
        # Docs cite files by bare name (`AgentManager.java`) or partial path
        # (`agents/screener.yml`, `.../tripwire/TripwireExecutor.java`).
        # Fall back to "exists anywhere in the tree" by suffix match.
        return self._resolve_by_suffix(claim.value)

    def _resolve_by_suffix(self, value: str) -> str | None:
        if self._basename_index is None:
            index: dict[str, list[str]] = {}
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
                rel_dir = os.path.relpath(dirpath, self.root).replace(os.sep, "/")
                for name in filenames + dirnames:
                    rel = name if rel_dir == "." else f"{rel_dir}/{name}"
                    index.setdefault(name, []).append(rel)
            self._basename_index = index
        value = value.rstrip("/")
        while value.startswith("../"):  # `../pom.xml` cited relative to elsewhere
            value = value[3:]
        base = value.rpartition("/")[2]
        matches = [rel for rel in self._basename_index.get(base, ())
                   if rel == value or rel.endswith("/" + value)]
        return sorted(matches)[0] if matches else None

    def _headings_of(self, rel: str) -> set[str] | None:
        if rel in self._heading_cache:
            return self._heading_cache[rel]
        full = os.path.join(self.root, rel)
        if not os.path.isfile(full):
            return None
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                doc = parse(f.read(), rel)
        except OSError:
            return None
        slugs = {anchor_slug(h.text) for h in doc.headings}
        self._heading_cache[rel] = slugs
        return slugs

    def _iter_corpus_files(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".git"))
            for fn in sorted(filenames):
                # Markdown is excluded from the corpus: a doc mentioning a
                # symbol must not count as evidence the symbol exists in code
                # (the claiming doc itself would always satisfy its own claim).
                if fn.lower().endswith((".md", ".mdx", ".markdown")):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(full) > _MAX_SYMBOL_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield full

    def _search_symbols(self, terms: set[str]) -> set[str]:
        """Return the subset of terms found (word-bounded) anywhere in the repo."""
        pending = {t: re.compile(rf"\b{re.escape(t)}\b") for t in terms}
        found: set[str] = set()
        for full in self._iter_corpus_files():
            if not pending:
                break
            try:
                with open(full, "rb") as f:
                    raw = f.read()
                if b"\x00" in raw[:8192]:
                    continue  # binary
                text = raw.decode("utf-8", errors="replace")
            except OSError:
                continue
            for term in list(pending):
                if pending[term].search(text):
                    found.add(term)
                    del pending[term]
        return found

    # -- main entry ----------------------------------------------------

    def verify(self, claims_by_doc: dict[str, list[Claim]]) -> Result:
        res = Result()
        symbol_claims: list[Claim] = []

        for doc_path, claims in claims_by_doc.items():
            # Paths this doc verifiably cites — used for stamp staleness.
            cited_paths: list[str] = []
            stamp_claims: list[Claim] = []

            for claim in claims:
                if claim.type in (ClaimType.PATH, ClaimType.LINK):
                    res.claims_checked += 1
                    resolved = self._resolve(claim)
                    if resolved:
                        cited_paths.append(resolved)
                    elif claim.type == ClaimType.PATH and not _has_known_ext(claim.value):
                        # `key/value`, `supportsCount/contradictsCount`, bare dir
                        # names — too ambiguous to report as broken when missing.
                        res.claims_checked -= 1
                        res.claims_skipped += 1
                    else:
                        code = "path-missing" if claim.type == ClaimType.PATH else "link-broken"
                        res.findings.append(Finding(
                            doc_path, claim.line, "error", code,
                            f"`{claim.value}` does not exist (checked repo root and doc dir)",
                        ))

                elif claim.type == ClaimType.LINE_REF:
                    res.claims_checked += 1
                    resolved = self._resolve(claim)
                    if not resolved:
                        res.findings.append(Finding(
                            doc_path, claim.line, "error", "path-missing",
                            f"`{claim.value}` does not exist (checked repo root and doc dir)",
                        ))
                        continue
                    cited_paths.append(resolved)
                    try:
                        with open(os.path.join(self.root, resolved), encoding="utf-8",
                                  errors="replace") as f:
                            n_lines = sum(1 for _ in f)
                    except OSError:
                        continue
                    end = claim.extra["line_end"]
                    if end > n_lines:
                        res.findings.append(Finding(
                            doc_path, claim.line, "error", "line-out-of-range",
                            f"`{claim.value}` cites line {end} but the file has {n_lines} lines",
                        ))

                elif claim.type == ClaimType.ANCHOR:
                    res.claims_checked += 1
                    target = claim.extra.get("in_target") or claim.extra.get("in_doc") or doc_path
                    for cand in resolve_candidates(target, doc_path):
                        slugs = self._headings_of(cand)
                        if slugs is not None:
                            if claim.value.lower() not in slugs:
                                res.findings.append(Finding(
                                    doc_path, claim.line, "warn", "anchor-missing",
                                    f"anchor `#{claim.value}` not found in `{cand}`",
                                ))
                            break

                elif claim.type == ClaimType.SYMBOL:
                    if self.symbol_severity != "off":
                        symbol_claims.append(claim)

                elif claim.type == ClaimType.COMMIT:
                    if not self.git:
                        res.claims_skipped += 1
                        continue
                    res.claims_checked += 1
                    if not gitinfo.commit_exists(self.root, claim.value):
                        res.findings.append(Finding(
                            doc_path, claim.line, "error", "commit-missing",
                            f"cited commit `{claim.value}` is not in this repository",
                        ))
                    elif claim.extra.get("stamp"):
                        stamp_claims.append(claim)

            for stamp in stamp_claims:
                # Staleness tracks cited *code files* only. Markdown is excluded
                # (docs carry their own stamps — otherwise the stamp commit
                # itself marks every cross-referencing doc stale) and so are
                # directories (a dir pathspec would match its whole subtree).
                code_paths = sorted({
                    p for p in cited_paths
                    if not p.lower().endswith((".md", ".mdx", ".markdown"))
                    and os.path.isfile(os.path.join(self.root, p))
                })
                changed = gitinfo.changed_files_since(self.root, stamp.value, code_paths)
                if changed:
                    behind = gitinfo.commits_since(self.root, stamp.value)
                    sample = ", ".join(changed[:3]) + ("…" if len(changed) > 3 else "")
                    res.findings.append(Finding(
                        doc_path, stamp.line, "warn", "stamp-stale",
                        f"verified at `{stamp.value[:12]}` ({behind} commits ago) but "
                        f"{len(changed)} of {len(code_paths)} cited code files changed since: {sample}",
                    ))

        if symbol_claims:
            terms = {c.extra["term"] for c in symbol_claims}
            found = self._search_symbols(terms)
            for claim in symbol_claims:
                res.claims_checked += 1
                if claim.extra["term"] not in found:
                    res.findings.append(Finding(
                        claim.doc, claim.line, self.symbol_severity, "symbol-missing",
                        f"symbol `{claim.value}` not found anywhere in the repo",
                    ))

        res.findings.sort(key=lambda f: (f.doc, f.line, f.code))
        return res
