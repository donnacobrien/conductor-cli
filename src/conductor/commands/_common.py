"""Shared setup used by every command: load config, resolve the API key,
build the HTTP client + Runner, and optional --org/--space filtering."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from rich.console import Console

from ..config.loader import ConfigValidationError, InstanceConfig, load_instance_config
from ..diffing import Change
from ..http import ArizeClient
from ..plan import Runner
from ..settings import MissingApiKeyError, resolve_api_key

console = Console()
err_console = Console(stderr=True)


def load_config_or_exit(instance: str) -> InstanceConfig:
    try:
        return load_instance_config(instance)
    except ConfigValidationError as e:
        err_console.print(f"[red]Config errors for instance '{instance}':[/red]")
        for err in e.errors:
            err_console.print(f"  - {err}")
        raise SystemExit(1) from e


@contextmanager
def build_runner(instance: str) -> Iterator[Runner]:
    cfg = load_config_or_exit(instance)
    try:
        api_key = resolve_api_key(cfg.instance)
    except MissingApiKeyError as e:
        err_console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from e
    with ArizeClient(cfg.instance.base_url, api_key) as client:
        yield Runner(client, cfg, instance)


def matches_filter(ch: Change, org: str | None, space: str | None) -> bool:
    if org and ch.context.get("org") != org:
        return False
    if space and ch.context.get("space") != space:
        return False
    return True
