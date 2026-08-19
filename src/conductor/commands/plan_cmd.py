"""`conductor plan` — non-interactive preview of the repo -> platform
direction only (what `apply` would push). Ignores platform-only/unmanaged
resources; use `diff` to see those."""

from __future__ import annotations

from ..render import render_summary
from ._common import build_runner, console, matches_filter


def plan_(instance: str, org: str | None = None, space: str | None = None) -> None:
    with build_runner(instance) as runner:
        summary = runner.run_all_readonly()

    for stage in summary.stages:
        stage.changes = [
            c for c in stage.changes if c.kind in ("add", "update") and matches_filter(c, org, space)
        ]

    render_summary(console, summary)
    if summary.has_drift:
        raise SystemExit(1)
