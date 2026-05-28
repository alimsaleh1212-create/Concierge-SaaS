"""Configuration helpers for the guardrails sidecar."""

from __future__ import annotations

import os

import httpx


DEFAULT_VAULT_ADDR = "http://vault:8200"
VAULT_SECRET_PATH = "secret/data/concierge"
VAULT_TOKEN_FIELD = "GUARDRAILS_SERVICE_TOKEN"

_cached_vault_service_token: str | None = None
_vault_lookup_attempted = False


def reset_guardrails_service_token_cache() -> None:
    """Reset cached Vault state for tests."""
    global _cached_vault_service_token, _vault_lookup_attempted

    _cached_vault_service_token = None
    _vault_lookup_attempted = False


def get_guardrails_service_token() -> str | None:
    env_token = os.getenv(VAULT_TOKEN_FIELD)
    if env_token:
        return env_token

    return _get_guardrails_service_token_from_vault()


def _get_guardrails_service_token_from_vault() -> str | None:
    global _cached_vault_service_token, _vault_lookup_attempted

    if _vault_lookup_attempted:
        return _cached_vault_service_token

    _vault_lookup_attempted = True

    vault_root_token = os.getenv("VAULT_ROOT_TOKEN")
    if not vault_root_token:
        return None

    vault_addr = os.getenv("VAULT_ADDR", DEFAULT_VAULT_ADDR).rstrip("/")
    url = f"{vault_addr}/v1/{VAULT_SECRET_PATH}"

    try:
        response = httpx.get(
            url,
            headers={"X-Vault-Token": vault_root_token},
            timeout=2.0,
        )
        response.raise_for_status()
        token = response.json()["data"]["data"].get(VAULT_TOKEN_FIELD)
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None

    if isinstance(token, str) and token:
        _cached_vault_service_token = token
        return token

    return None
