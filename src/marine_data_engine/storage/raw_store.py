"""Raw immutable object storage.

Raw source bytes are stored write-once under a deterministic key:

    {provider}/{dataset}/{yyyy}/{mm}/{dd}/{checksum}.{ext}

Each object records its checksum so re-ingestion of identical bytes is a no-op
(idempotent). Two backends are provided:

- :class:`InMemoryRawStore` — deterministic, dependency-free, used in tests and
  when ``MDE_S3_IN_MEMORY`` is set.
- :class:`S3RawStore` — MinIO/S3 via boto3 (optional dependency).

Immutability is enforced at the application layer: an existing key is never
overwritten; identical content is treated as already-stored.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Metadata describing a stored raw object."""

    uri: str
    key: str
    bucket: str
    checksum_sha256: str
    size_bytes: int
    media_type: str | None
    retrieved_at: datetime
    already_existed: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_key(provider: str, dataset: str, checksum: str, ext: str, when: datetime) -> str:
    """Build a deterministic, content-addressed storage key.

    C7 fix: uses hash-prefix partitioning instead of date partitioning so
    identical content always maps to the same key regardless of ingestion date,
    enabling correct cross-day deduplication.
    """
    ext = ext.lstrip(".")
    return (
        f"{provider.lower()}/{dataset.lower()}/"
        f"{checksum[:2]}/{checksum[2:4]}/{checksum}.{ext}"
    )


class RawStore(Protocol):
    """Interface for immutable raw storage backends."""

    bucket: str

    def put(
        self,
        *,
        provider: str,
        dataset: str,
        data: bytes,
        ext: str,
        media_type: str | None = None,
        when: datetime | None = None,
    ) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class InMemoryRawStore:
    """In-process, deterministic raw store for tests/local use."""

    def __init__(self, bucket: str = "marine-raw") -> None:
        self.bucket = bucket
        self._objects: dict[str, bytes] = {}
        self._meta: dict[str, tuple[str, str | None]] = {}

    def put(
        self,
        *,
        provider: str,
        dataset: str,
        data: bytes,
        ext: str,
        media_type: str | None = None,
        when: datetime | None = None,
    ) -> StoredObject:
        when = when or datetime.now(tz=UTC)
        checksum = _sha256(data)
        key = build_key(provider, dataset, checksum, ext, when)
        already = key in self._objects
        if not already:
            self._objects[key] = data
            self._meta[key] = (checksum, media_type)
        return StoredObject(
            uri=f"s3://{self.bucket}/{key}",
            key=key,
            bucket=self.bucket,
            checksum_sha256=checksum,
            size_bytes=len(data),
            media_type=media_type,
            retrieved_at=when,
            already_existed=already,
        )

    def get(self, key: str) -> bytes:
        return self._objects[key]

    def exists(self, key: str) -> bool:
        return key in self._objects


class S3RawStore:
    """MinIO/S3-backed raw store using boto3 (optional dependency).

    Immutability is enforced by checking object existence before writing;
    identical checksummed content is never rewritten.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        try:
            import boto3  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - exercised only w/o extra
            raise RuntimeError(
                "boto3 is required for S3RawStore; install the 'storage' extra."
            ) from exc
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def _head(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            # H3 fix: only treat 404-like errors as "not found".
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise  # Re-raise 403, 500, throttling, etc.

    def put(
        self,
        *,
        provider: str,
        dataset: str,
        data: bytes,
        ext: str,
        media_type: str | None = None,
        when: datetime | None = None,
    ) -> StoredObject:
        when = when or datetime.now(tz=UTC)
        checksum = _sha256(data)
        key = build_key(provider, dataset, checksum, ext, when)
        already = self._head(key)
        if not already:
            import base64  # noqa: PLC0415
            sha256_b64 = base64.b64encode(bytes.fromhex(checksum)).decode("ascii")
            extra = {"ContentType": media_type} if media_type else {}
            # H5 fix: enforce write-time integrity verification.
            self._client.put_object(
                Bucket=self.bucket, Key=key, Body=data,
                ChecksumSHA256=sha256_b64, **extra,
            )
        return StoredObject(
            uri=f"s3://{self.bucket}/{key}",
            key=key,
            bucket=self.bucket,
            checksum_sha256=checksum,
            size_bytes=len(data),
            media_type=media_type,
            retrieved_at=when,
            already_existed=already,
        )

    def get(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        return self._head(key)


def build_raw_store() -> RawStore:
    """Construct a raw store from settings (in-memory when configured)."""
    from ..config import get_settings

    s = get_settings().object_store
    if s.in_memory or s.endpoint_url is None:
        return InMemoryRawStore(bucket=s.raw_bucket)
    return S3RawStore(
        bucket=s.raw_bucket,
        endpoint_url=s.endpoint_url,
        region=s.region,
        access_key=s.access_key,
        secret_key=s.secret_key,
    )
