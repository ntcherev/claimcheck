"""Write `verified-commit` / `verified-date` front-matter stamps.

A stamp is the doc author asserting "I checked this doc against the code
as of this commit." `claimcheck check` then reports when files the doc
cites change after the stamp.
"""

from __future__ import annotations

import datetime
import os

from . import gitinfo
from .markdown import parse

STAMP_COMMIT_KEY = "verified-commit"
STAMP_DATE_KEY = "verified-date"


def stamp_file(root: str, rel_path: str, today: datetime.date | None = None) -> str:
    """Stamp one doc with the current HEAD. Returns the sha used."""
    sha = gitinfo.head_sha(root)
    if not sha:
        raise RuntimeError("not a git repository (or no commits yet) — cannot stamp")
    today = today or datetime.date.today()

    full = os.path.join(root, rel_path)
    with open(full, encoding="utf-8") as f:
        text = f.read()
    doc = parse(text, rel_path)
    lines = text.splitlines(keepends=True)

    if doc.front_matter_span:
        first, last = doc.front_matter_span  # 1-based, inclusive of fences
        body = lines[first:last - 1]  # inside the fences
        body = [ln for ln in body
                if not ln.split(":")[0].strip() in (STAMP_COMMIT_KEY, STAMP_DATE_KEY)]
        body.append(f"{STAMP_COMMIT_KEY}: {sha}\n")
        body.append(f"{STAMP_DATE_KEY}: {today.isoformat()}\n")
        new_lines = lines[:first] + body + lines[last - 1:]
    else:
        header = [
            "---\n",
            f"{STAMP_COMMIT_KEY}: {sha}\n",
            f"{STAMP_DATE_KEY}: {today.isoformat()}\n",
            "---\n",
        ]
        new_lines = header + lines

    with open(full, "w", encoding="utf-8") as f:
        f.write("".join(new_lines))
    return sha
