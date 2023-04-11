"""Модуль с моделями для реф."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, validator


class Referal(BaseModel):
    """Модель рефералов."""

    ref_code: str = ""
    sub_dream_id: int = ""
    dream_id: int = None

    @validator("dream_id")
    def validate_dream_id_pair(
        cls,
        v: int,
        values: Any,
        **kwargs: Dict,
    ) -> int:
        """Проваилидировать парность полей поля."""
        if not bool(values.get("ref_code")) ^ bool(values.get("sub_dream_id")):
            raise ValueError(
                "Expected only one, either `ref_code` or `sub_dream_id`"
                " in pair with dream_id"
            )
        return v


class UserForMyComminity(BaseModel):
    """Модель юзера для списка фандрайзеров."""

    id: Optional[int]  # noqa A003
    level: Optional[int]
    name: Optional[str]
    avatar: Optional[str]


class PaginateMyCommunity(BaseModel):
    """Модель списка фандрайзеров пользователя."""

    items: List[UserForMyComminity]
    total: int
    page: int
    size: int

    class Config:
        """Класс с настройками."""

        orm_mode = True


class UserReferal(BaseModel):
    """Модель юзера получаемая по реферальному коду."""

    name: str
    surname: Optional[str]
    country_id: Optional[int]
    avatar: Optional[str]
    verified_email: str

    class Config:
        """Класс с настройками."""

        orm_mode = True


class EmailReferal(BaseModel):
    """Модель для отправки реферального кода."""

    email: str

    class Config:
        """Класс с настройками."""

        orm_mode = True


class UserModel(BaseModel):
    """Модель пользователя для списка."""

    id: int  # noqa A003
    name: Optional[str]
    surname: Optional[str]
    avatar: Optional[str]
    country_id: Optional[str]
    level: Optional[int]
    confirm_donate: Optional[bool]


class ResponseUsersModel(BaseModel):
    """Модель списка пользователей для ответа."""

    items: List[UserModel]
    total: int
    page: int
    size: int
