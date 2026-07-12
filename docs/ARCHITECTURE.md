---
verified-commit: d4107d5e15f9d7c48b9f7f404491e794de69ea11
verified-date: 2026-07-12
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
  front-matter commits, `outside_repo: True` for home/absolute IMPORTs.
- `verify.Finding` — `(doc, line, severity, code, message)`; codes are the
  stable public vocabulary (`path-missing`, `line-out-of-range`,
  `link-broken`, `anchor-missing`, `symbol-missing`, `command-path-missing`,
  `import-missing`, `commit-missing`, `stamp-stale`, `gone-still-exists`).
  Severities are remappable per code via
  `[claimcheck.severity]`; `check --explain` records how each path claim
  resolved (repo-root / doc-relative / suffix-match).

## Resolution strategy (the heart of precision)

A path claim is resolved in order: repo-root relative → doc-dir relative →
suffix match against a lazily-built basename index of the whole tree (this is
what makes bare `AgentManager.java` and abbreviated `.../pkg/File.java`
citations work; cites escaping the root never reach the suffix pass, ADR-016).
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
- IMPORT claims (`@path` in CLAUDE.md / CLAUDE.local.md / AGENTS.md prose,
  ADR-013) are the exception to generosity: resolved only relative to the
  importing doc, exactly as the agent runtime loads them — no suffix rescue.
- Cites whose every in-repo reading escapes the root (`../sibling/pom.xml`
  in a multi-repo workspace) are skipped, not reported (ADR-016).
- `.claude/worktrees` (stale agent checkouts) is excluded from every walk —
  discovery, basename index, symbol corpus (ADR-014). `.claude` itself is
  walked so `.claude/skills/**/SKILL.md` docs are checked like any other.
- In a git repo, evidence is what git sees AND disk has: tracked +
  untracked-unignored (ADR-018). Gitignored paths are invisible both ways —
  never evidence, never reported missing. Doc discovery follows suit;
  explicitly named files override. Outside git: plain filesystem walks.
- Stamp staleness diffs the stamp against the working tree, not just
  `..HEAD` — uncommitted edits to cited files already count (ADR-019).
- A `claimcheck:gone` line inverts its claims — the doc asserts absence,
  resolving is the failure (ADR-020). `claimcheck:ignore <glob>` drops only
  matching targets on its line; bare, it still hides the line (ADR-021).

## Stamp staleness

For a doc with `verified-commit` front matter, the verifier collects the
doc's *resolved* cited paths, filters them to regular **code files**
(markdown and directories are excluded — ADR-009), then asks git for files
among them changed since the stamp — committed or not (ADR-019). Any change
→ `stamp-stale` warn naming the changed files. This is the loop that makes
doc freshness a checkable property.

## Testing

`python3 -m unittest discover -s tests` — 112 tests: unit (markdown parsing,
claim heuristics) and integration (real temp git repos exercising the full
check/stamp/stale cycle through `cli.main`). No test doubles for git; the
real binary runs against throwaway repos.
