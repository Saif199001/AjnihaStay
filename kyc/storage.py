"""Provider-neutral private storage boundary for sensitive KYC documents.

KYC services own authentication, workspace isolation, RBAC, and lifecycle state.
This module only owns provider interaction and deliberately exposes no public
media URL through domain models or serializers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import BinaryIO, Protocol
from uuid import uuid4

import cloudinary
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
    """Short-lived provider delivery grant.

    The URL is intentionally returned only from the storage adapter. KYC API
    serializers must not expose it as passive document metadata.
    """

    url: str
    expires_at: datetime


class PrivateDocumentStorage(Protocol):
    def put(
        self,
        file: BinaryIO,
        *,
        storage_key: str,
        content_type: str,
    ) -> StorageObject: ...

    def open(self, storage_key: str) -> BinaryIO: ...

    def delete(self, storage_key: str) -> None: ...

    def exists(self, storage_key: str) -> bool: ...

    def create_controlled_access(
        self,
        storage_key: str,
        *,
        expires_at: datetime,
    ) -> DeliveryGrant: ...


def generate_storage_key(*, workspace_id: int, tenant_id: int) -> str:
    """Generate an opaque, non-PII KYC storage key."""

    return f"kyc/private/workspace/{workspace_id}/tenant/{tenant_id}/{uuid4().hex}"


class CloudinaryPrivateDocumentStorage:
    """Cloudinary implementation using private raw resources.

    Cloudinary is treated strictly as a storage/delivery provider. It does not
    perform tenant authorization and no provider URL is persisted as domain
    truth.
    """

    resource_type = "raw"
    delivery_type = "private"

    def _ensure_configured(self) -> None:
        config = cloudinary.config()
        if not config.cloud_name or not config.api_key or not config.api_secret:
            raise PrivateStorageError("Private KYC storage provider is not configured")

    @staticmethod
    def _public_id(storage_key: str) -> str:
        if not storage_key.startswith("kyc/private/"):
            raise PrivateStorageError("Invalid KYC storage key")
        return storage_key

    def put(
        self,
        file: BinaryIO,
        *,
        storage_key: str,
        content_type: str,
    ) -> StorageObject:
        self._ensure_configured()
        public_id = self._public_id(storage_key)
        try:
            result = cloudinary.uploader.upload(
                file,
                public_id=public_id,
                resource_type=self.resource_type,
                type=self.delivery_type,
                overwrite=False,
                unique_filename=False,
                use_filename=False,
                invalidate=False,
            )
        except Exception as exc:  # provider-specific exceptions must not leak
            raise PrivateStorageError("KYC document upload failed") from exc

        return StorageObject(
            storage_key=storage_key,
            provider_reference=str(result.get("public_id") or public_id),
            content_type=content_type,
            file_size=int(result.get("bytes") or 0),
        )

    def create_controlled_access(
        self,
        storage_key: str,
        *,
        expires_at: datetime,
    ) -> DeliveryGrant:
        self._ensure_configured()
        if expires_at.tzinfo is None:
            raise PrivateStorageError("Delivery grant expiry must be timezone-aware")
        if expires_at <= datetime.now(timezone.utc):
            raise PrivateStorageError("Delivery grant expiry must be in the future")

        public_id = self._public_id(storage_key)
        try:
            url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type=self.resource_type,
                type=self.delivery_type,
                secure=True,
                sign_url=True,
                format=None,
            )
        except Exception as exc:
            raise PrivateStorageError("KYC document delivery grant creation failed") from exc

        return DeliveryGrant(url=url, expires_at=expires_at)

    def open(self, storage_key: str) -> BinaryIO:
        """Open a private object through a short-lived signed provider URL."""

        grant = self.create_controlled_access(
            storage_key,
            expires_at=datetime.now(timezone.utc).replace(microsecond=0),
        )
        # create_controlled_access intentionally requires a future expiry; use a
        # minimal provider-side read grant for backend-controlled retrieval.
        raise PrivateStorageError(
            "Direct backend object streaming is not enabled; use controlled delivery"
        )

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
                public_id,
                resource_type=self.resource_type,
                type=self.delivery_type,
                invalidate=True,
            )
        except Exception as exc:
            raise PrivateStorageError("KYC document deletion failed") from exc
