"""Модуль с моделями наборов жителей."""
from datetime import date
from typing import List
from pydantic import BaseModel


class KitModel(BaseModel):
    """Модель набора жителей."""
    citizen_id: int
    town: str
    street: str
    building: str
    apartment: int
    name: str
    birth_date: date
    gender: str
    relatives: list

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ImportKitModel(BaseModel):
    """Модель для загрузки набора жителей."""

    citizens: List[KitModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True
