from typing import Protocol


class ProcessedStore(Protocol):
    bucket: str
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...

class S3ProcessedStore:
    def __init__(self, bucket: str, endpoint_url: str | None, region: str, access_key: str, secret_key: str) -> None:
        import boto3
        self.bucket = bucket
        self._client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region, aws_access_key_id=access_key, aws_secret_access_key=secret_key)

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

class InMemoryProcessedStore:
    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._objects[key] = data

    def get(self, key: str) -> bytes:
        return self._objects[key]

def build_processed_store() -> ProcessedStore:
    from ..config import get_settings
    s = get_settings().object_store
    if s.in_memory or s.endpoint_url is None:
        return InMemoryProcessedStore(bucket=s.processed_bucket)
    return S3ProcessedStore(bucket=s.processed_bucket, endpoint_url=s.endpoint_url, region=s.region, access_key=s.access_key, secret_key=s.secret_key)
