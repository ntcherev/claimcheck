# claimcheck

[![ci](https://github.com/ntcherev/claimcheck/actions/workflows/ci.yml/badge.svg)](https://github.com/ntcherev/claimcheck/actions/workflows/ci.yml)

**A linter that keeps agent-facing docs true.**

Coding agents read `CLAUDE.md`, `AGENTS.md`, and `docs/kb/*.md` and act on them
verbatim. A stale doc no longer just confuses a human — it sends an agent to a
file that moved three months ago, or has it "fix" code to match documentation
that was wrong. claimcheck extracts the **verifiable claims** your markdown
makes about the codebase and checks every one of them against reality:

```text
$ claimcheck check
docs/kb/loop-core.md
  L290 [error] line-out-of-range: `PipelineExecutor.java` cites line 1172 but the file has 1098 lines
docs/kb/research-pipeline.md
  L74 [error] path-missing: `SearchContextTool.java` does not exist (checked repo root and doc dir)
  L187 [warn] symbol-missing: symbol `app.cost.fastPath` not found anywhere in the repo

3 error(s), 1 warning(s) · 8 doc(s) scanned (5 clean) · 942 claim(s) checked, 12 skipped
```

Deterministic, offline, zero dependencies (Python ≥ 3.11 stdlib only), no API
keys. Exit codes are CI-friendly: `0` clean, `1` drift found, `2` usage error.

## What it checks

| Claim | Example in your markdown | Finding when it drifts |
|---|---|---|
| Path | `` `src/planner.py` ``, `` `AgentManager.java` ``, `` `.../tripwire/TripwireExecutor.java` `` | `path-missing` |
| Line reference | `` `src/planner.py:142` `` | `line-out-of-range` |
| Relative link | `[design](../docs/design.md)` | `link-broken` |
| Anchor | `[setup](README.md#install)` | `anchor-missing` |
| Symbol | `` `Planner.execute()` ``, `` `Foo#bar` `` | `symbol-missing` |
| Command path | `./scripts/dev.sh` inside a ```` ```bash ```` fence | `command-path-missing` |
| Memory import | `@AGENTS.md` in `CLAUDE.md` / `AGENTS.md` prose | `import-missing` |
| Absence | `` `OldTool.java` was deleted `` + `claimcheck:gone` marker | `gone-still-exists` |
| Commit citation | `verified against commit abc1234` | `commit-missing` | <!-- claimcheck:ignore -->

| Freshness stamp | `verified-commit:` front matter | `stamp-stale` |

Paths are resolved generously before being reported: repo root, the doc's own
directory, then a suffix match anywhere in the tree (so `AgentManager.java`
and abbreviated `.../deep/File.java` citations resolve). Ambiguous
extension-less tokens (`key/value`) are skipped, not reported — errors are
meant to be trustworthy. Symbol checks deliberately ignore markdown files as
evidence: a doc mentioning a symbol must not vouch for its own claim.

Four deliberate exceptions keep verdicts honest and identical across checkouts:

- **Memory imports get runtime semantics.** A `@path` import in `CLAUDE.md`,
  `CLAUDE.local.md`, or `AGENTS.md` is checked exactly where the agent
  runtime would load it — relative to the importing file, no generous
  fallbacks. A dangling import silently loads nothing, so it reports as an
  error. Skill docs (`.claude/skills/**/SKILL.md`) are checked like any
  other markdown.
- **Cites that escape the repo are skipped.** `../sibling-repo/pom.xml` in a
  multi-repo workspace can't be verified inside this checkout, so it counts
  as skipped rather than failing your CI.
- **Stale agent worktrees are never evidence.** Files under
  `.claude/worktrees` (leftover agent checkouts) don't satisfy claims — a
  deleted file "existing" in a stale copy would mask real drift.
- **Gitignored paths are invisible, both ways.** A `.env` that exists only
  in your checkout is not evidence (CI's clone won't have it), and citing
  one is never reported as drift — the verdict is the same in your working
  copy and a fresh clone.

## The stamp workflow

The feature the rest of the tool is built around: a doc can carry a
**freshness stamp** asserting "I verified this doc against the code as of this
commit."

```text
$ claimcheck stamp docs/kb/pipeline.md
stamped docs/kb/pipeline.md @ 62b3d3f6a1c2
```

This writes front matter (`verified-commit`, `verified-date`). From then on,
`claimcheck check` compares the files the doc actually cites against git
history since the stamp:

```text
docs/kb/pipeline.md
  L1 [warn] stamp-stale: verified at `62b3d3f6a1c2` (14 commits ago) but 4 of 12 cited files changed since: src/planner.py, src/loop.py, …
```

You re-read the doc, fix what drifted, re-stamp. The doc's freshness is now a
checkable property instead of a hope.

## Install / run

No install needed — it's stdlib-only:

```text
python3 -m claimcheck check          # from a checkout, or with PYTHONPATH set
```

Or install the `claimcheck` command with `pip install .` from this repo.

```text
claimcheck check [paths...]          # verify docs (default: whole repo)
claimcheck check --since <ref>       # only docs changed since a git ref (fast pre-commit runs)
claimcheck check --strict            # warnings also fail CI
claimcheck check --format json       # machine-readable findings
claimcheck check --explain           # show where each path claim resolved
claimcheck check --no-symbols        # skip symbol claims
claimcheck claims [paths...]         # debug: list every claim extracted
claimcheck stamp <docs...>           # write verified-commit front matter
claimcheck stamp --all-stale         # restamp stale-only docs, print re-verify checklist
```

## CI and pre-commit

As a GitHub Action (checkout with history so freshness stamps can be verified):

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: ntcherev/claimcheck@v0.4.0
  with:
    paths: docs        # optional, default: whole repo
    strict: "true"     # optional, fail on warnings too
```

As a pre-commit hook (checks only docs you touched — instant on non-doc commits):

```yaml
repos:
  - repo: https://github.com/ntcherev/claimcheck
    rev: v0.4.0
    hooks:
      - id: claimcheck
```

## Configuration

Optional `.claimcheck.toml` at the repo root:

```toml
[claimcheck]
exclude = ["docs/archive/**"]   # docs not scanned at all
ignore = ["legacy/*"]           # claim targets never reported
symbols = "warn"                # off | warn | error
fences = "warn"                 # off | warn | error — path claims in ```bash fences

[claimcheck.severity]           # per-finding-code overrides
anchor-missing = "error"        # off | warn | error
```

Inline markers (HTML comments, invisible when rendered):

- `<!-- claimcheck:ignore -->` — the whole line is invisible to the checker.
- `<!-- claimcheck:ignore weird/* -->` — only claim targets on this line
  matching the glob(s) are dropped; every other cite stays verified.
- `<!-- claimcheck:gone -->` — inverts the line's claims: the doc asserts
  these paths/symbols **no longer exist**, and a revert that resurrects one
  flags every doc that recorded the deletion (`gone-still-exists`).

## Scope, honestly

claimcheck verifies **mechanical truth**: this path exists, this line exists,
this symbol appears, this commit is real, this doc was re-verified after the
code it cites changed. It cannot tell you that prose *semantics* drifted —
pairing the stamp workflow with review is the intended use. It checks claims
about *this* repository only; URLs are out of scope (link checkers exist).

## Project docs

- [Architecture](docs/ARCHITECTURE.md) — module map and data flow
- [Decisions](docs/DECISIONS.md) — ADR log: why it is the way it is
- [Roadmap](docs/ROADMAP.md) — where this is going
- [Research](docs/RESEARCH.md) — the market/gap research behind the project
