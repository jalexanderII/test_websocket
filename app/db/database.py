from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,  # type: ignore
    sessionmaker,
)

from app.config.env import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
