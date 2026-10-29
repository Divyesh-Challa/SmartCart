"""Lock tables away from Supabase's auto-generated Data API.

Supabase exposes every table in the public schema over REST/GraphQL to the
browser-visible anon key. SmartCart only reads and writes the database through
its own API (as the table owner), so row-level security is enabled on every
table with no policies, which denies the anon and authenticated roles entirely.
No-op on SQLite.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    tables = [r[0] for r in bind.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))]
    for table in tables:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
    op.execute("""
        DO $$
        DECLARE r text;
        BEGIN
            FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
                    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
                    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
                    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
                END IF;
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    tables = [r[0] for r in bind.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))]
    for table in tables:
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
