"""Модуль с моделями для работы с пользователями."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class User(BaseModel):
    """Модель юзера."""

    id: Optional[int]  # noqa A003
    name: Optional[str]
    surname: Optional[str]
    avatar: Optional[str]
    refer_count: Optional[int]
    refer_code: Optional[str]
    country_id: Optional[int]
    paid_till: Optional[date]
    trial_till: Optional[datetime]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True
