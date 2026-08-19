"""`conductor diff` — the primary interactive command.

Shows every drifted resource and, one at a time, asks whether to pull it
(platform -> repo) or push it (repo -> platform), or skip it. Accepted
actions execute immediately. `--check` (or running outside a TTY) instead
does a pure read-only report — CI-friendly, exits 1 if there's any drift.
"""

from __future__ import annotations

import sys

from rich.prompt import Prompt

from ..diffing import Change
from ..plan import AbortRun, Decision
from ..render import prompt_choices, render_change_header, render_result_line, render_summary
from ._common import build_runner, console, err_console, matches_filter


class InteractiveDecider:
    """Per-resource prompt with a sticky "apply this direction to everything
    left in the run" shortcut (`all-push` / `all-pull`)."""

    def __init__(self, org: str | None, space: str | None) -> None:
        self.org = org
        self.space = space
        self.sticky: Decision | None = None

    def __call__(self, ch: Change) -> Decision:
        if not matches_filter(ch, self.org, self.space):
            return "skip"
        if self.sticky is not None:
            decision = self.sticky if self.sticky in ch.directions else "skip"
            render_change_header(console, ch)
            console.print(f"    -> [dim]{decision} (sticky)[/dim]")
            return decision

        render_change_header(console, ch)
        choices = prompt_choices(ch)
        raw = Prompt.ask("  " + "/".join(choices), console=console, choices=choices, default="skip")
        if raw == "abort":
            return "abort"
        if raw == "all-push":
            self.sticky = "push"
            return "push"
        if raw == "all-pull":
            self.sticky = "pull"
            return "pull"
        return raw  # "push" | "pull" | "skip"


def diff_(instance: str, org: str | None = None, space: str | None = None, check: bool = False) -> None:
    interactive = not check and sys.stdin.isatty() and sys.stdout.isatty()

    with build_runner(instance) as runner:
        if not interactive:
            summary = runner.run_all_readonly()
            for stage in summary.stages:
                stage.changes = [c for c in stage.changes if matches_filter(c, org, space)]
            render_summary(console, summary)
            if summary.has_drift:
                raise SystemExit(1)
            return

        decide = InteractiveDecider(org, space)
        try:
            org_stage = runner.run_organizations(decide, stop_on_error=False)
            space_stage = runner.run_spaces(decide, stop_on_error=False)
            provider_stage = runner.run_providers(decide, stop_on_error=False)
            sk_stage, secrets = runner.run_service_keys(decide, stop_on_error=False)
        except AbortRun:
            console.print("[yellow]Aborted.[/yellow]")
            raise SystemExit(1)

        # Each change's execution result prints right after its own prompt
        # (via render_result_line, called inline below) rather than re-showing
        # the whole diff a second time at the end.
        for stage in (org_stage, space_stage, provider_stage, sk_stage):
            for ch in stage.changes:
                render_result_line(console, ch)
                if ch.result == "error":
                    err_console.print(f"[red]  {ch.resource_type} {ch.key}: {ch.error}[/red]")
            if stage.pending_note:
                console.print(f"  [dim]{stage.pending_note}[/dim]")

        for key_name, path in secrets:
            console.print(
                f"[yellow]Service key secret for '{key_name}' written to {path} "
                f"— move it to a real secret manager.[/yellow]"
            )

        all_changes = [c for s in (org_stage, space_stage, provider_stage, sk_stage) for c in s.changes]
        pushed = sum(1 for c in all_changes if c.result == "pushed")
        pulled = sum(1 for c in all_changes if c.result == "pulled")
        skipped = sum(1 for c in all_changes if c.result == "skipped")
        errors = sum(1 for c in all_changes if c.result == "error")
        console.rule(style="dim")
        console.print(f"{pushed} pushed, {pulled} pulled, {skipped} skipped, {errors} error(s)")
