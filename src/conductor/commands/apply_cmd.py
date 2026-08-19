"""`conductor apply` — repo -> platform, non-interactive bulk push.

Shows the plan, asks one y/n for the whole batch (or `--yes` skips it), then
executes every add/update change in dependency order. Stops with full
context on the first failure (does not attempt to continue past it)."""

from __future__ import annotations

from rich.prompt import Confirm

from ..diffing import Change
from ..plan import AbortRun, Decision, RunSummary
from ..render import render_summary
from ._common import build_runner, console, err_console, matches_filter


def apply_(instance: str, org: str | None = None, space: str | None = None, yes: bool = False) -> None:
    with build_runner(instance) as runner:
        preview = runner.run_all_readonly()
        for stage in preview.stages:
            stage.changes = [
                c for c in stage.changes if c.kind in ("add", "update") and matches_filter(c, org, space)
            ]
        render_summary(console, preview)
        if not preview.has_drift:
            return

        if not yes and not Confirm.ask("Push these changes to the platform?", default=False):
            console.print("Aborted — no changes made.")
            raise SystemExit(1)

        def decide(ch: Change) -> Decision:
            if not matches_filter(ch, org, space) or ch.kind not in ("add", "update"):
                return "skip"
            return "push"

        try:
            org_stage = runner.run_organizations(decide)
            space_stage = runner.run_spaces(decide)
            provider_stage = runner.run_providers(decide)
            sk_stage, secrets = runner.run_service_keys(decide)
        except AbortRun:
            console.print("Aborted.")
            raise SystemExit(1)
        except Exception as e:  # noqa: BLE001
            err_console.print(f"[red]apply failed: {e}[/red]")
            raise SystemExit(1) from e

        render_summary(console, RunSummary(stages=[org_stage, space_stage, provider_stage, sk_stage]))
        for key_name, path in secrets:
            console.print(
                f"[yellow]Service key secret for '{key_name}' written to {path} "
                f"— move it to a real secret manager.[/yellow]"
            )
