"""Модуль с pydantic-моделями наборов жителей."""
from datetime import date, datetime
from typing import List, Optional

from fastapi import HTTPException
from loguru import logger
from pydantic import BaseModel, validator, root_validator
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

    @root_validator(pre=True)
    def check_citizen_values(cls, values):
        if not any(values):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="request data cannot be empty"
            )
        return values


class CitizenModel(BaseModel):
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


class ResponseCitizenModel(BaseModel):
    """Модель данных жителя для ответа."""

    data: CitizenModel

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ResponseKitModel(BaseModel):
    """Модель набора жителей для ответа."""

    data: List[CitizenModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ResponsePercentileModel(BaseModel):
    """Модель статистики по перцентилям по городу для ответа."""

    town: str
    p50: float
    p75: float
    p99: float

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ResponsePercentilesModel(BaseModel):
    """Модель статистики по перцентилям для ответа."""

    data: List[ResponsePercentileModel]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True