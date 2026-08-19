"""Orchestrates the four resource stages, in dependency order:

    organizations -> spaces (fan-out) -> providers (derived) -> service keys (derived)

Every command (`validate` excepted) drives this through `Runner`, differing
only in the `decide` callback they pass per stage:

  - `plan`/`diff --check`: `decide` always returns "skip" (pure read-only report)
  - `apply`/`pull`: `decide` returns "push"/"pull" unconditionally (batch already
    confirmed by the command layer) for the one direction that command owns
  - interactive `diff`: `decide` is the per-resource rich prompt

`Runner` re-fetches each stage's `actual()` after executing any changes in it,
rather than hand-tracking created ids incrementally — simpler and correct,
at the cost of a few extra list calls (not perf-sensitive for a control-plane
CLI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from .config.loader import InstanceConfig
from .diffing import Change, diff
from .http import ArizeClient
from .resources import organizations, providers, service_keys, spaces
from .secrets_store import write_secret

Decision = Literal["push", "pull", "skip", "abort"]
DecideFn = Callable[[Change], Decision]


class AbortRun(Exception):
    pass


@dataclass
class StageResult:
    resource_type: str
    changes: list[Change]
    pending_count: int = 0  # derived-resource (org,space) pairs not yet resolvable
    pending_note: str = ""


@dataclass
class RunSummary:
    stages: list[StageResult] = field(default_factory=list)
    secrets_written: list[tuple[str, "object"]] = field(default_factory=list)  # (key_name, Path)

    @property
    def all_changes(self) -> list[Change]:
        return [c for stage in self.stages for c in stage.changes]

    @property
    def has_drift(self) -> bool:
        return any(self.all_changes)


class Runner:
    def __init__(self, client: ArizeClient, cfg: InstanceConfig, instance_name: str) -> None:
        self.client = client
        self.cfg = cfg
        self.instance_name = instance_name
        self.org_ids: dict[str, str] = {}
        self.space_ids: dict[str, str] = {}

    # -- generic per-change execution -------------------------------------

    def _execute(self, ch: Change, decision: Decision, module, stop_on_error: bool, extra_create_arg=None) -> None:
        ch.decision = decision
        if decision == "abort":
            raise AbortRun()
        if decision == "skip" or decision is None:
            ch.result = "skipped"
            return
        try:
            if decision == "push":
                if ch.kind == "add":
                    if extra_create_arg is not None:
                        module.create(self.client, ch.desired, extra_create_arg)
                    else:
                        module.create(self.client, ch.desired)
                elif ch.kind == "update":
                    module.update(self.client, ch.actual, ch.desired, set(ch.diff_fields))
                ch.result = "pushed"
            elif decision == "pull":
                module.pull(self.cfg, ch.key, ch.actual)
                ch.result = "pulled"
        except Exception as e:  # noqa: BLE001 - surfaced via ch.error either way
            ch.result = "error"
            ch.error = str(e)
            if stop_on_error:
                raise

    # -- stage 1: organizations ---------------------------------------------

    def run_organizations(self, decide: DecideFn, stop_on_error: bool = True) -> StageResult:
        desired = organizations.desired(self.cfg)
        actual = organizations.actual(self.client, self.cfg)
        changes = diff(
            organizations.resource_type,
            desired,
            actual,
            organizations.COMPARABLE_FIELDS,
            unmanaged_context_fn=organizations.context_for_key,
        )
        for ch in changes:
            self._execute(ch, decide(ch), organizations, stop_on_error)
        self.org_ids = {name: rec.id for name, rec in organizations.actual(self.client, self.cfg).items()}
        return StageResult("organization", changes)

    # -- stage 2: spaces (fan-out) --------------------------------------------

    def run_spaces(self, decide: DecideFn, stop_on_error: bool = True) -> StageResult:
        desired = spaces.desired(self.cfg)
        actual = spaces.actual(self.client, self.cfg, self.org_ids)
        changes = diff(
            spaces.resource_type,
            desired,
            actual,
            spaces.COMPARABLE_FIELDS,
            unmanaged_context_fn=spaces.context_for_key,
        )
        pending = 0
        for ch in changes:
            org_name = ch.context.get("org")
            if org_name not in self.org_ids:
                ch.pending_reason = f"org '{org_name}' does not exist yet"
                pending += 1
                self._execute(ch, "skip", spaces, stop_on_error)
                continue
            self._execute(ch, decide(ch), spaces, stop_on_error, extra_create_arg=self.org_ids.get(org_name))
        self.space_ids = {
            key: rec.id for key, rec in spaces.actual(self.client, self.cfg, self.org_ids).items()
        }
        note = f"{pending} space(s) pending until their org is created" if pending else ""
        return StageResult("space", changes, pending_count=pending, pending_note=note)

    # -- stage 3: providers (derived) -----------------------------------------

    def run_providers(self, decide: DecideFn, stop_on_error: bool = True) -> StageResult:
        total_pairs = len(self.cfg.space_org_pairs())
        desired = providers.desired(self.cfg, self.org_ids, self.space_ids)
        actual = providers.actual(self.client, self.cfg)
        changes = diff(
            providers.resource_type,
            desired,
            actual,
            providers.COMPARABLE_FIELDS,
            supports_pull=providers.supports_pull,
        )
        for ch in changes:
            self._execute(ch, decide(ch), providers, stop_on_error)
        pending = total_pairs - len(desired)
        note = f"{pending} provider(s) pending until their (org, space) exist" if pending else ""
        return StageResult("provider", changes, pending_count=pending, pending_note=note)

    # -- stage 4: service keys (derived) --------------------------------------

    def run_service_keys(self, decide: DecideFn, stop_on_error: bool = True) -> tuple[StageResult, list[tuple[str, object]]]:
        total_pairs = len(self.cfg.space_org_pairs())
        desired = service_keys.desired(self.cfg, self.org_ids, self.space_ids)
        actual = service_keys.actual(self.client, self.cfg)
        changes = diff(
            service_keys.resource_type,
            desired,
            actual,
            service_keys.COMPARABLE_FIELDS,
            supports_pull=service_keys.supports_pull,
        )
        written: list[tuple[str, object]] = []
        for ch in changes:
            decision = decide(ch)
            ch.decision = decision
            if decision == "abort":
                raise AbortRun()
            if decision != "push" or ch.kind != "add":
                ch.result = "skipped" if decision != "push" else "skipped"
                continue
            try:
                _actual_rec, secret = service_keys.create(self.client, ch.desired)
                path = write_secret(self.instance_name, ch.key, secret)
                written.append((ch.key, path))
                ch.result = "pushed"
            except Exception as e:  # noqa: BLE001
                ch.result = "error"
                ch.error = str(e)
                if stop_on_error:
                    raise
        pending = total_pairs - len(desired)
        note = f"{pending} service key(s) pending until their (org, space) exist" if pending else ""
        return StageResult("service_key", changes, pending_count=pending, pending_note=note), written

    # -- convenience: run everything read-only (plan / diff --check) ---------

    def run_all_readonly(self) -> RunSummary:
        def never(_ch: Change) -> Decision:
            return "skip"

        summary = RunSummary()
        summary.stages.append(self.run_organizations(never, stop_on_error=False))
        summary.stages.append(self.run_spaces(never, stop_on_error=False))
        summary.stages.append(self.run_providers(never, stop_on_error=False))
        sk_stage, _ = self.run_service_keys(never, stop_on_error=False)
        summary.stages.append(sk_stage)
        return summary
