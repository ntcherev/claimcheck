---
verified-commit: bde8afa877dd93a5f99e49264b19d84dacddeaad
verified-date: 2026-07-11
---
# Roadmap

Ordered by conviction, not date. Each item should land with tests and an ADR
if it changes behavior.

## Shipped · v0.2 (2026-07-11) — daily-driver ergonomics

`check --since <ref>` (scoped fast runs incl. uncommitted/untracked docs,
ADR-012) · command claims in shell fences (`command-path-missing`, ADR-011) ·
`check --explain` resolution tracing · `[claimcheck.severity]` per-code
overrides · `stamp --all-stale` with re-verify checklist.

## v0.2.x — leftovers

- **Make/npm/just target claims** — `make deploy` in a fence verified against
  Makefile/package.json targets. Deferred from v0.2 (ADR-011): separate claim
  type, needs manifest parsing.

## v0.3 — ecosystem fit

- **GitHub Action + pre-commit hook** — thin wrappers; JSON output already
  exists. Publish to PyPI first (name checked free as of 2026-07-11).
- **Agent-skill awareness** — understand `SKILL.md`/skills directories and
  `@import` lines in CLAUDE.md (an import that points nowhere is a
  high-signal error).
- **SARIF output** — GitHub code-scanning annotations on PRs.

## Explicitly rejected (see DECISIONS.md)

- LLM-judged semantic drift inside `check` (ADR-003). If ever, a separate
  opt-in `claimcheck review` command.
- URL link checking — crowded space (lychee et al.), zero differentiation.
- Full CommonMark parsing (ADR-004) without field evidence it's needed.

## Open questions for next session

- Should suffix resolution require uniqueness (flag ambiguous basenames like
  `index.ts` matching 40 files)? Currently first-match-wins satisfies
  existence, which can hide a deletion when a same-named file exists elsewhere.
- Stamp granularity: per-doc today; per-section stamps for long KB files?
- Windows: path handling is POSIX-assumed; untested.
