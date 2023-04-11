"""Модуль с моделями для мечт."""
from datetime import datetime
from typing import List, Optional

from fastapi import File, Form
from pydantic import BaseModel, constr, validator

from dataset.config import settings
from dataset.rest.models.images import UploadCloudModel
from dataset.rest.models.recaptcha import TokenModelLanding
from dataset.rest.models.types import UploadFileOrLink
from dataset.rest.models.user import User
from dataset.rest.models.utils import as_form
from dataset.rest.views.hooks import ConvertOperation


@as_form
class DreamModel(UploadCloudModel):
    """Модель мечты."""

    title: constr(max_length=settings.LEN_DREAM_TITLE) = Form(...)
    description: str = Form(...)
    category_id: int = Form(...)
    goal: int = Form(...)
    picture: UploadCloudModel.get_type() = File(...)
    language: Optional[str] = Form(None)

    @validator("goal")
    def validate_goal(cls, v: int) -> int:
        """Валидация размера мечты."""
        if v <= 0:
            raise ValueError("You exceed the limit")
        return v * settings.FINANCE_RATIO  # todo переделать в единую точку

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True


@as_form
class CharityDreamModel(DreamModel):
    """Модель благотворительной мечты."""

    currency_id: int = Form(...)

    @validator("goal")
    def validate_goal(cls, v: int) -> int:
        """Валидация размера мечты."""
        if v > settings.CHARITY_DREAM_LIMIT or v <= 0:
            raise ValueError("You exceed the limit")
        return v * settings.FINANCE_RATIO  # todo переделать в единую точку


class ResponseDreamModel(BaseModel):
    """Модель мечты для ответа."""

    id: int  # noqa A003
    title: Optional[str]
    description: Optional[str]
    category_id: Optional[int]
    status: Optional[int]
    picture: Optional[str]
    user_id: Optional[int]
    collected: Optional[int]
    goal: Optional[int]
    type_dream: str
    donations_count: Optional[int]
    symbol: Optional[str]
    ref_donations: Optional[list]
    update_: Optional[bool]
    delete_: Optional[bool]
    support_dreams: Optional[bool]
    updated_at: Optional[datetime]
    failed_translate: Optional[bool]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class DreamListUserItem(BaseModel):
    """Модель юзера для списка мечт."""

    id: Optional[int]  # noqa A003
    name: Optional[str]
    surname: Optional[str]
    avatar: Optional[str]
    refer_count: Optional[int]
    country_id: Optional[int]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ResponseDreamListItem(BaseModel):
    """Модель мечты для списка мечт пользователей."""

    id: int  # noqa A003
    title: Optional[str]
    description: Optional[str]
    category_id: Optional[int]
    status: Optional[int]
    picture: Optional[str]
    type_dream: str
    donations_count: Optional[int]
    symbol: Optional[str]
    ref_donations: Optional[list]
    user_id: Optional[int]
    user: Optional[DreamListUserItem]
    failed_translate: Optional[bool]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class ResponseDreamUsPmModel(ResponseDreamModel):
    """Модель мечты с пользователем и достижением для ответа."""

    user: Optional[User]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class PaginateDreamsList(BaseModel):
    """Модель списка мечт участников."""

    items: List[ResponseDreamListItem]
    total: int
    page: int
    size: int

    class Config:
        """Класс с настройками."""

        orm_mode = True


@as_form
class DreamDraftModel(DreamModel):
    """Модель черновика мечты."""

    title: str = Form(...)
    description: str = Form("")
    category_id: int = Form(...)
    goal: int = Form(None)
    picture: UploadFileOrLink(
        validator=UploadCloudModel.validate_picture
    ) = File(...)

    @validator("goal")
    def validate_goal(cls, value: int) -> Optional[int]:
        """Валидация размера мечты."""
        if value is None:
            return value
        if value < 0:
            raise ValueError("Goal must be positive value")
        return value * settings.FINANCE_RATIO  # todo переделать в единую точку


class DreamSettingsModel(BaseModel):
    """Модель настроек лимита мечты для админа."""

    dream_limit: Optional[int]

    class Config:
        """Класс с настройками."""

        orm_mode = True


class DreamFormModel(TokenModelLanding):
    """Модель формы мечты на лендинге."""

    name: str
    title: str
    description: str
    goal: ConvertOperation
    email: str
    currency_id: int

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True


class ResponseOneDreamModel(BaseModel):
    """Модель для страницы отдельной мечты."""

    id: int  # noqa A003
    title: Optional[str]
    description: Optional[str]
    category_id: Optional[int]
    status: Optional[int]
    picture: Optional[str]
    user_id: Optional[int]
    type_dream: str
    user: Optional[User]
    failed_translate: Optional[bool]


class ResponseDreamCurrencyModel(ResponseOneDreamModel):
    """Модель для страницы отдельной мечты с валютой текущего пользователя."""

    currency_code: str
    currency_symbol: str
    dream_goal: int
    dream_collected: int
    support_dream: bool


class ResponseDreamLimitModel(BaseModel):
    """Модель лимита мечты со знаком валюты для ответа."""

    dream_limit: int
    symbol: str

    class Config:
        """Класс с настройками."""

        orm_mode = True


class EmailCodeModel(BaseModel):
    """Модель формы мечты."""

    code: str

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True


class ResponseModalWindowModel(BaseModel):
    """Модель модального окна для ответа."""

    show: bool


@as_form
class DreamChangeModel(DreamDraftModel):
    """Модель редактирования мечты."""

    description: str = Form(...)
    goal: int = Form(...)

    @validator("goal")
    def validate_goal(cls, v: int) -> int:
        """Валидация размера мечты."""
        if v <= 0:
            raise ValueError("You exceed the limit")
        return v * settings.FINANCE_RATIO  # todo переделать в единую точку
