"""Resolves an instance's API key from the environment.

Each instance's key comes from a local `.env` file (gitignored; see
`.env.example`), loaded via python-dotenv. `instances.yaml` names the
variable to read via `api_key_env` (e.g. `ARIZE_PROD_API_KEY`).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from .config.schema import Instance

_dotenv_loaded = False


def _ensure_dotenv_loaded() -> None:
    global _dotenv_loaded
    if not _dotenv_loaded:
        load_dotenv()
        _dotenv_loaded = True


class MissingApiKeyError(Exception):
    def __init__(self, instance: Instance) -> None:
        self.instance = instance
        super().__init__(
            f"environment variable '{instance.api_key_env}' is not set "
            f"(required for instance '{instance.name}'). Copy .env.example to "
            f".env and fill it in, or export it directly."
        )


def resolve_api_key(instance: Instance) -> str:
    _ensure_dotenv_loaded()
    key = os.environ.get(instance.api_key_env)
    if not key:
        raise MissingApiKeyError(instance)
    return key
