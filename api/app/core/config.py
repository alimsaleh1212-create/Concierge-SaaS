import logging
import os

import hvac
from functools import lru_cache
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# config.py lives at api/app/core/config.py — walk up three levels to reach repo root
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_ENV_FILE = os.path.join(_REPO_ROOT, ".env")


class Settings(BaseSettings):
    # Set DEV_MODE=true in .env to skip Vault entirely (local dev only)
    DEV_MODE: bool = False

    # Supplied by user via .env — everything else comes from Vault
    VAULT_ADDR: str = "http://vault:8200"
    VAULT_ROOT_TOKEN: str = ""
    ANTHROPIC_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""

    # Populated from Vault at startup (or from .env when DEV_MODE=true)
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    MINIO_ENDPOINT: str = ""
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MODELSERVER_SERVICE_TOKEN: str = "dev-modelserver-token"
    GUARDRAILS_SERVICE_TOKEN: str = "dev-guardrails-token"
    JWT_SECRET: str = ""

    class Config:
        env_file = _ENV_FILE
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    if settings.DEV_MODE:
        logger.warning("DEV_MODE=true — Vault skipped, reading secrets from .env")
    else:
        _load_vault_secrets(settings)
    return settings


def _load_vault_secrets(settings: Settings) -> None:
    client = hvac.Client(url=settings.VAULT_ADDR, token=settings.VAULT_ROOT_TOKEN)
    secret = client.secrets.kv.v2.read_secret_version(
        path="concierge", mount_point="secret"
    )
    data: dict = secret["data"]["data"]

    settings.DATABASE_URL = data["DATABASE_URL"]
    settings.REDIS_URL = data["REDIS_URL"]
    settings.MINIO_ENDPOINT = data["MINIO_ENDPOINT"]
    settings.MINIO_ACCESS_KEY = data["MINIO_ACCESS_KEY"]
    settings.MINIO_SECRET_KEY = data["MINIO_SECRET_KEY"]
    settings.MODELSERVER_SERVICE_TOKEN = data["MODELSERVER_SERVICE_TOKEN"]
    settings.GUARDRAILS_SERVICE_TOKEN = data["GUARDRAILS_SERVICE_TOKEN"]
    settings.JWT_SECRET = data["JWT_SECRET"]
