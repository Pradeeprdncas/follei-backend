"""Auth router — uses AuthService, does NOT access DB directly."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Any

from app import schema
from app.database.session import get_db
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Identity & Auth"])


def _auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/register", response_model=schema.Token, status_code=status.HTTP_201_CREATED)
def register_tenant(payload: schema.RegisterRequest, auth: AuthService = Depends(_auth_service)) -> Any:
    return auth.register_tenant(
        name=payload.name,
        domain=payload.domain,
        admin_email=payload.admin_email,
        admin_password=payload.admin_password,
        admin_first_name=payload.admin_first_name,
        admin_last_name=payload.admin_last_name,
        business_phone_number=payload.business_phone_number,
        business_email=payload.business_email,
        timezone=payload.timezone,
        business_hours=payload.business_hours,
        forwarding_number=payload.forwarding_number,
        auto_reply_enabled=payload.auto_reply_enabled,
        channel_config=payload.channel_config,
    )


@router.post("/login", response_model=schema.Token)
def login(payload: schema.LoginRequest, auth: AuthService = Depends(_auth_service)) -> Any:
    return auth.login(email=payload.email, password=payload.password)


@router.get("/me", response_model=schema.User)
def get_current_user_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    auth: AuthService = Depends(_auth_service),
) -> Any:
    return auth.get_current_user(credentials.credentials)
