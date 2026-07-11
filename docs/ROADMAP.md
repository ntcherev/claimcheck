---
verified-commit: 3566947c92967e1a56f3415ccc82bcf9ea6ab9e8
verified-date: 2026-07-11
---
# Roadmap

Ordered by conviction, not date. Each item should land with tests and an ADR
if it changes behavior.

## v0.2 — earn daily-driver status

- **`check --since <ref>`** — only check docs touched in a git range; makes
  pre-commit/PR usage instant on big repos.
- **Command claims** — verify fenced ```bash blocks' script paths and
  make/npm/just targets exist (extraction is already fence-aware; this is the
  reason fences are collected).
- **Suffix-resolution report mode** — `--explain` prints where each claim
  resolved, so users can see why something passed.
- **Per-code severity config** — `[claimcheck.severity] anchor-missing = "error"`.
- **Stamp ergonomics** — `stamp --all-stale` restamps every doc whose only
  finding is `stamp-stale` after a human pass; print a re-verify checklist
  (the changed cited files) per doc.

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
