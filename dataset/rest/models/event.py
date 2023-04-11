"""Модуль с моделями для событий."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserEventModel(BaseModel):
    """Модель пользователя для событий."""

    id: Optional[int]  # noqa A003
    name: Optional[str]
    surname: Optional[str]
    country_id: Optional[int]
    avatar: Optional[str]

    class Config:
        """Класс с настройками."""

        orm_mode = True


class DreamEventModel(BaseModel):
    """Модель мечты для событий."""

    id: int  # noqa A003
    picture: Optional[str]
    status: int
    title: str

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class DonateEventModel(BaseModel):
    """Модель донатов для событий."""

    id: int  # noqa A003
    first_amount: int
    status: int
    confirmed_at: Optional[datetime]

    class Config:
        """Класс с настройками."""

        orm_mode = True


class CurrencyEventModel(BaseModel):
    """Модель валюты донатов для событий."""

    symbol: str

    class Config:
        """Класс с настройками."""

        orm_mode = True


class EventModel(BaseModel):
    """Модель событий."""

    id: Optional[int]  # noqa A003
    type_event: Optional[str]
    created_at: Optional[datetime]
    is_read: Optional[bool]
    data: Optional[dict]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class EventDreamModel(BaseModel):
    """Базовая модель ивента мечты."""

    user: UserEventModel
    dream: DreamEventModel


class EventDonateModel(BaseModel):
    """Базовая модель ивента доната."""

    user: UserEventModel
    dream: DreamEventModel
    sender: UserEventModel
    donation: DonateEventModel
    currency: CurrencyEventModel


class EventConfirmDonateModel(BaseModel):
    """Базовая модель ивента подтверждающего доната."""

    user: UserEventModel
    sender: UserEventModel


class EventNewPersonModel(EventConfirmDonateModel):
    """Базовая модель нового пользователя."""
