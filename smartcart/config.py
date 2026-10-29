"""
SmartCart runtime configuration, read from environment variables (and a local
.env file in development). See .env.example for every supported setting.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SMARTCART_", extra="ignore")

    environment: str = Field("development", description="development | staging | production")
    log_level: str = "INFO"

    # Database: a SQLAlchemy-style URL. sqlite:///path or postgresql://user:pass@host/db
    database_url: Optional[str] = None
    db_path: str = "smartcart.db"
    region: str = "edmonton"

    # Supabase Auth. Tokens are verified with the project's JWKS (asymmetric keys)
    # or, for legacy projects, the shared JWT secret.
    supabase_url: Optional[str] = None
    supabase_jwt_secret: Optional[str] = None
    supabase_jwt_audience: str = "authenticated"

    # Optional: lets account deletion also remove the Supabase auth user.
    supabase_service_role_key: Optional[str] = None

    # Accounts signing in with these (Supabase-verified) emails become admins with
    # full access. JSON list, e.g. ["owner@example.com"].
    admin_emails: List[str] = Field(default_factory=list)

    # Interim content-management guard (flyer uploads) until admin roles exist.
    admin_token: Optional[str] = None

    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    sentry_dsn: Optional[str] = None
    sentry_traces_sample_rate: float = 0.0

    # Run the periodic sync inside the web process. Turn off in production and
    # run `python -m smartcart.worker` as a separate process instead.
    run_scheduler: bool = True

    rate_limit_enabled: bool = True
    rate_limit_default: str = "120/minute"
    rate_limit_price_submissions: str = "60/hour"
    max_request_bytes: int = 8 * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
