"""Find the markdown documents to check."""

from __future__ import annotations

import os

from . import gitinfo
from .config import Config
from .verify import is_excluded_path, prune_dirnames

DOC_EXTS = (".md", ".mdx", ".markdown")


def discover(paths: list[str], cfg: Config) -> list[str]:
    """Resolve CLI path args to a sorted list of repo-relative doc paths.
    Args may be files or directories; default is the repo root.

    Directory discovery covers what git sees (tracked + untracked-unignored,
    ADR-018) so a gitignored scratch doc can't change results between
    checkouts; outside git it falls back to walking. An explicitly named
    file is always included — the user's intent overrides the filter."""
    root = os.path.abspath(cfg.root)
    git_docs = _git_docs(root)
    found: set[str] = set()
    for arg in paths or [root]:
        full = os.path.abspath(arg)
        if os.path.isfile(full):
            rel = os.path.relpath(full, root)
            if not cfg.is_doc_excluded(rel):
                found.add(rel)
            continue
        rel_arg = os.path.relpath(full, root).replace(os.sep, "/")
        if git_docs is not None and not rel_arg.startswith(".."):
            prefix = "" if rel_arg == "." else rel_arg + "/"
            found.update(d for d in git_docs
                         if d.startswith(prefix) and not cfg.is_doc_excluded(d))
            continue
        for dirpath, dirnames, filenames in os.walk(full):
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            dirnames[:] = prune_dirnames(rel_dir, dirnames)
            for fn in sorted(filenames):
                if fn.lower().endswith(DOC_EXTS):
                    rel = os.path.relpath(os.path.join(dirpath, fn), root)
                    if not rel.startswith("..") and not cfg.is_doc_excluded(rel):
                        found.add(rel)
    return sorted(found)


def _git_docs(root: str) -> list[str] | None:
    listed = gitinfo.ls_files(root)
    if listed is None:
        return None
    return [f for f in listed
            if f.lower().endswith(DOC_EXTS) and not is_excluded_path(f)
            and os.path.exists(os.path.join(root, f))]
