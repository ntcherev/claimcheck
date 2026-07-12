"""claimcheck — a linter that keeps agent-facing docs true.

Agents act on CLAUDE.md / AGENTS.md / docs/kb verbatim, so stale docs are
worse than useless. claimcheck extracts verifiable claims from markdown
(paths, line refs, links, anchors, symbols, commit citations) and checks
them against the codebase. Deterministic, stdlib-only, CI-friendly.
"""

__version__ = "0.3.1"
