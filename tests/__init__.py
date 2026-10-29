"""
Test-wide configuration. This runs before any test module imports smartcart,
so settings read at import time see these values.
"""

import os
import tempfile

# Never touch the real smartcart.db or any database configured in .env. Environment
# variables take precedence over .env, so these overrides always win. Postgres test
# runs opt in with SMARTCART_TEST_DATABASE_URL (localhost only; see tests/db_utils.py).
os.environ["SMARTCART_DATABASE_URL"] = os.environ.get("SMARTCART_TEST_DATABASE_URL", "")
os.environ["SMARTCART_SUPABASE_URL"] = ""
os.environ["SMARTCART_SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["SMARTCART_SENTRY_DSN"] = ""
os.environ["SMARTCART_ADMIN_EMAILS"] = '["owner@example.com"]'
os.environ["SMARTCART_DB_PATH"] = (os.path.join(tempfile.mkdtemp(prefix="smartcart-test-"), "test.db"))
# Tokens in tests are signed with this HS256 secret (see tests/auth_utils.py).
os.environ["SMARTCART_SUPABASE_JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"
os.environ.setdefault("SMARTCART_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SMARTCART_RUN_SCHEDULER", "false")
os.environ["SMARTCART_ADMIN_TOKEN"] = "test-admin-token"
