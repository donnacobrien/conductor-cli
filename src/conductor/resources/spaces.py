"""Spaces: GET/POST /v2/spaces, GET/PATCH /v2/spaces/{id}.

Fan-out semantics: a space file's `organizations:` list means the same-named
space is provisioned independently in each listed org (Arize spaces belong to
exactly one org — there's no cross-org sharing in the API). The natural key
is therefore `(org, space name)`, encoded as "{org}/{space_name}".

`create()` needs the org's live id, which may not exist yet at `desired()`
time (the org itself might be mid-creation in the same run) — so `org_id` is
passed in separately by plan.py once the organizations stage has resolved it,
rather than baked into the payload up front.
"""

from __future__ import annotations

from ..config.loader import InstanceConfig
from ..http import ArizeClient
from ..yaml_io import read_yaml, write_yaml
from .base import ActualRecord, DesiredRecord

resource_type = "space"
COMPARABLE_FIELDS: tuple[str, ...] = ("description", "is_private")
supports_pull = True


def make_key(org: str, space_name: str) -> str:
    return f"{org}/{space_name}"


def context_for_key(key: str) -> dict:
    org, space_name = key.split("/", 1)
    return {"org": org, "space": space_name}


def desired(cfg: InstanceConfig) -> dict[str, DesiredRecord]:
    out: dict[str, DesiredRecord] = {}
    for loaded_space, org_name in cfg.space_org_pairs():
        s = loaded_space.value
        key = make_key(org_name, s.name)
        out[key] = DesiredRecord(
            key=key,
            fields={"description": s.description, "is_private": s.is_private},
            payload={
                "name": s.name,
                "description": s.description,
                "is_private": s.is_private,
                # organization_id filled in by plan.py at create time
            },
            context={"org": org_name, "space": s.name},
            source_file=loaded_space.source_file,
        )
    return out


def actual(client: ArizeClient, cfg: InstanceConfig, org_ids: dict[str, str]) -> dict[str, ActualRecord]:
    out: dict[str, ActualRecord] = {}
    for org_name, org_id in org_ids.items():
        for item in client.paginate(
            "/v2/spaces",
            item_key="spaces",
            params={"organization_id": org_id},
            context={"resource": resource_type, "org": org_name},
        ):
            key = make_key(org_name, item["name"])
            out[key] = ActualRecord(
                key=key,
                id=item["id"],
                fields={
                    "description": item.get("description") or "",
                    "is_private": bool(item.get("is_private", False)),
                },
                raw=item,
            )
    return out


def create(client: ArizeClient, record: DesiredRecord, org_id: str) -> ActualRecord:
    payload = {**record.payload, "organization_id": org_id}
    resp = client.post("/v2/spaces", json=payload, context=record.context)
    return ActualRecord(
        key=record.key,
        id=resp["id"],
        fields={
            "description": resp.get("description") or "",
            "is_private": bool(resp.get("is_private", False)),
        },
        raw=resp,
    )


def update(
    client: ArizeClient,
    actual_record: ActualRecord,
    record: DesiredRecord,
    changed: set[str],
) -> ActualRecord:
    payload = {f: record.fields[f] for f in changed}
    resp = client.patch(f"/v2/spaces/{actual_record.id}", json=payload, context=record.context)
    return ActualRecord(
        key=record.key,
        id=resp["id"],
        fields={
            "description": resp.get("description") or "",
            "is_private": bool(resp.get("is_private", False)),
        },
        raw=resp,
    )


def pull(cfg: InstanceConfig, key: str, actual_record: ActualRecord) -> None:
    org_name, space_name = key.split("/", 1)
    # find which space file already declares this space (by name); if none,
    # a platform-only ("unmanaged") space has nowhere to go without the
    # operator choosing a file, so we create one named after the space.
    target_file = None
    for loaded_space in cfg.spaces:
        if loaded_space.value.name == space_name:
            target_file = loaded_space.source_file
            break
    if target_file is None:
        target_file = cfg.root / "spaces" / f"{space_name}.yaml"

    data = read_yaml(target_file) if target_file.exists() else {}
    entries = data.get("space") or []
    for entry in entries:
        if entry.get("name") == space_name:
            entry["description"] = actual_record.fields["description"]
            entry["is_private"] = actual_record.fields["is_private"]
            if org_name not in (entry.get("organizations") or []):
                entry.setdefault("organizations", []).append(org_name)
            break
    else:
        entries.append(
            {
                "name": space_name,
                "description": actual_record.fields["description"],
                "organizations": [org_name],
                "gcp_shortname": space_name,
                "location": "us-central1",
                "is_private": actual_record.fields["is_private"],
            }
        )
    data["space"] = entries
    write_yaml(target_file, data)
