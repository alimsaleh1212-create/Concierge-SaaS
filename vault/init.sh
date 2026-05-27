#!/bin/sh
# Idempotent Vault + MinIO bootstrap — runs once on `docker compose up` via vault-init service.
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
    ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set in .env}" \
    VOYAGE_API_KEY="${VOYAGE_API_KEY:?VOYAGE_API_KEY must be set in .env}"

  echo "[vault-init] Secrets written."
fi

# Create MinIO buckets (idempotent — mc mb --ignore-existing)
echo "[vault-init] Configuring MinIO buckets..."

# Install mc if not present
if ! command -v mc > /dev/null 2>&1; then
  echo "[vault-init] Downloading MinIO client..."
  wget -q "https://dl.min.io/client/mc/release/linux-amd64/mc" -O /usr/local/bin/mc
  chmod +x /usr/local/bin/mc
fi

MINIO_HOST="${MINIO_ROOT_USER:-minioadmin}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-minioadmin}"

mc alias set local http://minio:9000 "$MINIO_HOST" "$MINIO_PASS" --api S3v4 > /dev/null 2>&1

mc mb --ignore-existing local/concierge-widget
mc mb --ignore-existing local/concierge-cms

echo "[vault-init] MinIO buckets ready."
echo "[vault-init] Bootstrap complete."
