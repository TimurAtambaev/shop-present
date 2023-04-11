"""Модуль с моделями для авторизации/регистрации."""
from typing import Optional

from pydantic import BaseModel, Field

from dataset.config import settings
from dataset.rest.models.recaptcha import TokenModel
from dataset.rest.models.types import TGUrl


class TokenPair(BaseModel):
    """Модель пары access/refresh токенов."""

    access: str
    refresh: str
    commentoCommenterToken: Optional[str]  # noqa N815


class BaseAuth(BaseModel):
    """Модель авторизации."""

    username: str
    password: str


class Auth(BaseAuth, TokenModel):
    """Модель авторизации."""


class AdminAuth(BaseAuth):
    """Модель авторизации оператора."""


class Registration(TokenModel):
    """Модель регистрации."""

    country: int
    email: str
    is_age_offer_acceptance_status: bool
    is_offer_acceptance_status: bool
    name: str = Field(..., min_length=settings.LEN_NAME)
    surname: str = Field(..., min_length=settings.LEN_NAME)
    password: str = Field(..., min_length=settings.LEN_PASSWORD)
    password_repeat: str = Field(..., min_length=settings.LEN_PASSWORD)
    referer: Optional[str]
    telegram: Optional[TGUrl]


class ConfirmToken(BaseModel):
    """Модель токена подтверждения регистрации."""

    token: str
