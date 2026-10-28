"""Test database helpers that work for both SQLite and Postgres runs."""

from smartcart import database


def reset_database() -> None:
    """Drop everything and re-run migrations so each test starts from an empty schema."""
    if database.is_postgres():
        conn = database.get_connection()
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.commit()
        conn.close()
    elif database.DB_PATH.exists():
        database.DB_PATH.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = database.DB_PATH.with_name(database.DB_PATH.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
    database.init_db()
