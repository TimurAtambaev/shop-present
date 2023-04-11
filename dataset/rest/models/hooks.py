"""Модуль с моделями хуков."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, validator


class UserUpdate(BaseModel):
    """Модель обновленного юзера."""

    ufandao_id: Optional[int]
    imrix_id: Optional[int]
    dream_id: Optional[int] = None
    user_valid_till: Optional[date] = None
    user_trial_till: Optional[datetime] = None

    @validator("user_valid_till")
    def validate_user_valid_till(cls, v, values, **kwargs):  # noqa
        """Валидация даты."""
        if not v or v >= datetime.now().date():
            return v
        raise ValueError("the date has expired")
