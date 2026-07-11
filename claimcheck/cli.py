"""claimcheck command-line interface.

Exit codes: 0 clean · 1 findings (errors; warnings too with --strict) · 2 usage/env error.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, claims as claims_mod, config as config_mod
from .discover import discover
from .markdown import parse
from .report import render_json, render_text
from .stamp import stamp_file
from .verify import Verifier


def _load(paths: list[str]):
    start = paths[0] if paths and os.path.isdir(paths[0]) else "."
    root = config_mod.find_root(start)
    cfg = config_mod.load(root)
    return root, cfg


def _extract_all(root, cfg, docs, symbols_enabled):
    by_doc = {}
    for rel in docs:
        try:
            with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
                doc = parse(f.read(), rel.replace(os.sep, "/"))
        except OSError as e:
            print(f"warning: cannot read {rel}: {e}", file=sys.stderr)
            continue
        extracted = claims_mod.extract(doc, symbols_enabled=symbols_enabled)
        by_doc[doc.path] = [c for c in extracted if not cfg.is_target_ignored(c.value)]
    return by_doc


def cmd_check(args) -> int:
    try:
        root, cfg = _load(args.paths)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    symbols = "off" if args.no_symbols else cfg.symbols
    docs = discover(args.paths, cfg)
    if not docs:
        print("no markdown documents found", file=sys.stderr)
        return 2
    by_doc = _extract_all(root, cfg, docs, symbols_enabled=symbols != "off")
    res = Verifier(root, symbol_severity=symbols).verify(by_doc)
    print(render_json(res, len(docs)) if args.format == "json"
          else render_text(res, len(docs)))
    errors = any(f.severity == "error" for f in res.findings)
    warns = any(f.severity == "warn" for f in res.findings)
    return 1 if errors or (args.strict and warns) else 0


def cmd_claims(args) -> int:
    root, cfg = _load(args.paths)
    docs = discover(args.paths, cfg)
    by_doc = _extract_all(root, cfg, docs, symbols_enabled=True)
    for doc_path, doc_claims in sorted(by_doc.items()):
        for c in doc_claims:
            extra = f"  {c.extra}" if c.extra else ""
            print(f"{doc_path}:{c.line}  {c.type.value}  {c.value}{extra}")
    return 0


def cmd_stamp(args) -> int:
    root, cfg = _load(args.paths)
    docs = discover(args.paths, cfg)
    if not docs:
        print("no markdown documents found", file=sys.stderr)
        return 2
    try:
        for rel in docs:
            sha = stamp_file(root, rel)
            print(f"stamped {rel} @ {sha[:12]}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claimcheck",
        description="A linter that keeps agent-facing docs true: verifies paths, "
                    "links, anchors, symbols, and commit citations in markdown "
                    "against the actual codebase.",
    )
    parser.add_argument("--version", action="version", version=f"claimcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="verify docs and report drift")
    p_check.add_argument("paths", nargs="*", help="docs or directories (default: repo root)")
    p_check.add_argument("--format", choices=("text", "json"), default="text")
    p_check.add_argument("--strict", action="store_true", help="warnings also fail (exit 1)")
    p_check.add_argument("--no-symbols", action="store_true", help="skip symbol claims")
    p_check.set_defaults(func=cmd_check)

    p_claims = sub.add_parser("claims", help="list extracted claims (debugging)")
    p_claims.add_argument("paths", nargs="*")
    p_claims.set_defaults(func=cmd_claims)

    p_stamp = sub.add_parser("stamp", help="write verified-commit front matter")
    p_stamp.add_argument("paths", nargs="+", help="docs to stamp")
    p_stamp.set_defaults(func=cmd_stamp)

    args = parser.parse_args(argv)
    return args.func(args)
