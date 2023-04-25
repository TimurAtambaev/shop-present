"""Модуль с pydantic-моделями наборов жителей."""
from datetime import date, datetime
from typing import List, Optional

from fastapi import HTTPException
from loguru import logger
from pydantic import BaseModel, validator
from starlette import status


class CitizenModel(BaseModel):
    """Модель информации о жителе."""

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

    @validator("birth_date")
    def validate_birth_date(cls, birth_date: str) -> datetime:
        """Валидация и перевод даты рождения в формат datetime."""
        try:
            clean_birth_date = datetime.strptime(birth_date, "%d.%m.%Y")
            if clean_birth_date > datetime.now():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="incorrect birth date"
                )
        except ValueError as exc:
            logger.error(exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="incorrect birth date format, use DD.MM.YYYY"
            )
        return clean_birth_date


class ImportCitizenModel(BaseModel):
    """Модель загрузки наборов жителей."""

    citizens: List[CitizenModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ChangeCitizenModel(BaseModel):
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


class ResponseCitizenModel(BaseModel):
    """Модель жителя для ответа."""

    citizen_id: int
    town: str
    street: str
    building: str
    apartment: int
    name: str
    birth_date: str
    gender: str
    relatives: list

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ResponseCitizensModel(BaseModel):
    """Модель набора жителей для ответа."""

    data: List[ResponseCitizenModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True
