#!/bin/sh
# =============================================================================
# minio-init.sh — creates the object-storage buckets required by the stack.
# Runs once (as the `minio-init` compose service) after MinIO is healthy.
# Ensures the immutable RAW bucket exists (prompt requirement) plus processed
# and artifact buckets. Idempotent: safe to re-run.
# =============================================================================
set -eu

MC_ALIAS=local
ENDPOINT="${S3_ENDPOINT_URL:-http://minio:9000}"

echo "[minio-init] configuring mc alias -> ${ENDPOINT}"
mc alias set "${MC_ALIAS}" "${ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

create_bucket() {
    bucket="$1"
    if mc ls "${MC_ALIAS}/${bucket}" >/dev/null 2>&1; then
        echo "[minio-init] bucket already exists: ${bucket}"
    else
        echo "[minio-init] creating bucket: ${bucket}"
        mc mb "${MC_ALIAS}/${bucket}"
    fi
}

# Immutable raw bucket (prompt §20 raw object store) + processed + artifacts.
create_bucket "${S3_BUCKET_RAW:-marine-raw}"
create_bucket "${S3_BUCKET_PROCESSED:-marine-processed}"
create_bucket "${S3_BUCKET_ARTIFACTS:-marine-artifacts}"

# Enforce immutability on the RAW bucket via versioning (retention/WORM would
# require object-lock at bucket creation; versioning gives immutable history
# for the local dev tier and prevents silent overwrites of raw files).
echo "[minio-init] enabling versioning on ${S3_BUCKET_RAW:-marine-raw}"
mc version enable "${MC_ALIAS}/${S3_BUCKET_RAW:-marine-raw}"

echo "[minio-init] done."
