#!/bin/sh
set -eu

mc alias set local http://minio:9000 "$ORDERFLOW_INFRA_MINIO_ROOT_USER" "$ORDERFLOW_INFRA_MINIO_ROOT_PASSWORD"
mc mb --ignore-existing "local/$ORDERFLOW_INFRA_DOCUMENTS_BUCKET"
mc anonymous set private "local/$ORDERFLOW_INFRA_DOCUMENTS_BUCKET"

echo "MinIO bucket bootstrap completed: $ORDERFLOW_INFRA_DOCUMENTS_BUCKET"
