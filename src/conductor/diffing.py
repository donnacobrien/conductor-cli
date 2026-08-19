"""Generic desired-vs-actual diff engine, resource-agnostic.

Never emits deletes: a key present only on the platform is reported as
`unmanaged` (informational — pullable if the resource supports it, but
never auto-removed from the platform and never a reason to fail `apply`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .resources.base import ActualRecord, DesiredRecord

ChangeKind = Literal["add", "update", "unmanaged"]
Direction = Literal["push", "pull"]


@dataclass
class Change:
    resource_type: str
    key: str
    kind: ChangeKind
    desired: DesiredRecord | None
    actual: ActualRecord | None
    diff_fields: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # field -> (repo, platform)
    directions: tuple[Direction, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    pending_reason: str | None = None

    # filled in as a run executes this change; unset for a pure read-only plan/diff
    decision: str | None = None  # "push" | "pull" | "skip"
    result: str | None = None  # "pushed" | "pulled" | "skipped" | "error"
    error: str | None = None


def diff(
    resource_type: str,
    desired: dict[str, DesiredRecord],
    actual: dict[str, ActualRecord],
    comparable_fields: tuple[str, ...],
    *,
    supports_pull: bool = True,
    unmanaged_context_fn: Callable[[str], dict] | None = None,
) -> list[Change]:
    changes: list[Change] = []
    for key in sorted(set(desired) | set(actual)):
        d = desired.get(key)
        a = actual.get(key)
        if d and not a:
            changes.append(
                Change(
                    resource_type=resource_type,
                    key=key,
                    kind="add",
                    desired=d,
                    actual=None,
                    directions=("push",),
                    context=d.context,
                )
            )
        elif d and a:
            differing = {
                f: (d.fields.get(f), a.fields.get(f))
                for f in comparable_fields
                if d.fields.get(f) != a.fields.get(f)
            }
            if differing:
                directions: tuple[Direction, ...] = ("push", "pull") if supports_pull else ("push",)
                changes.append(
                    Change(
                        resource_type=resource_type,
                        key=key,
                        kind="update",
                        desired=d,
                        actual=a,
                        diff_fields=differing,
                        directions=directions,
                        context=d.context,
                    )
                )
            # else: in sync, no Change emitted
        else:  # a and not d
            changes.append(
                Change(
                    resource_type=resource_type,
                    key=key,
                    kind="unmanaged",
                    desired=None,
                    actual=a,
                    directions=("pull",) if supports_pull else (),
                    context=unmanaged_context_fn(key) if unmanaged_context_fn else {},
                )
            )
    return changes
