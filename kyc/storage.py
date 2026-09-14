"""Provider-neutral private storage boundary for sensitive KYC documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import re
from typing import BinaryIO, Protocol
from uuid import uuid4

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
import requests


class PrivateStorageError(Exception):
    """Provider-neutral storage failure."""


@dataclass(frozen=True)
class StorageObject:
    storage_key: str
    provider_reference: str
    content_type: str
    file_size: int


@dataclass(frozen=True)
class DeliveryGrant:
    """Short-lived provider delivery grant."""

    url: str
    expires_at: datetime


_STORAGE_KEY_PATTERN = re.compile(
    r"^kyc/private/workspace/[1-9][0-9]*/tenant/[1-9][0-9]*/[0-9a-f]{32}$"
)
_MAX_DELIVERY_GRANT = timedelta(minutes=15)


def generate_storage_key(*, workspace_id: int, tenant_id: int) -> str:
    """Generate a unique, provider-neutral KYC storage key."""
    if workspace_id <= 0 or tenant_id <= 0:
        raise PrivateStorageError("Workspace and tenant identifiers must be positive")
    return f"kyc/private/workspace/{workspace_id}/tenant/{tenant_id}/{uuid4().hex}"


def _validate_storage_key(storage_key: str) -> str:
    if not isinstance(storage_key, str) or not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
        raise PrivateStorageError("Invalid KYC storage key")
    return storage_key


class PrivateDocumentStorage(Protocol):
    def put(self, file: BinaryIO, *, storage_key: str, content_type: str) -> StorageObject: ...
    def open(self, storage_key: str) -> BinaryIO: ...
    def delete(self, storage_key: str) -> None: ...
    def exists(self, storage_key: str) -> bool: ...
    def create_controlled_access(self, storage_key: str, *, expires_at: datetime) -> DeliveryGrant: ...


class CloudinaryPrivateDocumentStorage:
    """Cloudinary implementation using private raw resources."""

    resource_type = "raw"
    delivery_type = "private"

    def _ensure_configured(self) -> None:
        config = cloudinary.config()
        if not config.cloud_name or not config.api_key or not config.api_secret:
            raise PrivateStorageError("Private KYC storage provider is not configured")

    @staticmethod
    def _public_id(storage_key: str) -> str:
        return _validate_storage_key(storage_key)

    def put(self, file: BinaryIO, *, storage_key: str, content_type: str) -> StorageObject:
        self._ensure_configured()
        if not isinstance(content_type, str) or not content_type.strip():
            raise PrivateStorageError("KYC document content type is required")
        public_id = self._public_id(storage_key)
        try:
            result = cloudinary.uploader.upload(
                file, public_id=public_id, resource_type=self.resource_type,
                type=self.delivery_type, overwrite=False, unique_filename=False,
                use_filename=False, invalidate=False,
            )
        except Exception as exc:
            raise PrivateStorageError("KYC document upload failed") from exc
        return StorageObject(
            storage_key=storage_key,
            provider_reference=str(result.get("public_id") or public_id),
            content_type=content_type,
            file_size=int(result.get("bytes") or 0),
        )

    def create_controlled_access(self, storage_key: str, *, expires_at: datetime) -> DeliveryGrant:
        self._ensure_configured()
        if expires_at.tzinfo is None:
            raise PrivateStorageError("Delivery grant expiry must be timezone-aware")
        now = datetime.now(timezone.utc)
        if expires_at <= now:
            raise PrivateStorageError("Delivery grant expiry must be in the future")
        if expires_at - now > _MAX_DELIVERY_GRANT:
            raise PrivateStorageError("Delivery grant expiry exceeds the maximum lifetime")
        public_id = self._public_id(storage_key)
        try:
            url = cloudinary.utils.private_download_url(
                public_id, "", resource_type=self.resource_type, type=self.delivery_type,
                expires_at=int(expires_at.timestamp()), attachment=False,
            )
        except Exception as exc:
            raise PrivateStorageError("KYC document delivery grant creation failed") from exc
        return DeliveryGrant(url=url, expires_at=expires_at)

    def open(self, storage_key: str) -> BinaryIO:
        grant = self.create_controlled_access(
            storage_key, expires_at=datetime.now(timezone.utc) + timedelta(minutes=1)
        )
        try:
            response = requests.get(grant.url, timeout=30, allow_redirects=False)
            response.raise_for_status()
        except Exception as exc:
            raise PrivateStorageError("KYC document retrieval failed") from exc
        return BytesIO(response.content)

    def exists(self, storage_key: str) -> bool:
        self._ensure_configured()
        public_id = self._public_id(storage_key)
        try:
            cloudinary.api.resource(public_id, resource_type=self.resource_type, type=self.delivery_type)
            return True
        except Exception:
            return False

    def delete(self, storage_key: str) -> None:
        self._ensure_configured()
        public_id = self._public_id(storage_key)
        try:
            cloudinary.uploader.destroy(
                public_id, resource_type=self.resource_type, type=self.delivery_type, invalidate=True
            )
        except Exception as exc:
            raise PrivateStorageError("KYC document deletion failed") from exc
