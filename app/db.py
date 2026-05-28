import sqlite3

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import DATA_DIR, DEFAULT_DB_PATH


DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"


def create_sqlite_engine(database_url: str = DATABASE_URL) -> Engine:
    engine = create_engine(database_url, future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = create_sqlite_engine()
SessionLocal = sessionmaker(bind=engine, future=True)


def init_db() -> None:
    from app.models import Base

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
