"""Create missing canonical tables for a fresh local Follei database."""
from app.database.base import Base
from app.config.database import engine
import app.models  # noqa: F401 - registers canonical mappings on Base.metadata


def ensure_base_schema() -> int:
    Base.metadata.create_all(bind=engine)
    return len(Base.metadata.tables)


if __name__ == "__main__":
    print(f"verified_tables={ensure_base_schema()}")