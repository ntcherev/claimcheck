"""Find the markdown documents to check."""

from __future__ import annotations

import os

from .config import Config
from .verify import EXCLUDE_DIRS

DOC_EXTS = (".md", ".mdx", ".markdown")


def discover(paths: list[str], cfg: Config) -> list[str]:
    """Resolve CLI path args to a sorted list of repo-relative doc paths.
    Args may be files or directories; default is the repo root."""
    root = os.path.abspath(cfg.root)
    found: set[str] = set()
    for arg in paths or [root]:
        full = os.path.abspath(arg)
        if os.path.isfile(full):
            rel = os.path.relpath(full, root)
            if not cfg.is_doc_excluded(rel):
                found.add(rel)
            continue
        for dirpath, dirnames, filenames in os.walk(full):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
            for fn in sorted(filenames):
                if fn.lower().endswith(DOC_EXTS):
                    rel = os.path.relpath(os.path.join(dirpath, fn), root)
                    if not rel.startswith("..") and not cfg.is_doc_excluded(rel):
                        found.add(rel)
    return sorted(found)
