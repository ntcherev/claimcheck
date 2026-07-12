---
verified-commit: bde8afa877dd93a5f99e49264b19d84dacddeaad
verified-date: 2026-07-11
---
# Roadmap

Ordered by conviction, not date. Each item should land with tests and an ADR
if it changes behavior.

## Shipped · v0.3 (2026-07-12) — agent-file awareness

`@path` memory-import claims in CLAUDE.md/CLAUDE.local.md/AGENTS.md, verified
with runtime resolution semantics (`import-missing`, error, ADR-013) ·
`.claude/skills/**/SKILL.md` coverage locked by tests · `.claude/worktrees`
never counts as evidence (ADR-014) · leading-hyphen suffix shorthand rejected
(ADR-015) · cites escaping the repo root skipped, not reported (ADR-016).
All four corpus-validated; every surviving corpus error spot-checked genuine.

## Shipped · v0.2 (2026-07-11) — daily-driver ergonomics

`check --since <ref>` (scoped fast runs incl. uncommitted/untracked docs,
ADR-012) · command claims in shell fences (`command-path-missing`, ADR-011) ·
`check --explain` resolution tracing · `[claimcheck.severity]` per-code
overrides · `stamp --all-stale` with re-verify checklist.

## v0.4 — ecosystem fit

- **Publish to PyPI** — name checked free as of 2026-07-11; needs the owner's
  credentials. Prerequisite for the wrappers below.
- **GitHub Action + pre-commit hook** — thin wrappers; JSON output already
  exists.
- **SARIF output** — GitHub code-scanning annotations on PRs.
- **Make/npm/just target claims** — `make deploy` in a fence verified against
  Makefile/package.json targets. Deferred from v0.2 (ADR-011): separate claim
  type, needs manifest parsing.

## Explicitly rejected (see DECISIONS.md)

- LLM-judged semantic drift inside `check` (ADR-003). If ever, a separate
  opt-in `claimcheck review` command.
- URL link checking — crowded space (lychee et al.), zero differentiation.
- Full CommonMark parsing (ADR-004) without field evidence it's needed.

## Open questions for next session

- Should suffix resolution require uniqueness (flag ambiguous basenames like
  `index.ts` matching 40 files)? Currently first-match-wins satisfies
  existence, which can hide a deletion when a same-named file exists elsewhere.
  (v0.3's worktree exclusion removed the worst instance of this in the field.)
- Import-graph reachability: extract `@` imports from any file transitively
  imported by CLAUDE.md, instead of the basename gate (ADR-013)?
- Stamp granularity: per-doc today; per-section stamps for long KB files?
- Windows: path handling is POSIX-assumed; untested.
