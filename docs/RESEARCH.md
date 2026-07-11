---
verified-commit: bde8afa877dd93a5f99e49264b19d84dacddeaad
verified-date: 2026-07-11
---
# Market / gap research (2026-07-11)

Why claimcheck exists, with sources. Summarized from live web research at
project inception.

## The niche

Agent context files are now infrastructure: AGENTS.md (proposed by OpenAI
Aug 2025, donated to the Linux Foundation's Agentic AI Foundation Dec 2025)
is read by 30+ agents; repos accumulate CLAUDE.md, .cursorrules,
copilot-instructions.md — "a markdown museum for confused bots"
([morphllm guide](https://www.morphllm.com/agents-md-guide),
[codersera comparison](https://codersera.com/blog/agents-md-vs-claude-md-vs-cursor-rules-comparison-2026/)).
Agents *act* on these files, so drift is an active hazard, not cosmetic.

Direct evidence of the pain in the owner's own private repos: they mandate KB
docs "citation-verified against code at commit <sha>" with manual
re-verification, and note "line numbers drift" as a known failure mode.

## Adjacent tools and why they don't cover this

- **Link checkers** (lychee, markdown-link-check): URLs and file links only;
  no inline-code paths, line refs, symbols, commits, or freshness stamps.
- **[jbrockSTL/doc-drift](https://github.com/jbrockSTL/doc-drift)** ("DocDrift"
  GitHub Action): LLM judges staged diffs vs docs. Non-deterministic, needs
  API key, judgment-based. claimcheck is the deterministic complement (and
  was renamed from "docdrift" to avoid this collision — ADR-007).
- **LLM observability/eval platforms** (Confident AI, Braintrust, Langfuse…):
  crowded space, orthogonal problem (runtime behavior, not repo docs).

## Dead ends investigated

- **Sourcetrail-gap** (code visualization): looked promising ("Sourcetrail
  alternative" heavily searched after 2021 archival) but the
  [petermost fork](https://github.com/petermost/Sourcetrail) is actively
  maintained (releases through Dec 2025), plus NumbatUI and
  OpenSourceSourceTrail. Gap mostly filled.
- **Content-addressed snapshot tool**: vetoed as derivative of git/restic.

## Demand signals worth re-checking later

- HN "[what developer tool do you wish existed in 2026](https://news.ycombinator.com/item?id=46345827)":
  recurring themes were codebase-understanding tools and CI friction —
  claimcheck sits in the second.
- Agent-tooling gap lists repeatedly name context management and lock-in
  across CLAUDE.md/memory formats as unsolved
  ([n8n blog](https://blog.n8n.io/we-need-re-learn-what-ai-agent-development-tools-are-in-2026/)).
