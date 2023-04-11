"""Модуль с моделью токена для капчи."""
from typing import ClassVar, Optional

import requests
from fastapi import Form
from pydantic import BaseModel, validator

from dataset.config import settings


class BaseTokenModel(BaseModel):
    """Базовая модель токена для капчи."""

    re_token: str = ""
    _recaptcha_secret_key: ClassVar

    @validator("re_token")
    def validate_re_token(cls, value: str) -> None:
        """Валидация токена рекаптчи."""
        if settings.GS_ENVIRONMENT in ("test", "dev"):
            return
        payload = {"secret": cls._recaptcha_secret_key, "response": value}

        response = requests.post(settings.RECAPTCHA_API_SERVER, data=payload)
        result = response.json()
        if not result.get("success", False):
            raise ValueError(f"Wrong token. Error: {result}.")


class TokenModel(BaseTokenModel):
    """Модель токена для капчи."""

    _recaptcha_secret_key = settings.RECAPTCHA_SECRET_KEY_REGISTER


class TokenModelLanding(BaseTokenModel):
    """Модель токена для капчи лендинга."""

    _recaptcha_secret_key = settings.RECAPTCHA_SECRET_KEY_LANDING


class FreeDonateTokenModel(BaseTokenModel):
    """Модель токена рекапчи для свободного доната."""

    re_token: Optional[str] = Form("")
    _recaptcha_secret_key = settings.RECAPTCHA_SECRET_KEY_REGISTER
