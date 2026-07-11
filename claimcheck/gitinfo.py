"""Thin subprocess wrappers around git. All functions degrade gracefully:
claimcheck works in non-git directories, it just skips commit claims."""

from __future__ import annotations

import subprocess


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True, text=True, timeout=30,
    )


def is_git_repo(root: str) -> bool:
    try:
        r = _git(root, "rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def toplevel(root: str) -> str | None:
    r = _git(root, "rev-parse", "--show-toplevel")
    return r.stdout.strip() if r.returncode == 0 else None


def head_sha(root: str) -> str | None:
    r = _git(root, "rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def commit_exists(root: str, sha: str) -> bool:
    return _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def commits_since(root: str, sha: str) -> int | None:
    r = _git(root, "rev-list", "--count", f"{sha}..HEAD")
    if r.returncode != 0:
        return None
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def changed_files_since(root: str, sha: str, paths: list[str]) -> list[str]:
    """Repo-relative paths (from `paths`) touched between sha and HEAD."""
    if not paths:
        return []
    r = _git(root, "diff", "--name-only", f"{sha}..HEAD", "--", *paths)
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]
