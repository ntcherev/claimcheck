---
verified-commit: bde8afa877dd93a5f99e49264b19d84dacddeaad
verified-date: 2026-07-11
---
# Architecture

One-line pitch: extract *verifiable claims* from markdown, verify them against
the filesystem and git, report with CI-friendly severity.

## Pipeline

```text
discover -> parse -> extract claims -> verify -> report
```

Every stage is a separate module with a plain-data interface between stages:

| Module | Responsibility |
|---|---|
| `claimcheck/discover.py` | Resolve CLI path args to repo-relative `.md`/`.mdx` files, honoring excludes. |
| `claimcheck/markdown.py` | Hand-rolled scanner: front matter, headings, fenced blocks, inline code, links. Produces a `Document`. |
| `claimcheck/claims.py` | Heuristics turning `Document` pieces into typed `Claim`s (PATH, LINE_REF, LINK, ANCHOR, SYMBOL, COMMIT). |
| `claimcheck/verify.py` | `Verifier` checks claims against the tree + git; returns `Finding`s. All resolution generosity lives here. |
| `claimcheck/gitinfo.py` | Subprocess wrappers around git; everything degrades gracefully outside a git repo. |
| `claimcheck/stamp.py` | Writes `verified-commit` / `verified-date` front matter. |
| `claimcheck/report.py` | Text and JSON rendering of results. |
| `claimcheck/config.py` | `.claimcheck.toml` loading (stdlib `tomllib`) and repo-root detection. |
| `claimcheck/cli.py` | argparse wiring; subcommands `check`, `claims`, `stamp`. Exit codes 0/1/2. |

## Key data shapes

- `markdown.Document` — front matter dict, headings, inline code spans, links,
  fenced blocks, prose lines; all carry 1-based line numbers.
- `claims.Claim` — `(type, value, doc, line, extra)`. `extra` holds line
  ranges for LINE_REF, the search term for SYMBOL, `stamp: True` for
  front-matter commits.
- `verify.Finding` — `(doc, line, severity, code, message)`; codes are the
  stable public vocabulary (`path-missing`, `line-out-of-range`,
  `link-broken`, `anchor-missing`, `symbol-missing`, `command-path-missing`,
  `commit-missing`, `stamp-stale`). Severities are remappable per code via
  `[claimcheck.severity]`; `check --explain` records how each path claim
  resolved (repo-root / doc-relative / suffix-match).

## Resolution strategy (the heart of precision)

A path claim is resolved in order: repo-root relative → doc-dir relative →
suffix match against a lazily-built basename index of the whole tree (this is
what makes bare `AgentManager.java` and abbreviated `.../pkg/File.java`
citations work; leading `../` segments are stripped for the suffix pass).
Reporting rules that keep errors trustworthy:

- Missing PATH claims are only reported when the basename has a known file
  extension (`claims.KNOWN_EXTS`); extension-less tokens (`key/value`,
  `supportsCount/contradictsCount`) are counted as skipped.
- ALL_CAPS slash lists (`SIGNAL_PENDING/ROUTED`) are rejected at extraction.
- Fenced blocks are scanned only when shell-like (```bash et al., ADR-011):
  slash-containing tokens become command-path claims (`command-path-missing`,
  warn by default). Output/example fences (```text, ```python, bare) never are.
- SYMBOL search excludes markdown from its corpus — a doc must not vouch for
  its own claim — and is word-boundary based over text files ≤ 1 MB.

## Stamp staleness

For a doc with `verified-commit` front matter, the verifier collects the
doc's *resolved* cited paths, filters them to regular **code files**
(markdown and directories are excluded — ADR-009), then asks git for files
among them changed in `stamp..HEAD`. Any change → `stamp-stale` warn naming
the changed files. This is the loop that makes doc freshness a checkable
property.

## Testing

`python3 -m unittest discover -s tests` — 68 tests: unit (markdown parsing,
claim heuristics) and integration (real temp git repos exercising the full
check/stamp/stale cycle through `cli.main`). No test doubles for git; the
real binary runs against throwaway repos.
