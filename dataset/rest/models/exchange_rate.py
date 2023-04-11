"""Модуль с моделями для курсов валют."""
from pydantic import BaseModel


class ExchangeRate(BaseModel):
    """Модель курса валют за день."""

    rate: float
