import hvac
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supplied by user via .env — used only to bootstrap Vault connection
    VAULT_ADDR: str = "http://vault:8200"
    VAULT_ROOT_TOKEN: str

    # Populated from Vault at startup — defaults are empty; will raise if Vault unreachable
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    MINIO_ENDPOINT: str = ""
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MODELSERVER_BASE_URL: str = "http://modelserver:8001"
    GUARDRAILS_BASE_URL: str = "http://guardrails:8002"
    MODELSERVER_SERVICE_TOKEN: str = ""
    GUARDRAILS_SERVICE_TOKEN: str = ""
    JWT_SECRET: str = ""
    ANTHROPIC_API_KEY: str = ""
    VOYAGE_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
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
    settings.ANTHROPIC_API_KEY = data["ANTHROPIC_API_KEY"]
    settings.VOYAGE_API_KEY = data["VOYAGE_API_KEY"]
