"""Модуль с моделями для интеграции с фб."""
from typing import Any

from pydantic import BaseModel, ValidationError, validator


class FacebookModel(BaseModel):
    """Общая модель для интеграции с фб."""

    token: str


class FacebookRegistrationModel(FacebookModel):
    """Модель для регистрации через фб."""

    adult: bool = False
    privacy_policy: bool = False

    @validator("adult")
    def adult_check(cls, v: bool, values: Any, **kwargs: Any) -> bool:
        """Валидация возраста."""
        if not v:
            raise ValidationError("You must be an adult")

        return v

    @validator("privacy_policy")
    def privacy_policy_check(cls, v: bool, values: Any, **kwargs: Any) -> bool:
        """Валидация ознакомления с политикой приватности."""
        if not v:
            raise ValidationError("Please read our policy")

        return v
