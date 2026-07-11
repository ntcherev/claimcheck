"""Render verification results as human text or JSON."""

from __future__ import annotations

import json
from dataclasses import asdict

from .verify import Result


def render_text(res: Result, docs_scanned: int) -> str:
    lines: list[str] = []
    by_doc: dict[str, list] = {}
    for f in res.findings:
        by_doc.setdefault(f.doc, []).append(f)

    for doc, findings in sorted(by_doc.items()):
        lines.append(doc)
        for f in findings:
            lines.append(f"  L{f.line} [{f.severity}] {f.code}: {f.message}")
        lines.append("")

    errors = sum(1 for f in res.findings if f.severity == "error")
    warns = sum(1 for f in res.findings if f.severity == "warn")
    clean = docs_scanned - len(by_doc)
    lines.append(
        f"{errors} error(s), {warns} warning(s) · "
        f"{docs_scanned} doc(s) scanned ({clean} clean) · "
        f"{res.claims_checked} claim(s) checked, {res.claims_skipped} skipped"
    )
    return "\n".join(lines)


def render_json(res: Result, docs_scanned: int) -> str:
    errors = sum(1 for f in res.findings if f.severity == "error")
    warns = sum(1 for f in res.findings if f.severity == "warn")
    payload = {
        "findings": [asdict(f) for f in res.findings],
        "summary": {
            "errors": errors,
            "warnings": warns,
            "docs_scanned": docs_scanned,
            "claims_checked": res.claims_checked,
            "claims_skipped": res.claims_skipped,
        },
    }
    if res.explanations:
        payload["explanations"] = res.explanations
    return json.dumps(payload, indent=2)
