"""AI integrations ("providers"): GET/POST /v2/ai-integrations, GET/PATCH
/v2/ai-integrations/{id}.

NOT YAML-authored. Whenever a space is onboarded to an org (i.e. that
(space, org) pair exists on the platform), conductor derives exactly one
VERTEX_AI provider from a fixed built-in template — the space's own fields
plus the org's GCP project (via gcp_projects.yaml). See the plan doc for the
exact template. Not configurable in v1.

Only resolvable once both the org and the space it belongs to already exist
on the platform (their live ids are required for `scopings`); pairs that
aren't resolvable yet are simply left out of `desired()` for this run —
plan.py surfaces how many are pending so that's not silent.
"""

from __future__ import annotations

from ..config.loader import InstanceConfig
from ..http import ArizeClient
from .base import ActualRecord, DesiredRecord
from .spaces import make_key as space_key

resource_type = "provider"
COMPARABLE_FIELDS: tuple[str, ...] = ("project_id", "location")
supports_pull = False


def _provider_name(org: str, space: str) -> str:
    return f"{space}-{org}"


def desired(
    cfg: InstanceConfig,
    org_ids: dict[str, str],
    space_ids: dict[str, str],
) -> dict[str, DesiredRecord]:
    out: dict[str, DesiredRecord] = {}
    for loaded_space, org_name in cfg.space_org_pairs():
        s = loaded_space.value
        org_id = org_ids.get(org_name)
        sp_id = space_ids.get(space_key(org_name, s.name))
        if org_id is None or sp_id is None:
            continue  # org/space not created yet; pending, see plan.py
        name = _provider_name(org_name, s.name)
        project_id = cfg.project_id_for_org(org_name)
        out[name] = DesiredRecord(
            key=name,
            fields={"project_id": project_id, "location": s.location},
            payload={
                "name": name,
                "provider": "VERTEX_AI",
                "provider_metadata": {
                    "kind": "GCP",
                    "project_id": project_id,
                    "location": s.location,
                    "project_access_label": f"{org_name}/{s.name}",
                },
                "scopings": [{"organization_id": org_id, "space_id": sp_id}],
            },
            context={"org": org_name, "space": s.name},
        )
    return out


def actual(client: ArizeClient, cfg: InstanceConfig) -> dict[str, ActualRecord]:
    out: dict[str, ActualRecord] = {}
    for item in client.paginate(
        "/v2/ai-integrations", item_key="ai_integrations", context={"resource": resource_type}
    ):
        meta = item.get("provider_metadata") or {}
        out[item["name"]] = ActualRecord(
            key=item["name"],
            id=item["id"],
            fields={
                "project_id": meta.get("project_id"),
                "location": meta.get("location"),
            },
            raw=item,
        )
    return out


def create(client: ArizeClient, record: DesiredRecord) -> ActualRecord:
    resp = client.post("/v2/ai-integrations", json=record.payload, context=record.context)
    meta = resp.get("provider_metadata") or {}
    return ActualRecord(
        key=record.key,
        id=resp["id"],
        fields={"project_id": meta.get("project_id"), "location": meta.get("location")},
        raw=resp,
    )


def update(
    client: ArizeClient,
    actual_record: ActualRecord,
    record: DesiredRecord,
    changed: set[str],
) -> ActualRecord:
    # provider_metadata is replaced wholesale, not patched per sub-field
    resp = client.patch(
        f"/v2/ai-integrations/{actual_record.id}",
        json={"provider_metadata": record.payload["provider_metadata"]},
        context=record.context,
    )
    meta = resp.get("provider_metadata") or {}
    return ActualRecord(
        key=record.key,
        id=resp["id"],
        fields={"project_id": meta.get("project_id"), "location": meta.get("location")},
        raw=resp,
    )
