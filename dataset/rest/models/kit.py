"""Модуль с моделями наборов жителей."""
from typing import List, Optional
from pydantic import BaseModel


class KitModel(BaseModel):
    """Модель набора жителей."""

    citizen_id: int
    town: str
    street: str
    building: str
    apartment: int
    name: str
    birth_date: str
    gender: str
    relatives: list
    import_id: int = None

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ImportKitModel(BaseModel):
    """Модель загрузки наборов жителей."""

    citizens: List[KitModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ChangeKitModel(BaseModel):
    """Модель изменения информации о жителе."""

    town: Optional[str]
    street: Optional[str]
    building: Optional[str]
    apartment: Optional[int]
    name: Optional[str]
    birth_date: Optional[str]
    gender: Optional[str]
    relatives: Optional[list]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True