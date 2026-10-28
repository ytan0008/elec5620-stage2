from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().database_url, connect_args={"check_same_thread": False, "timeout": 15} if settings().database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
