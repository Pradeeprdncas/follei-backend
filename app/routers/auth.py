from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Any
from uuid import UUID

from app import schema
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models.tenancy import Tenant, User

bearer_scheme = HTTPBearer()

router = APIRouter(
    prefix="/auth",
    tags=["Identity & Auth"]
)

@router.post("/register", response_model=schema.Token, status_code=status.HTTP_201_CREATED)
def register_tenant(payload: schema.RegisterRequest, db: Session = Depends(get_db)) -> Any:
    """
    Create a new tenant, an initial admin user, and return an access token.
    """
    existing_tenant = db.query(Tenant).filter(Tenant.domain == payload.domain).first()
    if payload.domain and existing_tenant:
        raise HTTPException(status_code=409, detail="Tenant domain already exists")

    existing_user = db.query(User).filter(User.email == payload.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="User email already exists")

    tenant = Tenant(name=payload.name, domain=payload.domain)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=payload.admin_email,
        hashed_password=hash_password(payload.admin_password),
        first_name=payload.admin_first_name,
        last_name=payload.admin_last_name,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user.id, user.tenant_id), "token_type": "bearer"}

@router.post("/login", response_model=schema.Token)
def login(payload: schema.LoginRequest, db: Session = Depends(get_db)) -> Any:
    """
    Authenticate a user and return a JWT token.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")
    return {"access_token": create_access_token(user.id, user.tenant_id), "token_type": "bearer"}

@router.get("/me", response_model=schema.User)
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get the current authenticated user's profile.
    """
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, UUID(payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")
    return user
