"""Configuration: .claimcheck.toml at the repo root (all keys optional).

    [claimcheck]
    exclude = ["docs/archive/**"]        # doc globs not scanned
    ignore = ["legacy/*", "*.png"]       # claim targets never reported
    symbols = "warn"                     # off | warn | error
"""

from __future__ import annotations

import fnmatch
import os
import tomllib
from dataclasses import dataclass, field

CONFIG_FILENAME = ".claimcheck.toml"


@dataclass
class Config:
    root: str = "."
    exclude: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
    symbols: str = "warn"

    def is_doc_excluded(self, rel_path: str) -> bool:
        return any(fnmatch.fnmatch(rel_path, pat) for pat in self.exclude)

    def is_target_ignored(self, value: str) -> bool:
        return any(fnmatch.fnmatch(value, pat) for pat in self.ignore)


def find_root(start: str) -> str:
    """Walk up from `start` to the nearest dir with .claimcheck.toml or .git."""
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, CONFIG_FILENAME)) or \
           os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start)
        cur = parent


def load(root: str) -> Config:
    cfg = Config(root=root)
    path = os.path.join(root, CONFIG_FILENAME)
    if not os.path.exists(path):
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)
    section = data.get("claimcheck", data)
    cfg.exclude = list(section.get("exclude", []))
    cfg.ignore = list(section.get("ignore", []))
    symbols = section.get("symbols", "warn")
    if symbols not in ("off", "warn", "error"):
        raise ValueError(f"{CONFIG_FILENAME}: symbols must be off|warn|error, got {symbols!r}")
    cfg.symbols = symbols
    return cfg
