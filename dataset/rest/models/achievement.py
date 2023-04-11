"""Модуль с моделями достижений."""
from datetime import date
from typing import Optional

from pydantic import BaseModel


class AchievementModel(BaseModel):
    """Модель достижения."""

    id: int  # noqa A003
    user_id: int
    title: str
    description: str
    type_name: str


class ResponseAchievementModel(BaseModel):
    """Модель достижения для ответа."""

    id: int  # noqa A003
    user_id: int
    title: str
    description: str
    type_name: str
    received_at: Optional[date]

    class Config:
        """Класс с настройками."""

        orm_mode = True
