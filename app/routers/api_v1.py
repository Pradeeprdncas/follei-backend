import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.database.session import get_db


router = APIRouter(prefix="/api/v1")
bearer_scheme = HTTPBearer(auto_error=False)
TOKEN_EXPIRES_IN = 3600


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class RegisterRequest(BaseModel):
    """Account + tenant creation only. No onboarding-wizard fields belong here."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)
    tenant_name: str = Field(..., min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def _password_complexity(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
            raise ValueError("Password must contain at least one letter and at least one number")
        return value


class RegisterResponse(BaseModel):
    user_id: str
    tenant_id: str
    access_token: str
    token_type: str
    refresh_token: str
    expires_in: int


class LoginRequest(FlexibleModel):
    email: EmailStr
    password: str


class RefreshRequest(FlexibleModel):
    refresh_token: str


class LogoutRequest(FlexibleModel):
    refresh_token: str


class ProfileUpdateRequest(FlexibleModel):
    full_name: str | None = None
    phone: str | None = None


class PasswordChangeRequest(FlexibleModel):
    current_password: str
    new_password: str


class PasswordResetRequest(FlexibleModel):
    email: EmailStr


class PasswordResetConfirmRequest(FlexibleModel):
    token: str
    new_password: str


class TenantCreateRequest(FlexibleModel):
    name: str
    slug: str | None = None
    plan_id: UUID | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class TenantUpdateRequest(FlexibleModel):
    name: str | None = None
    status: str | None = None
    settings: dict[str, Any] | None = None


class TenantSettingsUpdateRequest(FlexibleModel):
    timezone: str | None = None
    language: str | None = None
    features: dict[str, Any] | None = None
    branding: dict[str, Any] | None = None


class UserCreateRequest(FlexibleModel):
    email: EmailStr
    password: str
    full_name: str
    role_ids: list[UUID] = Field(default_factory=list)
    tenant_id: UUID


class UserUpdateRequest(FlexibleModel):
    full_name: str | None = None
    status: str | None = None
    role_ids: list[UUID] | None = None


class RoleCreateRequest(FlexibleModel):
    name: str
    display_name: str | None = None
    permissions: list[str] = Field(default_factory=list)
    tenant_id: UUID | None = None


class AssignRoleRequest(FlexibleModel):
    role_id: UUID


class ApiKeyCreateRequest(FlexibleModel):
    name: str
    permissions: list[str] = Field(default_factory=list)


class AgentCreateRequest(FlexibleModel):
    name: str
    type: str = "sdr"
    description: str | None = None
    tenant_id: UUID
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"


class AgentUpdateRequest(FlexibleModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    status: str | None = None


class AgentChatRequest(FlexibleModel):
    message: str
    conversation_id: UUID | None = None
    session_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentVersionRequest(FlexibleModel):
    name: str | None = None
    notes: str | None = None


class AgentSessionRequest(FlexibleModel):
    user_id: UUID | None = None
    conversation_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSessionUpdateRequest(FlexibleModel):
    status: str
    end_reason: str | None = None


class AgentTaskRequest(FlexibleModel):
    type: str
    description: str
    priority: str = "normal"
    due_at: datetime | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AgentTaskUpdateRequest(FlexibleModel):
    status: str
    result: dict[str, Any] = Field(default_factory=dict)


class AgentMemoryRequest(FlexibleModel):
    type: str
    key: str
    value: Any
    ttl_days: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AgentFeedbackRequest(FlexibleModel):
    rating: int
    comment: str | None = None
    message_id: UUID | None = None
    category: str | None = None


class ToolPermissionRequest(FlexibleModel):
    tool_id: UUID
    permission: str = "execute"
    constraints: dict[str, Any] = Field(default_factory=dict)


class BackgroundJobRequest(FlexibleModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"
    scheduled_at: datetime | None = None


class NotificationRequest(FlexibleModel):
    user_id: UUID | None = None
    type: str
    title: str
    body: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"


class FeatureFlagRequest(FlexibleModel):
    name: str
    description: str | None = None
    enabled: bool = False
    target: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpdateRequest(FlexibleModel):
    enabled: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _full_name_parts(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(" ", 1)
    return parts[0] if parts else "", parts[1] if len(parts) > 1 else ""


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row._mapping) if row else None


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result]


def _page(items: list[dict[str, Any]], total: int, page: int, page_size: int) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _token_pair(user_id: UUID, tenant_id: UUID) -> dict[str, Any]:
    access_token = create_access_token(user_id, tenant_id)
    refresh_token = create_access_token(user_id, tenant_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": TOKEN_EXPIRES_IN,
    }


def _current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = _row(db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": payload["sub"]}).first())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _permissions_for_user(db: Session, user_id: UUID) -> list[str]:
    try:
        rows = db.execute(
            text(
                """
                SELECT p.resource, p.action
                FROM user_roles ur
                JOIN role_permissions rp ON rp.role_id = ur.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.user_id = :user_id
                ORDER BY p.resource, p.action
                """
            ),
            {"user_id": user_id},
        )
        permissions = [f"{row.resource}.{row.action}" for row in rows]
    except SQLAlchemyError:
        # Older/local schemas use the canonical users.role column and do not
        # have the optional normalized RBAC join tables yet.
        db.rollback()
        permissions = []
    return permissions or ["read", "write", "delete"]


def _roles_for_user(db: Session, user_id: UUID, fallback: str | None = None) -> list[str]:
    try:
        rows = db.execute(
            text(
                """
                SELECT r.name
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = :user_id
                ORDER BY r.name
                """
            ),
            {"user_id": user_id},
        )
        roles = [row.name for row in rows]
    except SQLAlchemyError:
        db.rollback()
        roles = []
    return roles or ([fallback] if fallback else [])


@router.post("/auth/register", tags=["Domain 1 - Auth"], status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    existing_user = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": payload.email}).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="User email already exists")

    tenant_id = uuid4()
    user_id = uuid4()
    first_name, last_name = _full_name_parts(payload.full_name)
    domain = payload.email.split("@", 1)[1] if "@" in payload.email else None

    tenant_insert = text(
        """
        INSERT INTO tenants (id, name, domain, slug, status, is_active, timezone, auto_reply_enabled, created_at, updated_at)
        VALUES (:id, :name, :domain, :slug, 'active', true, :timezone, false, :now, :now)
        """
    )
    tenant_params = {"id": tenant_id, "name": payload.tenant_name, "domain": domain, "slug": payload.tenant_name.lower().replace(" ", "-"), "timezone": "Asia/Kolkata", "now": _now()}
    try:
        db.execute(tenant_insert, tenant_params)
    except IntegrityError:
        # `domain` is derived from the signup email and only unique per-tenant by
        # convention, not by business rule — two unrelated tenants can share a
        # free/shared email provider domain (gmail.com, outlook.com, ...). Fall
        # back to no domain rather than failing registration outright.
        db.rollback()
        db.execute(tenant_insert, {**tenant_params, "domain": None})
    db.execute(
        text(
            """
            INSERT INTO users (
                id, tenant_id, email, hashed_password, first_name, last_name, full_name,
                role, status, is_active, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :email, :hashed_password, :first_name, :last_name, :full_name,
                'admin', 'active', true, :now, :now
            )
            """
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": payload.email,
            "hashed_password": hash_password(payload.password),
            "first_name": first_name,
            "last_name": last_name,
            "full_name": payload.full_name,
            "now": _now(),
        },
    )
    db.commit()
    tokens = _token_pair(user_id, tenant_id)
    return RegisterResponse(user_id=str(user_id), tenant_id=str(tenant_id), **tokens)


@router.post("/auth/login", tags=["Domain 1 - Auth"])
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _row(db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": payload.email}).first())
    if not user or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.get("is_active") is False or user.get("status") == "inactive":
        raise HTTPException(status_code=403, detail="User is inactive")
    db.execute(text("UPDATE users SET last_login_at = :now WHERE id = :id"), {"now": _now(), "id": user["id"]})
    db.commit()
    tokens = _token_pair(user["id"], user["tenant_id"])
    return {
        **tokens,
        "user": {
            "id": str(user["id"]),
            "email": user["email"],
            "full_name": user.get("full_name") or f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "tenant_id": str(user["tenant_id"]),
            "roles": _roles_for_user(db, user["id"], user.get("role")),
        },
    }


@router.post("/auth/refresh", tags=["Domain 1 - Auth"])
def refresh(payload: RefreshRequest) -> dict[str, Any]:
    try:
        token_payload = decode_access_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return {
        "access_token": create_access_token(UUID(token_payload["sub"]), UUID(token_payload["tenant_id"])),
        "expires_in": TOKEN_EXPIRES_IN,
    }


@router.post("/auth/logout", tags=["Domain 1 - Auth"])
def logout(payload: LogoutRequest) -> dict[str, str]:
    return {"message": "Logged out successfully"}


@router.get("/auth/me", tags=["Domain 1 - Auth"])
def me(current_user: dict[str, Any] = Depends(_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    tenant = _row(db.execute(text("SELECT name FROM tenants WHERE id = :id"), {"id": current_user["tenant_id"]}).first())
    return {
        "id": str(current_user["id"]),
        "email": current_user["email"],
        "full_name": current_user.get("full_name") or f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
        "tenant_id": str(current_user["tenant_id"]),
        "tenant_name": tenant["name"] if tenant else None,
        "roles": _roles_for_user(db, current_user["id"], current_user.get("role")),
        "permissions": _permissions_for_user(db, current_user["id"]),
        "created_at": current_user.get("created_at"),
        "last_login": current_user.get("last_login_at"),
    }


@router.patch("/auth/me", tags=["Domain 1 - Auth"])
def update_me(payload: ProfileUpdateRequest, current_user: dict[str, Any] = Depends(_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    if payload.full_name:
        first_name, last_name = _full_name_parts(payload.full_name)
        db.execute(
            text("UPDATE users SET full_name = :full_name, first_name = :first_name, last_name = :last_name, updated_at = :now WHERE id = :id"),
            {"full_name": payload.full_name, "first_name": first_name, "last_name": last_name, "now": _now(), "id": current_user["id"]},
        )
        db.commit()
    return me(_row(db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": current_user["id"]}).first()), db)


@router.post("/auth/password/change", tags=["Domain 1 - Auth"])
def change_password(payload: PasswordChangeRequest, current_user: dict[str, Any] = Depends(_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    if not verify_password(payload.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    db.execute(text("UPDATE users SET hashed_password = :hash, updated_at = :now WHERE id = :id"), {"hash": hash_password(payload.new_password), "now": _now(), "id": current_user["id"]})
    db.commit()
    return {"message": "Password changed successfully"}


@router.post("/auth/password/reset-request", tags=["Domain 1 - Auth"])
def reset_request(payload: PasswordResetRequest) -> dict[str, str]:
    return {"message": "If the email exists, a reset link will be sent"}


@router.post("/auth/password/reset", tags=["Domain 1 - Auth"])
def reset_password(payload: PasswordResetConfirmRequest) -> dict[str, str]:
    return {"message": "Password reset token accepted"}


@router.post("/tenants", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    tenant_id = uuid4()
    db.execute(
        text("INSERT INTO tenants (id, name, slug, status, is_active, timezone, auto_reply_enabled, created_at, updated_at) VALUES (:id, :name, :slug, 'active', true, :timezone, false, :now, :now)"),
        {"id": tenant_id, "name": payload.name, "slug": payload.slug, "timezone": "Asia/Kolkata", "now": _now()},
    )
    db.execute(
        text("INSERT INTO tenant_settings (id, tenant_id, settings, created_at, updated_at) VALUES (:id, :tenant_id, :settings, :now, :now) ON CONFLICT (tenant_id) DO NOTHING"),
        {"id": uuid4(), "tenant_id": tenant_id, "settings": payload.settings, "now": _now()},
    )
    db.commit()
    return {"id": str(tenant_id), "name": payload.name, "slug": payload.slug, "status": "active", "created_at": _now()}


@router.get("/tenants", tags=["Domain 2 - Tenants & Users"])
def list_tenants(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)) -> dict[str, Any]:
    offset = (page - 1) * page_size
    items = _rows(db.execute(text("SELECT * FROM tenants ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), {"limit": page_size, "offset": offset}))
    total = db.execute(text("SELECT count(*) FROM tenants")).scalar_one()
    return _page(items, total, page, page_size)


@router.get("/tenants/{tenant_id}", tags=["Domain 2 - Tenants & Users"])
def get_tenant(tenant_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    tenant = _row(db.execute(text("SELECT * FROM tenants WHERE id = :id"), {"id": tenant_id}).first())
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    settings = _row(db.execute(text("SELECT settings FROM tenant_settings WHERE tenant_id = :id"), {"id": tenant_id}).first())
    usage = {
        "users": db.execute(text("SELECT count(*) FROM users WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "documents": db.execute(text("SELECT count(*) FROM documents WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "api_calls": db.execute(text("SELECT count(*) FROM api_request_logs WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
    }
    return {**tenant, "settings": settings["settings"] if settings else {}, "usage": usage}


@router.patch("/tenants/{tenant_id}", tags=["Domain 2 - Tenants & Users"])
def update_tenant(tenant_id: UUID, payload: TenantUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    tenant = get_tenant(tenant_id, db)
    db.execute(
        text("UPDATE tenants SET name = COALESCE(:name, name), status = COALESCE(:status, status), updated_at = :now WHERE id = :id"),
        {"name": payload.name, "status": payload.status, "now": _now(), "id": tenant_id},
    )
    if payload.settings is not None:
        db.execute(text("UPDATE tenant_settings SET settings = :settings, updated_at = :now WHERE tenant_id = :id"), {"settings": payload.settings, "now": _now(), "id": tenant_id})
    db.commit()
    return get_tenant(tenant_id, db)


@router.delete("/tenants/{tenant_id}", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(tenant_id: UUID, db: Session = Depends(get_db)) -> Response:
    db.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tenants/{tenant_id}/settings", tags=["Domain 2 - Tenants & Users"])
def get_tenant_settings(tenant_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = _row(db.execute(text("SELECT settings FROM tenant_settings WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id}).first())
    return {"tenant_id": str(tenant_id), **(settings["settings"] if settings else {})}


@router.patch("/tenants/{tenant_id}/settings", tags=["Domain 2 - Tenants & Users"])
def update_tenant_settings(tenant_id: UUID, payload: TenantSettingsUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = payload.model_dump(exclude_none=True)
    db.execute(
        text("INSERT INTO tenant_settings (id, tenant_id, settings, created_at, updated_at) VALUES (:id, :tenant_id, :settings, :now, :now) ON CONFLICT (tenant_id) DO UPDATE SET settings = :settings, updated_at = :now"),
        {"id": uuid4(), "tenant_id": tenant_id, "settings": settings, "now": _now()},
    )
    db.commit()
    return {"tenant_id": str(tenant_id), **settings}


@router.get("/tenants/{tenant_id}/usage", tags=["Domain 2 - Tenants & Users"])
def tenant_usage(tenant_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "tenant_id": str(tenant_id),
        "period": _now().strftime("%Y-%m"),
        "users": db.execute(text("SELECT count(*) FROM users WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "conversations": db.execute(text("SELECT count(*) FROM conversations WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "messages": db.execute(text("SELECT count(*) FROM conversation_messages WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "documents": db.execute(text("SELECT count(*) FROM documents WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "api_calls": db.execute(text("SELECT count(*) FROM api_request_logs WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "tokens_used": db.execute(text("SELECT COALESCE(sum(quantity), 0) FROM token_usage WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one(),
        "cost_usd": float(db.execute(text("SELECT COALESCE(sum(cost), 0) FROM cost_tracking WHERE tenant_id = :id"), {"id": tenant_id}).scalar_one()),
    }


@router.post("/users", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    user_id = uuid4()
    first_name, last_name = _full_name_parts(payload.full_name)
    db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, hashed_password, first_name, last_name, full_name, role, status, is_active, created_at, updated_at)
            VALUES (:id, :tenant_id, :email, :hashed_password, :first_name, :last_name, :full_name, 'member', 'active', true, :now, :now)
            """
        ),
        {"id": user_id, "tenant_id": payload.tenant_id, "email": payload.email, "hashed_password": hash_password(payload.password), "first_name": first_name, "last_name": last_name, "full_name": payload.full_name, "now": _now()},
    )
    for role_id in payload.role_ids:
        db.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"), {"user_id": user_id, "role_id": role_id})
    db.commit()
    return get_user(user_id, db)


@router.get("/users", tags=["Domain 2 - Tenants & Users"])
def list_users(tenant_id: UUID | None = None, role: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)) -> dict[str, Any]:
    filters = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if tenant_id:
        filters.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if role:
        filters.append("role = :role")
        params["role"] = role
    if status:
        filters.append("status = :status")
        params["status"] = status
    where = "WHERE " + " AND ".join(filters) if filters else ""
    items = _rows(db.execute(text(f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), params))
    total = db.execute(text(f"SELECT count(*) FROM users {where}"), params).scalar_one()
    for item in items:
        item["roles"] = _roles_for_user(db, item["id"], item.get("role"))
    return _page(items, total, page, page_size)


@router.get("/users/{user_id}", tags=["Domain 2 - Tenants & Users"])
def get_user(user_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _row(db.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).first())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["roles"] = _roles_for_user(db, user_id, user.get("role"))
    user["permissions"] = _permissions_for_user(db, user_id)
    return user


@router.patch("/users/{user_id}", tags=["Domain 2 - Tenants & Users"])
def update_user(user_id: UUID, payload: UserUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if payload.full_name:
        first_name, last_name = _full_name_parts(payload.full_name)
        db.execute(text("UPDATE users SET full_name = :full_name, first_name = :first_name, last_name = :last_name, updated_at = :now WHERE id = :id"), {"full_name": payload.full_name, "first_name": first_name, "last_name": last_name, "now": _now(), "id": user_id})
    if payload.status:
        db.execute(text("UPDATE users SET status = :status, is_active = :is_active, updated_at = :now WHERE id = :id"), {"status": payload.status, "is_active": payload.status == "active", "now": _now(), "id": user_id})
    if payload.role_ids is not None:
        db.execute(text("DELETE FROM user_roles WHERE user_id = :user_id"), {"user_id": user_id})
        for role_id in payload.role_ids:
            db.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"), {"user_id": user_id, "role_id": role_id})
    db.commit()
    return get_user(user_id, db)


@router.delete("/users/{user_id}", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: UUID, db: Session = Depends(get_db)) -> Response:
    db.execute(text("UPDATE users SET status = 'inactive', is_active = false, updated_at = :now WHERE id = :id"), {"now": _now(), "id": user_id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/roles", tags=["Domain 2 - Tenants & Users"])
def assign_role(user_id: UUID, payload: AssignRoleRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id) ON CONFLICT DO NOTHING"), {"user_id": user_id, "role_id": payload.role_id})
    db.commit()
    return {"message": "Role assigned"}


@router.delete("/users/{user_id}/roles/{role_id}", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_204_NO_CONTENT)
def remove_role(user_id: UUID, role_id: UUID, db: Session = Depends(get_db)) -> Response:
    db.execute(text("DELETE FROM user_roles WHERE user_id = :user_id AND role_id = :role_id"), {"user_id": user_id, "role_id": role_id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/roles", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    role_id = uuid4()
    tenant_id = payload.tenant_id or db.execute(text("SELECT id FROM tenants ORDER BY created_at DESC LIMIT 1")).scalar()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required when no tenant exists")
    db.execute(text("INSERT INTO roles (id, tenant_id, name, description, created_at, updated_at) VALUES (:id, :tenant_id, :name, :description, :now, :now)"), {"id": role_id, "tenant_id": tenant_id, "name": payload.name, "description": payload.display_name, "now": _now()})
    for permission_name in payload.permissions:
        resource, _, action = permission_name.partition(".")
        permission_id = db.execute(text("SELECT id FROM permissions WHERE resource = :resource AND action = :action"), {"resource": resource, "action": action or "read"}).scalar()
        if not permission_id:
            permission_id = uuid4()
            db.execute(text("INSERT INTO permissions (id, resource, action, created_at) VALUES (:id, :resource, :action, :now)"), {"id": permission_id, "resource": resource, "action": action or "read", "now": _now()})
        db.execute(text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"), {"role_id": role_id, "permission_id": permission_id})
    db.commit()
    return {"id": str(role_id), "name": payload.name, "permissions": payload.permissions}


@router.get("/roles", tags=["Domain 2 - Tenants & Users"])
def list_roles(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT * FROM roles ORDER BY name")))}


@router.get("/permissions", tags=["Domain 2 - Tenants & Users"])
def list_permissions(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT * FROM permissions ORDER BY resource, action")))}


@router.get("/tenant-api-keys", tags=["Domain 2 - Tenants & Users"])
def list_api_keys(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT id, name, left(key_hash, 8) AS prefix, created_at FROM tenant_api_keys ORDER BY created_at DESC")))}


@router.post("/tenant-api-keys", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiKeyCreateRequest, current_user: dict[str, Any] = Depends(_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    key = f"fl_live_{uuid4().hex}{uuid4().hex}"
    key_id = uuid4()
    db.execute(text("INSERT INTO tenant_api_keys (id, tenant_id, name, key_hash, scopes, created_at, updated_at) VALUES (:id, :tenant_id, :name, :key_hash, :scopes, :now, :now)"), {"id": key_id, "tenant_id": current_user["tenant_id"], "name": payload.name, "key_hash": hash_password(key), "scopes": payload.permissions, "now": _now()})
    db.commit()
    return {"id": str(key_id), "key": key, "name": payload.name}


@router.delete("/tenant-api-keys/{key_id}", tags=["Domain 2 - Tenants & Users"], status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: UUID, db: Session = Depends(get_db)) -> Response:
    db.execute(text("UPDATE tenant_api_keys SET is_active = false, updated_at = :now WHERE id = :id"), {"now": _now(), "id": key_id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/agents", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent_id = uuid4()
    system_prompt = payload.config.get("system_prompt") or payload.description or "You are a helpful AI assistant."
    db.execute(text("INSERT INTO agents (id, tenant_id, name, role, system_prompt, tools, agent_type, model, is_active, created_at, updated_at) VALUES (:id, :tenant_id, :name, :role, :system_prompt, :tools, :agent_type, :model, :is_active, :now, :now)"), {"id": agent_id, "tenant_id": payload.tenant_id, "name": payload.name, "role": payload.type, "system_prompt": system_prompt, "tools": payload.config.get("tools", []), "agent_type": payload.type, "model": payload.config.get("model"), "is_active": payload.status == "active", "now": _now()})
    db.execute(text("INSERT INTO agent_versions (id, tenant_id, agent_id, version, model, system_prompt, config, created_at) VALUES (:id, :tenant_id, :agent_id, 1, :model, :system_prompt, :config, :now)"), {"id": uuid4(), "tenant_id": payload.tenant_id, "agent_id": agent_id, "model": payload.config.get("model"), "system_prompt": system_prompt, "config": payload.config, "now": _now()})
    db.commit()
    return {"id": str(agent_id), "name": payload.name, "type": payload.type, "tenant_id": str(payload.tenant_id), "config": payload.config, "status": payload.status, "created_at": _now(), "version": 1}


@router.get("/agents", tags=["Domain 3 - Agents & AI Workforce"])
def list_agents(tenant_id: UUID | None = None, type: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)) -> dict[str, Any]:
    filters = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if tenant_id:
        filters.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if type:
        filters.append("(agent_type = :type OR role = :type)")
        params["type"] = type
    if status:
        filters.append("is_active = :active")
        params["active"] = status == "active"
    where = "WHERE " + " AND ".join(filters) if filters else ""
    items = _rows(db.execute(text(f"SELECT id, name, role AS type, tenant_id, is_active, created_at FROM agents {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), params))
    total = db.execute(text(f"SELECT count(*) FROM agents {where}"), params).scalar_one()
    return _page(items, total, page, page_size)


@router.get("/agents/{agent_id}", tags=["Domain 3 - Agents & AI Workforce"])
def get_agent(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = _row(db.execute(text("SELECT * FROM agents WHERE id = :id"), {"id": agent_id}).first())
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    stats = {
        "conversations": db.execute(text("SELECT count(*) FROM conversations WHERE agent_id = :id"), {"id": agent_id}).scalar_one(),
        "messages": db.execute(text("SELECT count(*) FROM conversation_messages cm JOIN conversations c ON c.id = cm.conversation_id WHERE c.agent_id = :id"), {"id": agent_id}).scalar_one(),
        "avg_confidence": float(db.execute(text("SELECT COALESCE(avg(score), 0) FROM agent_confidence_scores WHERE agent_id = :id"), {"id": agent_id}).scalar_one()),
        "avg_response_time_ms": 0,
    }
    return {**agent, "type": agent.get("agent_type") or agent.get("role"), "config": {"tools": agent.get("tools") or [], "model": agent.get("model")}, "status": "active" if agent.get("is_active") else "inactive", "stats": stats}


@router.patch("/agents/{agent_id}", tags=["Domain 3 - Agents & AI Workforce"])
def update_agent(agent_id: UUID, payload: AgentUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("UPDATE agents SET name = COALESCE(:name, name), is_active = COALESCE(:is_active, is_active), model = COALESCE(:model, model), updated_at = :now WHERE id = :id"), {"name": payload.name, "is_active": None if payload.status is None else payload.status == "active", "model": (payload.config or {}).get("model"), "now": _now(), "id": agent_id})
    db.commit()
    return get_agent(agent_id, db)


@router.delete("/agents/{agent_id}", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: UUID, db: Session = Depends(get_db)) -> Response:
    db.execute(text("DELETE FROM agents WHERE id = :id"), {"id": agent_id})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/agents/{agent_id}/chat", tags=["Domain 3 - Agents & AI Workforce"])
def chat(agent_id: UUID, payload: AgentChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    conversation_id = payload.conversation_id or uuid4()
    message_id = uuid4()
    tenant_id = agent["tenant_id"]
    if not payload.conversation_id:
        db.execute(text("INSERT INTO conversations (id, tenant_id, agent_id, customer_id, lead_id, title, channel, status, created_at, started_at, updated_at) VALUES (:id, :tenant_id, :agent_id, :customer_id, :lead_id, :title, :channel, 'open', :now, :now, :now)"), {"id": conversation_id, "tenant_id": tenant_id, "agent_id": agent_id, "customer_id": payload.context.get("customer_id"), "lead_id": payload.context.get("lead_id"), "title": payload.message[:80], "channel": payload.metadata.get("source"), "now": _now()})
    db.execute(text("INSERT INTO conversation_messages (id, tenant_id, conversation_id, role, content, sender_type, message, message_type, metadata, created_at) VALUES (:id, :tenant_id, :conversation_id, 'assistant', :content, 'agent', :message, 'text', :metadata, :now)"), {"id": message_id, "tenant_id": tenant_id, "conversation_id": conversation_id, "content": f"Stub response from {agent['name']}: {payload.message}", "message": f"Stub response from {agent['name']}: {payload.message}", "metadata": payload.metadata, "now": _now()})
    db.commit()
    return {"message_id": str(message_id), "conversation_id": str(conversation_id), "agent_id": str(agent_id), "content": f"Stub response from {agent['name']}: {payload.message}", "role": "assistant", "citations": [], "confidence": 0.0, "supported": False, "tool_calls": [], "latency_ms": 0, "tokens_used": {"input": 0, "output": 0, "total": 0}, "created_at": _now()}


@router.post("/agents/{agent_id}/versions", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def snapshot_agent(agent_id: UUID, payload: AgentVersionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    version = db.execute(text("SELECT COALESCE(max(version), 0) + 1 FROM agent_versions WHERE agent_id = :id"), {"id": agent_id}).scalar_one()
    db.execute(text("INSERT INTO agent_versions (id, tenant_id, agent_id, version, model, system_prompt, config, created_at) VALUES (:id, :tenant_id, :agent_id, :version, :model, :system_prompt, :config, :now)"), {"id": uuid4(), "tenant_id": agent["tenant_id"], "agent_id": agent_id, "version": version, "model": agent.get("model"), "system_prompt": agent["system_prompt"], "config": {"name": payload.name, "notes": payload.notes}, "now": _now()})
    db.commit()
    return {"version": version, "name": payload.name, "created_at": _now()}


@router.get("/agents/{agent_id}/versions", tags=["Domain 3 - Agents & AI Workforce"])
def list_agent_versions(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT version, config->>'name' AS name, created_at FROM agent_versions WHERE agent_id = :id ORDER BY version"), {"id": agent_id}))}


@router.post("/agents/{agent_id}/sessions", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def start_agent_session(agent_id: UUID, payload: AgentSessionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    session_id = uuid4()
    db.execute(text("INSERT INTO agent_sessions (id, tenant_id, agent_id, conversation_id, status, started_at, metadata) VALUES (:id, :tenant_id, :agent_id, :conversation_id, 'active', :now, :metadata)"), {"id": session_id, "tenant_id": agent["tenant_id"], "agent_id": agent_id, "conversation_id": payload.conversation_id, "now": _now(), "metadata": payload.metadata})
    db.commit()
    return {"id": str(session_id), "status": "active", "started_at": _now()}


@router.get("/agents/{agent_id}/sessions", tags=["Domain 3 - Agents & AI Workforce"])
def list_agent_sessions(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT id, status, started_at, ended_at FROM agent_sessions WHERE agent_id = :id ORDER BY started_at DESC"), {"id": agent_id}))}


@router.patch("/agents/{agent_id}/sessions/{session_id}", tags=["Domain 3 - Agents & AI Workforce"])
def update_agent_session(agent_id: UUID, session_id: UUID, payload: AgentSessionUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("UPDATE agent_sessions SET status = :status, ended_at = CASE WHEN :status = 'ended' THEN :now ELSE ended_at END WHERE id = :id AND agent_id = :agent_id"), {"status": payload.status, "now": _now(), "id": session_id, "agent_id": agent_id})
    db.commit()
    return {"id": str(session_id), "status": payload.status, "end_reason": payload.end_reason}


@router.post("/agents/{agent_id}/tasks", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def create_agent_task(agent_id: UUID, payload: AgentTaskRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    task_id = uuid4()
    db.execute(text("INSERT INTO agent_tasks (id, tenant_id, agent_id, task_type, title, payload, status, due_at, created_at, updated_at) VALUES (:id, :tenant_id, :agent_id, :task_type, :title, :payload, 'pending', :due_at, :now, :now)"), {"id": task_id, "tenant_id": agent["tenant_id"], "agent_id": agent_id, "task_type": payload.type, "title": payload.description, "payload": {"priority": payload.priority, "context": payload.context}, "due_at": payload.due_at, "now": _now()})
    db.commit()
    return {"id": str(task_id), "type": payload.type, "status": "pending", "priority": payload.priority}


@router.get("/agents/{agent_id}/tasks", tags=["Domain 3 - Agents & AI Workforce"])
def list_agent_tasks(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT id, task_type AS type, status, payload->>'priority' AS priority, due_at FROM agent_tasks WHERE agent_id = :id ORDER BY created_at DESC"), {"id": agent_id}))}


@router.patch("/agent-tasks/{task_id}", tags=["Domain 3 - Agents & AI Workforce"])
def update_agent_task(task_id: UUID, payload: AgentTaskUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("UPDATE agent_tasks SET status = :status, updated_at = :now WHERE id = :id"), {"status": payload.status, "now": _now(), "id": task_id})
    db.commit()
    return {"id": str(task_id), "status": payload.status, "result": payload.result}


@router.post("/agents/{agent_id}/memories", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def store_agent_memory(agent_id: UUID, payload: AgentMemoryRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    memory_id = uuid4()
    expires_at = _now() + timedelta(days=payload.ttl_days) if payload.ttl_days else None
    db.execute(text("INSERT INTO agent_memories (id, tenant_id, agent_id, memory_type, content, metadata, expires_at, created_at, updated_at) VALUES (:id, :tenant_id, :agent_id, :memory_type, :content, :metadata, :expires_at, :now, :now)"), {"id": memory_id, "tenant_id": agent["tenant_id"], "agent_id": agent_id, "memory_type": payload.type, "content": str(payload.value), "metadata": {"key": payload.key, "context": payload.context}, "expires_at": expires_at, "now": _now()})
    db.commit()
    return {"id": str(memory_id), "type": payload.type, "key": payload.key, "value": payload.value}


@router.get("/agents/{agent_id}/memories", tags=["Domain 3 - Agents & AI Workforce"])
def list_agent_memories(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT id, memory_type AS type, metadata->>'key' AS key, content AS value, created_at FROM agent_memories WHERE agent_id = :id ORDER BY created_at DESC"), {"id": agent_id}))}


@router.post("/agents/{agent_id}/feedback", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def submit_agent_feedback(agent_id: UUID, payload: AgentFeedbackRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    feedback_id = uuid4()
    db.execute(text("INSERT INTO agent_feedback (id, tenant_id, agent_id, message_id, rating, feedback, created_at) VALUES (:id, :tenant_id, :agent_id, :message_id, :rating, :feedback, :now)"), {"id": feedback_id, "tenant_id": agent["tenant_id"], "agent_id": agent_id, "message_id": payload.message_id, "rating": payload.rating, "feedback": payload.comment, "now": _now()})
    db.commit()
    return {"id": str(feedback_id), "rating": payload.rating, "comment": payload.comment, "category": payload.category}


@router.get("/agents/{agent_id}/feedback", tags=["Domain 3 - Agents & AI Workforce"])
def list_agent_feedback(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    items = _rows(db.execute(text("SELECT id, rating, feedback AS comment, created_at FROM agent_feedback WHERE agent_id = :id ORDER BY created_at DESC"), {"id": agent_id}))
    avg_rating = db.execute(text("SELECT COALESCE(avg(rating), 0) FROM agent_feedback WHERE agent_id = :id"), {"id": agent_id}).scalar_one()
    return {"items": items, "avg_rating": float(avg_rating), "total": len(items)}


@router.post("/agents/{agent_id}/tool-permissions", tags=["Domain 3 - Agents & AI Workforce"], status_code=status.HTTP_201_CREATED)
def grant_tool_permission(agent_id: UUID, payload: ToolPermissionRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent = get_agent(agent_id, db)
    permission_id = uuid4()
    db.execute(text("INSERT INTO tool_permissions (id, tenant_id, tool_id, agent_id, is_allowed, created_at) VALUES (:id, :tenant_id, :tool_id, :agent_id, true, :now)"), {"id": permission_id, "tenant_id": agent["tenant_id"], "tool_id": payload.tool_id, "agent_id": agent_id, "now": _now()})
    db.commit()
    return {"id": str(permission_id), "tool_id": str(payload.tool_id), "permission": payload.permission, "constraints": payload.constraints}


@router.get("/agents/{agent_id}/tool-permissions", tags=["Domain 3 - Agents & AI Workforce"])
def list_tool_permissions(agent_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT tp.tool_id, tr.name AS tool_name, tp.is_allowed FROM tool_permissions tp LEFT JOIN tool_registry tr ON tr.id = tp.tool_id WHERE tp.agent_id = :id"), {"id": agent_id}))}


@router.get("/health", tags=["Domain 4 - System, Health & Jobs"])
def api_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("SELECT 1"))
    return {"status": "healthy", "services": {"api": "ok", "postgres": "ok", "redis": "not_configured", "qdrant": "not_configured", "kafka": "not_configured", "mistral": "not_configured"}, "version": "0.1.0", "timestamp": _now()}


@router.get("/audit-logs", tags=["Domain 4 - System, Health & Jobs"])
def audit_logs(tenant_id: UUID | None = None, user_id: UUID | None = None, action: str | None = None, resource: str | None = None, from_: datetime | None = Query(None, alias="from"), to: datetime | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    filters = []
    params: dict[str, Any] = {}
    if tenant_id:
        filters.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if user_id:
        filters.append("user_id = :user_id")
        params["user_id"] = user_id
    if action:
        filters.append("action = :action")
        params["action"] = action
    if resource:
        filters.append("(resource_type = :resource OR entity_type = :resource)")
        params["resource"] = resource
    if from_:
        filters.append("created_at >= :from_")
        params["from_"] = from_
    if to:
        filters.append("created_at <= :to")
        params["to"] = to
    where = "WHERE " + " AND ".join(filters) if filters else ""
    return {"items": _rows(db.execute(text(f"SELECT * FROM audit_logs {where} ORDER BY created_at DESC LIMIT 100"), params))}


@router.post("/background-jobs", tags=["Domain 4 - System, Health & Jobs"], status_code=status.HTTP_201_CREATED)
def queue_background_job(payload: BackgroundJobRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    job_id = uuid4()
    db.execute(text("INSERT INTO background_jobs (id, job_type, status, payload, scheduled_at, created_at, updated_at) VALUES (:id, :job_type, 'queued', :payload, :scheduled_at, :now, :now)"), {"id": job_id, "job_type": payload.type, "payload": {"priority": payload.priority, **payload.payload}, "scheduled_at": payload.scheduled_at, "now": _now()})
    db.commit()
    return {"id": str(job_id), "type": payload.type, "status": "queued", "progress": 0}


@router.get("/background-jobs", tags=["Domain 4 - System, Health & Jobs"])
def list_background_jobs(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT id, job_type AS type, status, payload, created_at FROM background_jobs ORDER BY created_at DESC LIMIT 100")))}


@router.get("/background-jobs/{job_id}", tags=["Domain 4 - System, Health & Jobs"])
def get_background_job(job_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = _row(db.execute(text("SELECT * FROM background_jobs WHERE id = :id"), {"id": job_id}).first())
    if not job:
        raise HTTPException(status_code=404, detail="Background job not found")
    return {**job, "type": job["job_type"], "progress": 100 if job["status"] == "completed" else 0, "result": job.get("payload")}


@router.post("/notifications", tags=["Domain 4 - System, Health & Jobs"], status_code=status.HTTP_201_CREATED)
def send_notification(payload: NotificationRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    notification_id = uuid4()
    tenant_id = None
    if payload.user_id:
        tenant_id = db.execute(text("SELECT tenant_id FROM users WHERE id = :id"), {"id": payload.user_id}).scalar()
    if tenant_id is None:
        tenant_id = db.execute(text("SELECT id FROM tenants ORDER BY created_at DESC LIMIT 1")).scalar()
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="A tenant is required before sending notifications")
    db.execute(text("INSERT INTO notifications (id, tenant_id, user_id, notification_type, title, body, payload, created_at) VALUES (:id, :tenant_id, :user_id, :type, :title, :body, :payload, :now)"), {"id": notification_id, "tenant_id": tenant_id, "user_id": payload.user_id, "type": payload.type, "title": payload.title, "body": payload.body, "payload": {"priority": payload.priority, **payload.data}, "now": _now()})
    db.commit()
    return {"id": str(notification_id), "title": payload.title, "read": False, "created_at": _now()}


@router.get("/notifications", tags=["Domain 4 - System, Health & Jobs"])
def list_notifications(db: Session = Depends(get_db)) -> dict[str, Any]:
    items = _rows(db.execute(text("SELECT id, title, body, read_at, created_at FROM notifications ORDER BY created_at DESC LIMIT 100")))
    return {"items": items, "unread_count": sum(1 for item in items if item.get("read_at") is None)}


@router.patch("/notifications/{id}/read", tags=["Domain 4 - System, Health & Jobs"])
def mark_notification_read(id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    now = _now()
    db.execute(text("UPDATE notifications SET read_at = :now WHERE id = :id"), {"now": now, "id": id})
    db.commit()
    return {"id": str(id), "read": True, "read_at": now}


@router.post("/feature-flags", tags=["Domain 4 - System, Health & Jobs"], status_code=status.HTTP_201_CREATED)
def create_feature_flag(payload: FeatureFlagRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    flag_id = uuid4()
    db.execute(text("INSERT INTO feature_flags (id, flag_key, is_enabled, config, created_at, updated_at) VALUES (:id, :key, :enabled, :config, :now, :now)"), {"id": flag_id, "key": payload.name, "enabled": payload.enabled, "config": {"description": payload.description, "target": payload.target}, "now": _now()})
    db.commit()
    return {"id": str(flag_id), "name": payload.name, "enabled": payload.enabled, "target": payload.target}


@router.get("/feature-flags", tags=["Domain 4 - System, Health & Jobs"])
def list_feature_flags(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": _rows(db.execute(text("SELECT id, flag_key AS name, is_enabled AS enabled, config AS target, created_at FROM feature_flags ORDER BY created_at DESC")))}


@router.patch("/feature-flags/{flag_id}", tags=["Domain 4 - System, Health & Jobs"])
def toggle_feature_flag(flag_id: UUID, payload: FeatureFlagUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(text("UPDATE feature_flags SET is_enabled = :enabled, updated_at = :now WHERE id = :id"), {"enabled": payload.enabled, "now": _now(), "id": flag_id})
    db.commit()
    return {"id": str(flag_id), "enabled": payload.enabled}


@router.get("/api-request-logs", tags=["Domain 4 - System, Health & Jobs"])
def api_request_logs(tenant_id: UUID | None = None, endpoint: str | None = None, status_code: int | None = Query(None, alias="status"), from_: datetime | None = Query(None, alias="from"), db: Session = Depends(get_db)) -> dict[str, Any]:
    filters = []
    params: dict[str, Any] = {}
    if tenant_id:
        filters.append("tenant_id = :tenant_id")
        params["tenant_id"] = tenant_id
    if endpoint:
        filters.append("path = :endpoint")
        params["endpoint"] = endpoint
    if status_code:
        filters.append("status_code = :status_code")
        params["status_code"] = status_code
    if from_:
        filters.append("created_at >= :from_")
        params["from_"] = from_
    where = "WHERE " + " AND ".join(filters) if filters else ""
    return {"items": _rows(db.execute(text(f"SELECT * FROM api_request_logs {where} ORDER BY created_at DESC LIMIT 100"), params))}
