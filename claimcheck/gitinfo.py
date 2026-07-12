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


def files_changed_from(root: str, ref: str) -> set[str] | None:
    """All files that differ from `ref`: committed changes, working-tree
    modifications, and untracked files. None if the ref is invalid."""
    r = _git(root, "diff", "--name-only", ref, "--")
    if r.returncode != 0:
        return None
    files = {ln for ln in r.stdout.splitlines() if ln.strip()}
    r2 = _git(root, "ls-files", "--others", "--exclude-standard")
    if r2.returncode == 0:
        files.update(ln for ln in r2.stdout.splitlines() if ln.strip())
    return files


def changed_files_since(root: str, sha: str, paths: list[str]) -> list[str]:
    """Repo-relative paths (from `paths`) touched since `sha` — committed
    changes AND working-tree edits, so a stamp goes stale the moment a cited
    file is modified, not only after the commit (ADR-019)."""
    if not paths:
        return []
    r = _git(root, "diff", "--name-only", sha, "--", *paths)
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def ls_files(root: str) -> list[str] | None:
    """Every path git considers part of the repo: tracked plus untracked-
    but-not-ignored. None when git fails (not a repo) — callers fall back
    to filesystem walks."""
    r = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if r.returncode != 0:
        return None
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def is_ignored(root: str, rel: str) -> bool:
    """True if the path is excluded by gitignore rules."""
    return _git(root, "check-ignore", "-q", "--", rel).returncode == 0
