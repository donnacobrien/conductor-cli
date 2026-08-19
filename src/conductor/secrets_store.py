"""Where a freshly-created service key's one-time secret gets written.

Never stored in the repo's tracked YAML — `.conductor/secrets/` is
gitignored. This is a stopgap, loudly labeled as such; move keys to a real
secret manager.
"""

from __future__ import annotations

from pathlib import Path

SECRETS_ROOT = Path(".conductor/secrets")


def write_secret(instance_name: str, key_name: str, secret: str) -> Path:
    path = SECRETS_ROOT / instance_name / f"{key_name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path
