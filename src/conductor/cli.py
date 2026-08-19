"""conductor: control-plane CLI for Arize AX, driven by YAML config-as-code
under configs/instances/. See the plan doc / README for the full model.
"""

from __future__ import annotations

import typer

from .commands import apply_cmd, delete_cmd, diff_cmd, plan_cmd, pull_cmd, validate_cmd

app = typer.Typer(
    name="conductor",
    help="Control plane for managing Arize AX (orgs/spaces/providers/service keys) as config-as-code.",
    no_args_is_help=True,
)

InstanceOpt = typer.Option(..., "--instance", "-i", help="Instance name from configs/instances/instances.yaml")
OrgOpt = typer.Option(None, "--org", help="Limit to this org")
SpaceOpt = typer.Option(None, "--space", help="Limit to this space")
YesOpt = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt (for CI/scripting)")


@app.command()
def validate(instance: str = InstanceOpt) -> None:
    """Local-only schema + referential checks. No network call."""
    validate_cmd.validate(instance)


@app.command()
def diff(
    instance: str = InstanceOpt,
    org: str = OrgOpt,
    space: str = SpaceOpt,
    check: bool = typer.Option(
        False, "--check", help="Read-only report, no prompts, exit 1 on drift (CI-friendly)."
    ),
) -> None:
    """Show drift and, interactively, pull or push each resource that has it."""
    diff_cmd.diff_(instance, org=org, space=space, check=check)


@app.command()
def plan(instance: str = InstanceOpt, org: str = OrgOpt, space: str = SpaceOpt) -> None:
    """Non-interactive preview of what `apply` would push (repo -> platform only)."""
    plan_cmd.plan_(instance, org=org, space=space)


@app.command()
def apply(instance: str = InstanceOpt, org: str = OrgOpt, space: str = SpaceOpt, yes: bool = YesOpt) -> None:
    """Push repo -> platform: create/update everything the repo declares."""
    apply_cmd.apply_(instance, org=org, space=space, yes=yes)


@app.command()
def pull(instance: str = InstanceOpt, org: str = OrgOpt, space: str = SpaceOpt, yes: bool = YesOpt) -> None:
    """Pull platform -> repo: overwrite local org/space YAML with the platform's values."""
    pull_cmd.pull_(instance, org=org, space=space, yes=yes)


@app.command()
def delete(
    resource_type: str = typer.Argument(..., help="organization | space | provider | service-key"),
    name: str = typer.Argument(..., help="The resource's name"),
    instance: str = InstanceOpt,
    org: str = OrgOpt,
    yes: bool = YesOpt,
) -> None:
    """Imperative, explicit delete. Never part of plan/apply/diff."""
    delete_cmd.delete_(instance, resource_type, name, org=org, yes=yes)


if __name__ == "__main__":
    app()
