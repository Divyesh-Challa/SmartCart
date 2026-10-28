"""
Test-wide configuration. This runs before any test module imports smartcart,
so settings read at import time see these values.
"""

import os
import tempfile

# Never touch the real smartcart.db.
os.environ.setdefault("SMARTCART_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="smartcart-test-"), "test.db"))
# Tokens in tests are signed with this HS256 secret (see tests/auth_utils.py).
os.environ.setdefault("SMARTCART_SUPABASE_JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
os.environ.setdefault("SMARTCART_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SMARTCART_RUN_SCHEDULER", "false")
os.environ.setdefault("SMARTCART_ADMIN_TOKEN", "test-admin-token")
