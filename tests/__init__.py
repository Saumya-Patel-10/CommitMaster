"""
Test bootstrap: runs BEFORE any commitmaster module is imported.

Tests exercise the private admin edition against a throw-away data directory with a
synthetic administrator identity supplied via environment variables (the application
itself contains no hard-coded administrator).
"""
import os
import tempfile

os.environ.setdefault("COMMITMASTER_DATA_DIR", os.path.join(tempfile.gettempdir(), "cm_test_data"))
os.environ.setdefault("ADMIN_USERNAME", "test.admin@Admin_#")
os.environ.setdefault("ADMIN_EMAIL", "test.admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "Test-Admin-Pass-123!")

from commitmaster import edition  # noqa: E402

edition.set_admin_edition()
