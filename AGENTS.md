---
verified-commit: cb17dad35405bd70e0a9307c749ee4b1dc8eb2f0
verified-date: 2026-07-11
---
# claimcheck — orientation for agents and future sessions

A linter that keeps agent-facing docs true: extracts verifiable claims
(paths, line refs, links, anchors, symbols, memory imports, commit citations)
from markdown and checks them against the codebase. Stdlib-only Python
(≥3.11), zero deps.

**Catch up in this order:**
1. `docs/DECISIONS.md` — ADR log; read before changing any behavior, several
   heuristics look wrong until you read why they're deliberate (esp. ADR-005).
2. `docs/ARCHITECTURE.md` — module map, data shapes, resolution strategy.
3. `docs/ROADMAP.md` — what's next, what's rejected, open questions.
4. `docs/RESEARCH.md` — market context; why this and not something else.

**Commands:**
- Run tests: `python3 -m unittest discover -s tests` (must stay green and fast)
- Run tool: `python3 -m claimcheck check` (dogfoods this repo via `.claimcheck.toml`)
- Real-world corpus: validate against a large production repo's `docs/kb`
  before releases (the owner keeps one locally; the path lives in project
  memory, deliberately not in this repo)

**House rules:**
- Zero dependencies is a feature, not a limitation (ADR-002). Don't add any.
- `check` must stay deterministic and offline (ADR-003).
- Precision over recall: a reported error must be trustworthy; when a
  heuristic is ambiguous, skip and count it, don't report (ADR-005).
- Every behavior change lands with tests and, if it alters decisions, an ADR.
- Before publishing anywhere, docs get `claimcheck stamp`ed and `check --strict`
  must pass on this repo.
- This is a public repo: nothing owner-specific — private repo names, local
  paths, machine names, internal class/package identifiers — may appear in
  files OR git history. Audit before committing; corpus specifics belong in
  project memory only.
