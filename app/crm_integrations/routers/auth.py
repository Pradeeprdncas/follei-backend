from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.crm_integrations.database import get_db
from app.crm_integrations.models.auth import AuthUser as AuthUserModel
from app.crm_integrations.schemas.auth import AuthUser, LoginRequest, LogoutResponse, RegisterRequest, RegisterResponse, TokenResponse
from app.crm_integrations.security import bearer_scheme, create_session, get_current_user, hash_password, revoke_current_session, verify_password


router = APIRouter(prefix="/api/auth", tags=["01 Authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED, summary="Create login user")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(AuthUserModel).filter(AuthUserModel.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.")
    user = AuthUserModel(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return RegisterResponse(id=user.id, username=user.username)


@router.post("/login", response_model=TokenResponse, summary="Login and get bearer token")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AuthUserModel).filter(AuthUserModel.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")
    token = create_session(db, user)
    return TokenResponse(access_token=token, user_id=user.id, username=user.username)


@router.get("/me", response_model=AuthUser, summary="Get current authenticated user")
def me(user: dict = Depends(get_current_user)):
    return AuthUser(**user)


@router.post("/logout", response_model=LogoutResponse, summary="Logout current session")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)):
    user = revoke_current_session(credentials, db)
    return LogoutResponse(message=f"{user.username} logged out.")
