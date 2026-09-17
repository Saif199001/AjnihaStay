import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class ProductionRLSSettingsContractTests(SimpleTestCase):
    def _import_settings_in_child(self, **overrides):
        env = os.environ.copy()
        env.pop("DJANGO_SETTINGS_MODULE", None)
        env.pop("DB_RLS_ENABLED", None)
        env.pop("DEBUG", None)
        env.update(overrides)

        code = """
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: None
import ajnihastay.settings
"""
        return subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_production_requires_db_rls_enabled(self):
        result = self._import_settings_in_child(DEBUG="false")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_RLS_ENABLED environment variable is required", result.stderr)

    def test_production_rejects_db_rls_disabled(self):
        result = self._import_settings_in_child(DEBUG="false", DB_RLS_ENABLED="false")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_RLS_ENABLED must be true when DEBUG=False", result.stderr)

    def test_production_rejects_invalid_db_rls_value(self):
        result = self._import_settings_in_child(DEBUG="false", DB_RLS_ENABLED="maybe")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_RLS_ENABLED must be a boolean value", result.stderr)

    def test_production_accepts_enabled_db_rls(self):
        result = self._import_settings_in_child(DEBUG="false", DB_RLS_ENABLED="true")

        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_debug_mode_can_explicitly_disable_db_rls(self):
        result = self._import_settings_in_child(DEBUG="true", DB_RLS_ENABLED="false")

        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_current_test_settings_use_atomic_requests_when_rls_enabled(self):
        self.assertTrue(settings.DB_RLS_ENABLED)
        self.assertTrue(settings.DATABASES["default"]["ATOMIC_REQUESTS"])
