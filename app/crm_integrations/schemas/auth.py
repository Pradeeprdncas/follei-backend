from typing import Any
from pydantic import BaseModel, Field, model_validator


USERNAME_ALIASES = ("email", "login_email", "loginEmail", "userName")


def normalize_username_alias(data: Any) -> Any:
    if not isinstance(data, dict) or "username" in data:
        return data
    for alias in USERNAME_ALIASES:
        if alias in data:
            return {**data, "username": data[alias]}
    return data


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def accept_username_aliases(cls, data: Any) -> Any:
        return normalize_username_alias(data)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def accept_username_aliases(cls, data: Any) -> Any:
        return normalize_username_alias(data)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class AuthUser(BaseModel):
    id: int
    username: str
    authenticated: bool = True


class RegisterResponse(BaseModel):
    id: int
    username: str


class LogoutResponse(BaseModel):
    message: str
