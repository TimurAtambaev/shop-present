"""Модуль с моделями для профиля."""
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import File, Form, HTTPException
from pydantic import BaseModel, validator
from starlette import status

from dataset.config import settings
from dataset.rest.models.images import UploadCloudModel
from dataset.rest.models.types import TGUrl
from dataset.rest.models.utils import as_form
from dataset.rest.views.utils import get_phone_info


@as_form
class ProfileModel(UploadCloudModel):
    """Модель формы редактирования профиля."""

    name: Optional[str] = Form(...)
    surname: Optional[str] = Form(...)
    birth_date: Optional[date] = Form(None)
    phone: Optional[str] = Form(None)
    country_id: Optional[int] = Form(...)
    avatar: UploadCloudModel.get_type() = File(None)
    telegram: Optional[TGUrl] = Form(None)

    @validator("birth_date")
    def validate_birth_date(cls, value: datetime) -> Optional[date]:
        """Валидация возраста."""
        if value is None or value <= (
            datetime.now().date() - timedelta(days=settings.AGE)
        ):
            return value
        raise ValueError("Age must be > or = 18 years")

    @validator("phone")
    def validate_phone_number(cls, value: str) -> Optional[str]:
        """Валидация номера телефона."""
        if value is None or (
            settings.PHONE_NUMBER_MAX
            >= len(value)
            >= settings.PHONE_NUMBER_MIN
        ):
            return value
        raise ValueError("Check the number of characters")


class ProfileChangePassword(BaseModel):
    """Модель изменения пароля пользователя."""

    old_password: str
    password: str
    password_repeat: str

    @validator("password")
    def validate_password(cls, value: str) -> str:
        """Валидация пароля."""
        if len(value) >= settings.LEN_PASSWORD:
            return value
        raise ValueError("Password must be > 8 symbols")

    @validator("password_repeat")
    def validate_password_repeat(cls, value: str, values: Any) -> str:
        """Валидация повтора пароля."""
        if value != values["password"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        return value


class ProfileResetPassword(BaseModel):
    """Модель сброса и обновления пароля пользователя."""

    reset_token: str
    password: str

    @validator("password")
    def validate_password(cls, value: str) -> str:
        """Валидация пароля."""
        if len(value) >= settings.LEN_PASSWORD:
            return value
        raise ValueError("Password must be > 8 symbols")


class ProfileInfo(BaseModel):
    """Модель данных пользователя."""

    id: int  # noqa A003
    name: str
    surname: Optional[str]
    avatar: Optional[str]
    country_id: Optional[int]
    refer_code: Optional[str]
    phone: Optional[str]
    verified_email: Optional[str]
    birth_date: Optional[date]
    paid_till: Optional[date]
    trial_till: Optional[datetime]
    is_vip: Optional[bool]
    telegram: Optional[TGUrl]
    has_active_dream: Optional[bool]
    is_active: Optional[bool]
    is_female: Optional[bool]
    language: Optional[str]

    class Config:
        """Класс с настройками."""

        orm_mode = True

    def dict(self, *args: tuple, **kwargs: dict) -> dict:  # noqa A003
        """Добавление кодов стран в выдачу."""
        data = super().dict(*args, **kwargs)
        data["phone_info"] = get_phone_info(data.get("phone"))
        return data


class LanguageModel(BaseModel):
    """Модель выбора языка."""

    language: str
