#!/bin/sh
# Idempotent Vault bootstrap (MinIO buckets are created by the minio-init service) — runs once on `docker compose up` via vault-init service.
# Exits 0 on success. Safe to re-run; skips secrets that already exist.
set -e

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-dev-root-token}"

echo "[vault-init] Waiting for Vault to be ready..."
until vault status -address="$VAULT_ADDR" > /dev/null 2>&1; do
  sleep 1
done

echo "[vault-init] Vault is ready. Checking if secrets already exist..."

# Check idempotency — skip if concierge secret already written
if vault kv get -address="$VAULT_ADDR" -mount=secret concierge > /dev/null 2>&1; then
  echo "[vault-init] Secrets already exist — skipping write."
else
  echo "[vault-init] Writing secrets to Vault..."

  vault kv put -address="$VAULT_ADDR" secret/concierge \
    DATABASE_URL="postgresql+asyncpg://concierge:concierge@postgres:5432/concierge" \
    REDIS_URL="redis://redis:6379/0" \
    MINIO_ENDPOINT="minio:9000" \
    MINIO_ACCESS_KEY="${MINIO_ROOT_USER:-minioadmin}" \
    MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD:-minioadmin}" \
    MODELSERVER_SERVICE_TOKEN="$(cat /dev/urandom | head -c 32 | base64 | tr -d '=+/' | head -c 43)" \
    GUARDRAILS_SERVICE_TOKEN="$(cat /dev/urandom | head -c 32 | base64 | tr -d '=+/' | head -c 43)" \
    JWT_SECRET="$(cat /dev/urandom | head -c 48 | base64 | tr -d '=+/' | head -c 64)" \
    GROQ_API_KEY="${GROQ_API_KEY:?GROQ_API_KEY must be set in .env}" \
    VOYAGE_API_KEY="${VOYAGE_API_KEY:?VOYAGE_API_KEY must be set in .env}"

  echo "[vault-init] Secrets written."
fi

echo "[vault-init] Bootstrap complete."
