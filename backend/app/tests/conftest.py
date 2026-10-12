"""Test session configuration.

Points the app at a throwaway SQLite file BEFORE any `app.*` module is imported, so the
suite never reads or writes the developer's `hardware_billing.db` and always starts clean.

Set TEST_DATABASE_URL (e.g. postgresql+asyncpg://user@127.0.0.1:5432/scratch_db) to run the
suite against a disposable PostgreSQL database instead. Never point it at real shop data.
"""

import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="hw_billing_tests_")
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_billing.db").replace("\\", "/")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
os.environ.setdefault("ENVIRONMENT", "testing")
