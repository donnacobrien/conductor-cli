"""Small YAML read/write helpers shared by the config loader and `pull`.

v1 uses plain PyYAML with a canonical dump style (sorted keys off, block
style, no aliases) rather than a comment-preserving round-trip. `pull`
therefore rewrites a whole file canonically instead of patching it in place.
This is a known, accepted limitation for v1 (see plan doc).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
