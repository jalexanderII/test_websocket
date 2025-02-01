from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,  # type: ignore
    sessionmaker,
)

from app.config.settings import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
