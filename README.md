# claimcheck

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
| Commit citation | `verified against commit abc1234` | `commit-missing` | <!-- claimcheck:ignore -->

| Freshness stamp | `verified-commit:` front matter | `stamp-stale` |

Paths are resolved generously before being reported: repo root, the doc's own
directory, then a suffix match anywhere in the tree (so `AgentManager.java`
and abbreviated `.../deep/File.java` citations resolve). Ambiguous
extension-less tokens (`key/value`) are skipped, not reported — errors are
meant to be trustworthy. Symbol checks deliberately ignore markdown files as
evidence: a doc mentioning a symbol must not vouch for its own claim.

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

Suppress a single line with an HTML comment: `` `old/path.py` `` `<!-- claimcheck:ignore -->`.

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
