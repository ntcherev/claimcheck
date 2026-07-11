---
verified-commit: bde8afa877dd93a5f99e49264b19d84dacddeaad
verified-date: 2026-07-11
---
# Decision log

ADR-style, newest last. Each entry: context → decision → consequences.

## ADR-001 · 2026-07-11 · Build claimcheck (docs-truth linter)

**Context.** Blank-canvas mandate: build something with real utility that the
owner would personally use and others would adopt. The owner's production
repos all mandate hand-maintained `docs/kb/*.md` +
`CLAUDE.md` with manual notes like "citation-verified against code at commit
<sha>" and "line numbers drift". Web research (see RESEARCH.md) showed the
agent-context-file ecosystem (AGENTS.md et al.) exploding with no tool that
verifies doc claims against code. An earlier idea (content-addressed snapshot
tool) was vetoed as too derivative of git/restic; a Sourcetrail-gap idea died
on discovering active forks.

**Decision.** A deterministic linter that extracts verifiable claims from
markdown and checks them against the repo, plus a `verified-commit` stamp
workflow making doc freshness checkable.

**Consequences.** Immediately dogfoodable on the owner's repos (first run on
the private validation corpus found real drift: dead file refs, line
citations past EOF).
Distinct from the LLM-based `doc-drift` GitHub Action: offline, no API key,
deterministic, trustworthy in CI.

## ADR-002 · 2026-07-11 · Pure Python stdlib, zero dependencies

**Context.** Environment has Python 3.13; user must approve any downloads.
**Decision.** Stdlib only (argparse, tomllib, re, subprocess for git). No
markdown library, no packaging beyond setuptools metadata.
**Consequences.** `python3 -m claimcheck` works from a bare checkout;
`requires-python >= 3.11` (tomllib). Markdown parsing is a hand-rolled subset
(ADR-004).

## ADR-003 · 2026-07-11 · Deterministic core; LLM assist deferred

**Context.** "Docs drift" tools in the wild reach for an LLM to judge
semantic drift, which makes findings non-reproducible and CI-hostile.
**Decision.** v0.1 checks only mechanically verifiable claims. Semantic
checks, if ever, become a separate opt-in command, never part of `check`.
**Consequences.** Findings are reproducible; the tool never needs keys or
network. Semantic drift is explicitly out of scope (README says so).

## ADR-004 · 2026-07-11 · Hand-rolled markdown scanner (subset semantics)

**Decision.** `markdown.py` recognizes exactly: `---` front matter, ATX
headings, ```/~~~ fences, inline code spans, inline links/images. Fenced
content is never scanned for claims. `claimcheck:ignore` in a line skips it.
**Consequences.** Some CommonMark constructs (setext headings, reference
links, indented code blocks) are invisible — acceptable: agent docs
overwhelmingly use the recognized subset. Revisit only with evidence.

## ADR-005 · 2026-07-11 · Precision over recall for findings

**Context.** First dogfood run on the validation corpus produced 462 errors, mostly false
positives (bare filenames, `.../abbreviated/paths.java`, enum lists,
extension-less tokens).
**Decision.** Resolve paths generously (root → doc dir → suffix match via
basename index; strip ellipses and leading `../`); report a missing PATH only
if its basename has a known extension; reject ALL_CAPS/slash lists at
extraction. Symbols and anchors default to `warn`, not `error`.
**Consequences.** 462 → 13 findings on the same corpus, spot-checked as real
drift. Cost: a genuinely missing extension-less dir claim is silently
skipped; a moved-but-still-existing file satisfies its claim. Documented in
README ("Scope, honestly").

## ADR-006 · 2026-07-11 · Markdown is not evidence for symbol claims

**Decision.** The symbol-search corpus excludes `.md`/`.mdx`/`.markdown`.
**Consequences.** A doc (or a copy of it) can never satisfy its own symbol
claim. Symbols defined only in docs (rare, e.g. planned APIs) will warn —
intended behavior.

## ADR-007 · 2026-07-11 · Renamed docdrift → claimcheck

**Context.** Pre-publish collision check found `jbrockSTL/doc-drift`, an
LLM-based GitHub Action marketed as "DocDrift".
**Decision.** Renamed to `claimcheck` (verb-able, describes the mechanism,
PyPI name free; only collision is an unrelated academic fact-checking repo).
Stamp front-matter keys (`verified-commit`, `verified-date`) stay
tool-agnostic on purpose.

## ADR-008 · 2026-07-11 · unittest over pytest

**Decision.** stdlib `unittest`, real `git` subprocesses against temp repos,
no mocks. Follows ADR-002; pytest would be the first dependency and buys
little at this scale (53 tests, 0.3 s).

## ADR-009 · 2026-07-11 · Stamp staleness tracks cited code files only

**Context.** The commit that adds stamps modifies every stamped doc; docs
cite each other, so each stamp immediately flagged its siblings as stale
(bootstrap loop). Directory citations also inflated the changed-file count
via subtree pathspecs.
**Decision.** The staleness set for a stamp is the doc's cited paths minus
markdown files (they carry their own stamps — mirrors ADR-006) and minus
directories; only regular code files count.
**Consequences.** Docs-only commits never invalidate stamps. A doc whose
*meaning* depends on another doc must cite that doc's underlying code to be
protected — acceptable, staleness is a code-drift signal.

## ADR-010 · 2026-07-11 · No owner-specific information in repo or history

**Context.** Pre-publish audit found the validation corpus's internal class
names, local paths, and a committed `.claude/settings.local.json` in the
first two commits; history was rebuilt before any push.
**Decision.** Public-repo hygiene rule (also in AGENTS.md): owner-private
identifiers never enter files or history; `.claude/` is gitignored; validation
corpus specifics live in the assistant's project memory, not the repo.

## ADR-011 · 2026-07-11 · Command claims: bash-ish fences, slash-required, distinct code

**Context.** v0.2 adds verification of paths inside fenced code blocks — the
reason fences were collected since v0.1. Fences are example-heavy, so the
false-positive risk is the highest of any claim type.
**Decision.** Only fences whose info string is shell-like (`bash`, `sh`,
`shell`, `zsh`, `fish`, `console`, `terminal`) are scanned; ```text/```python
and bare fences never are (that's where sample *output* lives). Tokens must
contain a `/`, pass the normal path heuristics, and not be absolute; comment
lines are skipped. Findings get their own code `command-path-missing` at
severity `warn` by default (config `fences = off|warn|error`), so they never
break CI unless opted in.
**Consequences.** `make`/`npm run` target verification is deferred — it needs
Makefile/package.json parsing and is a separate claim type, not a path claim.

## ADR-012 · 2026-07-11 · --since includes uncommitted work; empty selection passes

**Decision.** `check --since <ref>` scopes to docs that differ from `<ref>`
in *any* way: committed changes, working-tree edits, and untracked files
(`git diff --name-only <ref>` ∪ `git ls-files --others`). An empty selection
prints "nothing to check" and exits 0 — a scoped check with no scope is a
pass, not an error; a bad ref exits 2.
**Consequences.** Safe as a pre-commit hook: new docs are caught before their
first commit, and unchanged-doc drift (code moved under a stale doc) is
deliberately out of scope for `--since` — run the full `check` in CI for that.
