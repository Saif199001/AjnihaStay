from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase

from kyc.storage import (
    CloudinaryPrivateDocumentStorage,
    PrivateStorageError,
    generate_storage_key,
)


class StorageKeyTests(SimpleTestCase):
    def test_generated_key_is_private_and_unique(self):
        first = generate_storage_key(workspace_id=12, tenant_id=34)
        second = generate_storage_key(workspace_id=12, tenant_id=34)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^kyc/private/workspace/12/tenant/34/[0-9a-f]{32}$")

    def test_non_positive_ids_are_rejected(self):
        with self.assertRaises(PrivateStorageError):
            generate_storage_key(workspace_id=0, tenant_id=1)
        with self.assertRaises(PrivateStorageError):
            generate_storage_key(workspace_id=1, tenant_id=0)


class CloudinaryPrivateStorageSecurityTests(SimpleTestCase):
    def setUp(self):
        self.storage = CloudinaryPrivateDocumentStorage()
        self.key = generate_storage_key(workspace_id=1, tenant_id=2)

    @patch("kyc.storage.cloudinary.config")
    def test_provider_must_be_configured(self, config):
        config.return_value.cloud_name = ""
        config.return_value.api_key = ""
        config.return_value.api_secret = ""
        with self.assertRaises(PrivateStorageError):
            self.storage.create_controlled_access(
                self.key, expires_at=datetime.now(timezone.utc) + timedelta(minutes=1)
            )

    @patch("kyc.storage.cloudinary.config")
    def test_malformed_storage_keys_are_rejected_before_provider_access(self, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        bad_keys = [
            "https://example.com/private-document",
            "kyc/private/../../tenant/2/file",
            "kyc/private/workspace/1/tenant/2/not-a-uuid",
            "kyc/public/workspace/1/tenant/2/0123456789abcdef0123456789abcdef",
            "kyc/private/workspace/1/tenant/2/0123456789abcdef0123456789abcdef/extra",
        ]
        for key in bad_keys:
            with self.subTest(key=key):
                with self.assertRaises(PrivateStorageError):
                    self.storage.create_controlled_access(
                        key, expires_at=datetime.now(timezone.utc) + timedelta(minutes=1)
                    )

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.cloudinary.utils.private_download_url")
    def test_delivery_grant_rejects_naive_expiry(self, make_url, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        with self.assertRaises(PrivateStorageError):
            self.storage.create_controlled_access(self.key, expires_at=datetime.now())
        make_url.assert_not_called()

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.cloudinary.utils.private_download_url")
    def test_delivery_grant_rejects_expired_and_excessively_long_expiry(self, make_url, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.cloud_secret = "secret"
        config.return_value.api_secret = "secret"
        now = datetime.now(timezone.utc)
        with self.assertRaises(PrivateStorageError):
            self.storage.create_controlled_access(self.key, expires_at=now)
        with self.assertRaises(PrivateStorageError):
            self.storage.create_controlled_access(self.key, expires_at=now + timedelta(minutes=16))
        make_url.assert_not_called()

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.cloudinary.uploader.upload")
    def test_upload_rejects_empty_content_type(self, upload, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        with self.assertRaises(PrivateStorageError):
            self.storage.put(BytesIO(b"document"), storage_key=self.key, content_type=" ")
        upload.assert_not_called()

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.cloudinary.utils.private_download_url")
    def test_delivery_grant_is_short_lived_and_uses_private_raw_resource(self, make_url, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        make_url.return_value = "https://trusted.example/private"
        expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
        grant = self.storage.create_controlled_access(self.key, expires_at=expiry)
        self.assertEqual(grant.url, "https://trusted.example/private")
        make_url.assert_called_once()
        kwargs = make_url.call_args.kwargs
        self.assertEqual(kwargs["resource_type"], "raw")
        self.assertEqual(kwargs["type"], "private")

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.cloudinary.utils.private_download_url")
    @patch("kyc.storage.requests.get")
    def test_open_does_not_follow_redirects(self, get, make_url, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        make_url.return_value = "https://trusted.example/private"
        response = get.return_value
        response.content = b"document"
        response.raise_for_status.return_value = None
        result = self.storage.open(self.key)
        self.assertEqual(result.read(), b"document")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.cloudinary.utils.private_download_url", side_effect=RuntimeError("provider"))
    def test_provider_delivery_failure_is_sanitized(self, make_url, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        with self.assertRaisesMessage(PrivateStorageError, "delivery grant creation failed"):
            self.storage.create_controlled_access(
                self.key, expires_at=datetime.now(timezone.utc) + timedelta(minutes=1)
            )

    @patch("kyc.storage.cloudinary.config")
    @patch("kyc.storage.requests.get")
    @patch("kyc.storage.cloudinary.utils.private_download_url")
    def test_open_provider_failure_is_sanitized(self, make_url, get, config):
        config.return_value.cloud_name = "cloud"
        config.return_value.api_key = "key"
        config.return_value.api_secret = "secret"
        make_url.return_value = "https://trusted.example/private"
        get.side_effect = RuntimeError("secret provider detail")
        with self.assertRaisesMessage(PrivateStorageError, "KYC document retrieval failed"):
            self.storage.open(self.key)
