"""Модуль с моделями валют."""
from pydantic import BaseModel

from dataset.rest.views.hooks import ConvertDisplay


class CurrenciesModel(BaseModel):
    """Модель списка валют для пользователя."""

    id: int  # noqa A003
    code: str
    symbol: str
    name: str

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class CurrencyModel(BaseModel):
    """Модель валюты."""

    id: int  # noqa A003
    code: str
    symbol: str
    name: str
    course: ConvertDisplay
    sort_number: int
    is_active: bool
    dream_limit: int

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class CurrencyIdModel(BaseModel):
    """Модель для изменения валюты."""

    currency_id: int
