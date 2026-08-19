"""`conductor validate` — local-only schema + referential checks, no network."""

from __future__ import annotations

from ._common import console, load_config_or_exit


def validate(instance: str) -> None:
    cfg = load_config_or_exit(instance)  # exits 1 with details on failure
    n_orgs = len(cfg.orgs)
    n_projects = len(cfg.gcp_projects)
    n_pairs = len(cfg.space_org_pairs())
    console.print(f"[green]OK[/green] instance '{instance}': {n_orgs} org(s), {n_projects} gcp project(s), {n_pairs} space×org pairing(s).")
