from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATA_DIR, DEFAULT_DB_PATH


DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH}"

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)


def init_db() -> None:
    from app.models import Base

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
