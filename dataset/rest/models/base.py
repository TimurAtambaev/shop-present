"""Модуль базовых моделей."""
from pydantic import BaseModel


class BaseResponseModel(BaseModel):
    """Пидантик модель Response'а."""

    content: str
