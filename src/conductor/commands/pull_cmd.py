"""`conductor pull` — platform -> repo, non-interactive bulk pull.

Only organizations and spaces are pullable (providers/service keys are
derived, never hand-authored — they only show up inside interactive `diff`).
Rewrites the owning YAML file canonically for every drifted or unmanaged
(platform-only) org/space."""

from __future__ import annotations

from rich.prompt import Confirm

from ..diffing import Change
from ..plan import Decision, RunSummary
from ..render import render_summary
from ._common import build_runner, console, matches_filter


def pull_(instance: str, org: str | None = None, space: str | None = None, yes: bool = False) -> None:
    with build_runner(instance) as runner:
        preview = runner.run_all_readonly()
        for stage in preview.stages:
            if stage.resource_type not in ("organization", "space"):
                stage.changes = []
                continue
            stage.changes = [
                c for c in stage.changes if c.kind in ("update", "unmanaged") and matches_filter(c, org, space)
            ]
        render_summary(console, preview)
        if not any(s.changes for s in preview.stages):
            return

        if not yes and not Confirm.ask("Pull these values into the repo?", default=False):
            console.print("Aborted — no files changed.")
            raise SystemExit(1)

        def decide(ch: Change) -> Decision:
            if not matches_filter(ch, org, space) or ch.kind not in ("update", "unmanaged"):
                return "skip"
            return "pull"

        org_stage = runner.run_organizations(decide)
        space_stage = runner.run_spaces(decide)
        render_summary(console, RunSummary(stages=[org_stage, space_stage]))
