"""SQLAlchemy engine + session factory."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from app.config.settings import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    echo=settings.APP_ENV == "development",
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """FastAPI dependency: yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
