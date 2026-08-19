"""Service API keys: GET/POST /v2/api-keys, POST .../revoke, POST .../refresh.

NOT YAML-authored — same derivation pattern as providers.py: one SERVICE key
per (space, org) pair that already exists on the platform, from the fixed
built-in template. No update path (the API has no PATCH for keys; scoping/
role aren't even returned by list/get, so there's nothing to diff besides
existence) — a REVOKED key is treated as absent (shows up as `add` again,
i.e. needs a replacement, handled via `delete` + re-`apply`, never silently
"fixed").

The raw secret is returned once, on create, and is the caller's
responsibility to persist (see commands/apply_cmd.py / diff_cmd.py, which
write it to .conductor/secrets/<instance>/<key-name>.txt).
"""

from __future__ import annotations

from ..config.loader import InstanceConfig
from ..http import ArizeClient
from .base import ActualRecord, DesiredRecord
from .spaces import make_key as space_key

resource_type = "service_key"
COMPARABLE_FIELDS: tuple[str, ...] = ()  # existence-only; see module docstring
supports_pull = False


def _key_name(org: str, space: str) -> str:
    return f"{space}-{org}-svc"


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
        name = _key_name(org_name, s.name)
        out[name] = DesiredRecord(
            key=name,
            fields={},
            payload={
                "key_type": "SERVICE",
                "name": name,
                "description": f"Auto-provisioned service key for {s.name} in {org_name}",
                "organizations": [{"org_id": org_id, "spaces": [{"space_id": sp_id}]}],
            },
            context={"org": org_name, "space": s.name},
        )
    return out


def actual(client: ArizeClient, cfg: InstanceConfig) -> dict[str, ActualRecord]:
    out: dict[str, ActualRecord] = {}
    for item in client.paginate(
        "/v2/api-keys",
        item_key="api_keys",
        params={"key_type": "SERVICE"},
        context={"resource": resource_type},
    ):
        if item.get("status") != "ACTIVE":
            continue  # revoked keys don't count as "existing"
        out[item["name"]] = ActualRecord(key=item["name"], id=item["id"], fields={}, raw=item)
    return out


def create(client: ArizeClient, record: DesiredRecord) -> tuple[ActualRecord, str]:
    """Returns (ActualRecord, raw_secret) — the secret is only ever available here."""
    resp = client.post("/v2/api-keys", json=record.payload, context=record.context)
    secret = resp["key"]
    return ActualRecord(key=record.key, id=resp["id"], fields={}, raw=resp), secret


def revoke(client: ArizeClient, actual_record: ActualRecord, context: dict) -> None:
    client.post(f"/v2/api-keys/{actual_record.id}/revoke", context=context)
