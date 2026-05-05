"""
Initialize database: create all tables + lightweight migrations.
"""

from sqlalchemy import text, inspect

from app.database.session import engine, Base
from app.database import models  # noqa: F401 — ensure models are registered


def _add_column_if_missing(conn, table: str, column: str, col_type: str, default: str = ""):
    """Add a column to an existing table if it doesn't exist (SQLite compatible)."""
    insp = inspect(conn)
    cols = [c["name"] for c in insp.get_columns(table)]
    if column not in cols:
        default_clause = f" DEFAULT {default}" if default else ""
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"))


def init_db():
    Base.metadata.create_all(bind=engine)

    # Lightweight migrations for columns added after initial schema
    with engine.connect() as conn:
        _add_column_if_missing(conn, "users", "is_admin", "BOOLEAN", "0")
        _add_column_if_missing(conn, "users", "role", "VARCHAR(32)", "'user'")
        _add_column_if_missing(conn, "users", "is_email_verified", "BOOLEAN", "0")
        conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database tables created.")
