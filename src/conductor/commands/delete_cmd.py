"""`conductor delete` — imperative, explicit, never part of plan/apply/diff.

Requires `--yes` for non-interactive/CI use; interactively it instead prompts
the operator to type the resource's name back to confirm. Either way, it
looks the resource up live first and refuses if it can't find it.
"""

from __future__ import annotations

from typing import Callable

from rich.prompt import Prompt

from ..resources import organizations, providers, service_keys, spaces
from ._common import build_runner, console, err_console

VALID_TYPES = ("organization", "space", "provider", "service-key")


def delete_(
    instance: str,
    resource_type: str,
    name: str,
    org: str | None = None,
    yes: bool = False,
) -> None:
    if resource_type not in VALID_TYPES:
        err_console.print(f"[red]unknown resource type '{resource_type}'. Must be one of: {', '.join(VALID_TYPES)}[/red]")
        raise SystemExit(1)

    with build_runner(instance) as runner:
        client, cfg = runner.client, runner.cfg
        do_delete: Callable[[], None]

        if resource_type == "organization":
            found = organizations.actual(client, cfg).get(name)
            describe = f"organization '{name}'"
            if found:
                do_delete = lambda: client.delete(f"/v2/organizations/{found.id}", context={"org": name})

        elif resource_type == "space":
            if not org:
                err_console.print("[red]--org is required to delete a space[/red]")
                raise SystemExit(1)
            org_ids = {o: rec.id for o, rec in organizations.actual(client, cfg).items()}
            found = spaces.actual(client, cfg, org_ids).get(spaces.make_key(org, name))
            describe = f"space '{name}' in org '{org}'"
            if found:
                do_delete = lambda: client.delete(f"/v2/spaces/{found.id}", context={"org": org, "space": name})

        elif resource_type == "provider":
            found = providers.actual(client, cfg).get(name)
            describe = f"provider '{name}'"
            if found:
                do_delete = lambda: client.delete(f"/v2/ai-integrations/{found.id}", context={"name": name})

        else:  # service-key
            found = service_keys.actual(client, cfg).get(name)
            describe = f"service key '{name}'"
            if found:
                do_delete = lambda: service_keys.revoke(client, found, context={"name": name})

        if not found:
            err_console.print(f"[red]{describe} not found (or already gone) on instance '{instance}'[/red]")
            raise SystemExit(1)

        console.print(
            f"[red]About to delete {describe} (id: {found.id}) on instance '{instance}'. "
            f"This cannot be undone.[/red]"
        )
        if not yes:
            typed = Prompt.ask(f"Type the resource name ('{name}') to confirm")
            if typed != name:
                console.print("Names didn't match — aborted.")
                raise SystemExit(1)

        do_delete()
        console.print(f"[green]Deleted {describe}.[/green]")
