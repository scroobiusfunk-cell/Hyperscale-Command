"""Object storage.

Evidence photos, document page images and export packages all live here rather
than in Postgres. The interface is small on purpose: the platform only ever puts
bytes under a key and reads them back.

Every call is logged through `external_call`, per the logging rule in CLAUDE.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from botocore.exceptions import ClientError

from app.config import Settings
from app.logging import external_call, get_logger

if TYPE_CHECKING:  # pragma: no cover
    pass

log = get_logger(__name__)


class StorageError(RuntimeError):
    """A put or get that did not happen."""


class ObjectStorage(Protocol):
    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> str: ...

    def get(self, bucket: str, key: str) -> bytes: ...

    def exists(self, bucket: str, key: str) -> bool: ...


class S3Storage(ObjectStorage):
    """S3-compatible storage. MinIO locally, S3 in deployed environments."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> S3Storage:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url or None,
            aws_access_key_id=settings.storage_access_key or None,
            aws_secret_access_key=settings.storage_secret_key or None,
            region_name=settings.storage_region,
        )
        return cls(client)

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        with external_call(
            "storage", "put", version="s3", bucket=bucket, key=key, byte_size=len(data)
        ):
            self._client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def get(self, bucket: str, key: str) -> bytes:
        # Both implementations raise StorageError for an object that is not
        # there, so a caller can tell "missing" from "broken" without knowing
        # which backend it is talking to.
        try:
            with external_call("storage", "get", version="s3", bucket=bucket, key=key) as record:
                response = self._client.get_object(Bucket=bucket, Key=key)
                body: bytes = response["Body"].read()
                record["byte_size"] = len(body)
        except ClientError as exc:
            raise StorageError(f"No object at {bucket}/{key}") from exc
        return body

    def exists(self, bucket: str, key: str) -> bool:
        try:
            with external_call("storage", "head", version="s3", bucket=bucket, key=key):
                self._client.head_object(Bucket=bucket, Key=key)
        except Exception:
            return False
        return True


class InMemoryStorage(ObjectStorage):
    """For tests, and for a developer without MinIO running."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> str:
        self.objects[(bucket, key)] = (data, content_type)
        return key

    def get(self, bucket: str, key: str) -> bytes:
        try:
            return self.objects[(bucket, key)][0]
        except KeyError as exc:
            raise StorageError(f"No object at {bucket}/{key}") from exc

    def exists(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self.objects
