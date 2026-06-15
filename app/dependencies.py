"""FastAPI dependencies."""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.config.settings import get_settings


def get_current_db(db: Session = Depends(get_db)) -> Session:
    return db


def get_settings_dep():
    return get_settings()
