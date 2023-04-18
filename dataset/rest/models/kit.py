"""Модуль с pydantic-моделями наборов жителей."""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, validator


class RezidentModel(BaseModel):
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

    citizens: List[RezidentModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ChangeRezidentModel(BaseModel):
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


class ResponseRezidentModel(BaseModel):
    """Модель набора жителей для ответа."""

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

    @validator("birth_date")
    def validate_birth_date(cls, birth_date: date) -> str:
        """Перевод даты рождения в требуемый строковый формат."""
        return birth_date.strftime("%d.%m.%Y")
