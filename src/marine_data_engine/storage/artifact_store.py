from __future__ import annotations

from typing import Protocol


class ArtifactStore(Protocol):
    bucket: str

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...


class S3ArtifactStore:
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        import boto3

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


class InMemoryArtifactStore:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._objects[key] = data

    def get(self, key: str) -> bytes:
        return self._objects[key]


def build_artifact_store() -> ArtifactStore:
    from ..config import get_settings

    settings = get_settings().object_store
    if settings.in_memory or settings.endpoint_url is None:
        return InMemoryArtifactStore(bucket=settings.artifact_bucket)
    return S3ArtifactStore(
        bucket=settings.artifact_bucket,
        endpoint_url=settings.endpoint_url,
        region=settings.region,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
    )
