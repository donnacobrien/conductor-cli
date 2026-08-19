"""Organizations: GET/POST /v2/organizations, GET/PATCH /v2/organizations/{id}.

Matched by name (unique per account). Supports pull (rewrites orgs.yaml).
"""

from __future__ import annotations

from ..config.loader import InstanceConfig
from ..http import ArizeClient
from ..yaml_io import read_yaml, write_yaml
from .base import ActualRecord, DesiredRecord

resource_type = "organization"
COMPARABLE_FIELDS: tuple[str, ...] = ("description",)
supports_pull = True


def context_for_key(key: str) -> dict:
    return {"org": key}


def desired(cfg: InstanceConfig) -> dict[str, DesiredRecord]:
    out: dict[str, DesiredRecord] = {}
    for name, loaded in cfg.orgs.items():
        org = loaded.value
        out[name] = DesiredRecord(
            key=name,
            fields={"description": org.description},
            payload={"name": org.name, "description": org.description},
            context={"org": name},
            source_file=loaded.source_file,
        )
    return out


def actual(client: ArizeClient, cfg: InstanceConfig) -> dict[str, ActualRecord]:
    out: dict[str, ActualRecord] = {}
    for item in client.paginate(
        "/v2/organizations", item_key="organizations", context={"resource": resource_type}
    ):
        out[item["name"]] = ActualRecord(
            key=item["name"],
            id=item["id"],
            fields={"description": item.get("description") or ""},
            raw=item,
        )
    return out


def create(client: ArizeClient, record: DesiredRecord) -> ActualRecord:
    resp = client.post("/v2/organizations", json=record.payload, context=record.context)
    return ActualRecord(
        key=record.key,
        id=resp["id"],
        fields={"description": resp.get("description") or ""},
        raw=resp,
    )


def update(
    client: ArizeClient,
    actual_record: ActualRecord,
    record: DesiredRecord,
    changed: set[str],
) -> ActualRecord:
    payload: dict = {}
    if "description" in changed:
        payload["description"] = record.fields["description"]
    resp = client.patch(
        f"/v2/organizations/{actual_record.id}", json=payload, context=record.context
    )
    return ActualRecord(
        key=record.key,
        id=resp["id"],
        fields={"description": resp.get("description") or ""},
        raw=resp,
    )


def pull(cfg: InstanceConfig, key: str, actual_record: ActualRecord) -> None:
    data = read_yaml(cfg.orgs_file) or {}
    orgs_list = data.get("organizations") or []
    for entry in orgs_list:
        if entry.get("name") == key:
            entry["description"] = actual_record.fields["description"]
            break
    else:
        orgs_list.append({"name": key, "description": actual_record.fields["description"]})
    data["organizations"] = orgs_list
    write_yaml(cfg.orgs_file, data)
