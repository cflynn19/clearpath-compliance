import os

from sqlalchemy import create_engine


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://localhost/clearpath")
    # Hosts hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


engine = create_engine(_database_url(), pool_pre_ping=True)
