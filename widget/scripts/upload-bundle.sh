#!/usr/bin/env bash
set -euo pipefail

MINIO_ALIAS=${MINIO_ALIAS:-minio}
MINIO_ENDPOINT=${MINIO_ENDPOINT:-http://minio:9000}
MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
MINIO_BUCKET=${MINIO_BUCKET:-concierge-widget}

if ! command -v mc >/dev/null 2>&1; then
  echo "MinIO client (mc) is required to upload the widget bundle." >&2
  exit 1
fi

mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" >/dev/null
mc mb --ignore-existing "${MINIO_ALIAS}/${MINIO_BUCKET}" >/dev/null
mc cp --attr "Cache-Control=public,max-age=31536000" dist/index.js "${MINIO_ALIAS}/${MINIO_BUCKET}/index.js"
