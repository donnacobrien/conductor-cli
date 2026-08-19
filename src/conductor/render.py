"""rich-based terraform-style rendering, shared by every command."""

from __future__ import annotations

from rich.console import Console

from .diffing import Change
from .plan import RunSummary, StageResult

SYMBOL = {"add": "[green]+[/green]", "update": "[yellow]~[/yellow]", "unmanaged": "[cyan]?[/cyan]"}
LABEL = {"add": "create", "update": "update", "unmanaged": "unmanaged (platform-only)"}


def _label_for(ch: Change) -> str:
    parts = [ch.resource_type, ch.key]
    return " ".join(parts)


def render_change_header(console: Console, ch: Change) -> None:
    """The diff itself — resource, kind, field-level before/after. No outcome."""
    console.print(f"{SYMBOL[ch.kind]} {_label_for(ch)}  [dim]\\[{LABEL[ch.kind]}][/dim]")
    if ch.pending_reason:
        console.print(f"    [dim]pending: {ch.pending_reason}[/dim]")
    for field_name, (repo_val, platform_val) in ch.diff_fields.items():
        console.print(f"    {field_name}: [red]{repo_val!r}[/red] (repo) -> [green]{platform_val!r}[/green] (platform)")
    if ch.kind == "add" and ch.desired:
        for field_name, val in ch.desired.fields.items():
            console.print(f"    {field_name}: [green]{val!r}[/green] (repo only)")
    if ch.kind == "unmanaged" and ch.actual:
        for field_name, val in ch.actual.fields.items():
            console.print(f"    {field_name}: [cyan]{val!r}[/cyan] (platform only)")


def render_result_line(console: Console, ch: Change) -> None:
    if not ch.result:
        return
    result_style = {"pushed": "green", "pulled": "green", "skipped": "dim", "error": "red"}.get(ch.result, "")
    console.print(f"    -> [{result_style}]{ch.result}[/{result_style}]" + (f": {ch.error}" if ch.error else ""))


def render_change(console: Console, ch: Change) -> None:
    render_change_header(console, ch)
    render_result_line(console, ch)


def render_stage(console: Console, stage: StageResult) -> None:
    if not stage.changes and not stage.pending_note:
        return
    console.rule(f"[bold]{stage.resource_type}[/bold]", style="dim")
    for ch in stage.changes:
        render_change(console, ch)
    if stage.pending_note:
        console.print(f"  [dim]{stage.pending_note}[/dim]")


def render_summary(console: Console, summary: RunSummary) -> None:
    for stage in summary.stages:
        render_stage(console, stage)
    console.rule(style="dim")
    add = sum(1 for c in summary.all_changes if c.kind == "add")
    upd = sum(1 for c in summary.all_changes if c.kind == "update")
    unm = sum(1 for c in summary.all_changes if c.kind == "unmanaged")
    if not (add or upd or unm):
        console.print("[green]No drift — repo and platform match.[/green]")
    else:
        console.print(f"{add} to create, {upd} to update, {unm} unmanaged (platform-only)")


def prompt_choices(ch: Change) -> list[str]:
    """Valid decision words for this change, in prompt order. "abort" is
    always implicitly available on top of these."""
    choices: list[str] = []
    if "push" in ch.directions:
        choices += ["push", "all-push"]
    if "pull" in ch.directions:
        choices += ["pull", "all-pull"]
    choices.append("skip")
    choices.append("abort")
    return choices
