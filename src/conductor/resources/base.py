"""Shared record types every resource module (organizations/spaces/providers/
service_keys) produces, and that diffing.py compares generically.

Each resource module exposes, at minimum:

    COMPARABLE_FIELDS: tuple[str, ...]   # fields diffing considers for "update"
    def desired(cfg, ...) -> dict[str, DesiredRecord]
    def actual(client, cfg, ...) -> dict[str, ActualRecord]
    def create(client, record: DesiredRecord) -> ActualRecord
    def update(client, actual: ActualRecord, record: DesiredRecord, changed: set[str]) -> ActualRecord   # optional
    def pull(cfg, key, actual: ActualRecord) -> None                                                      # optional

The exact `desired`/`actual` signatures vary per resource (spaces need org
ids, providers/service keys need org+space ids) since the real dependency
chain — org -> space -> provider/service key — is inherently stage-specific.
plan.py orchestrates each stage explicitly rather than forcing a uniform
polymorphic call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DesiredRecord:
    """One resource as it should exist, per the repo (or, for providers/
    service keys, per the fixed built-in template)."""

    key: str
    fields: dict[str, Any]
    payload: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    source_file: Path | None = None


@dataclass
class ActualRecord:
    """One resource as it actually exists on the platform."""

    key: str
    id: str
    fields: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)
