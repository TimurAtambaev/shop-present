"""Модуль с моделью Country."""
from typing import Optional

from pydantic import BaseModel


class Country(BaseModel):
    """Модель категории."""

    country_id: int
    title: str
    code: Optional[str]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True

    def dict(self, *args: tuple, **kwargs: dict) -> dict:  # noqa A003
        """Переопределен метод для вывода данных по стране."""
        country = super().dict(*args, **kwargs)
        country["id"] = country.pop("country_id")
        return country
