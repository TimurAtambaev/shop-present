"""Модуль с моделями для админки."""
from datetime import datetime
from typing import List, Optional, Union

from fastapi import File, Form
from pydantic import BaseModel, constr, validator
from starlette.datastructures import UploadFile

from dataset.config import settings
from dataset.rest.models.category import Category
from dataset.rest.models.donation import UserForDonationModel
from dataset.rest.models.images import UploadCloudModel
from dataset.rest.models.user import User
from dataset.rest.models.utils import as_form
from dataset.rest.views.hooks import ConvertDisplay, ConvertOperation


@as_form
class AdminNews(UploadCloudModel):
    """Модель создания/обновления новости."""

    title: str = Form(...)
    language: Optional[str] = Form("")
    markup_text: Optional[str] = Form("")
    is_published: Optional[bool] = Form(False)
    text: str = Form(...)
    published_date: str = Form(...)
    tags: Optional[list[str]] = Form([])
    cover_url: UploadCloudModel.get_type() = File(None)

    @validator("cover_url")
    def validate_cover_url(
        cls, value: Union[UploadFile, str]
    ) -> Union[UploadFile, str, None]:
        """Валидация изображения новостей без сжатия."""
        if value is None:
            return value
        return UploadCloudModel.validate_picture(value, compress=False)

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True


class SpecialUsers(BaseModel):
    """Модель пользователя для списка."""

    id: Optional[int]  # noqa A003
    name: Optional[str]
    surname: Optional[str]
    status: Optional[list]


class ResponseSpecialUsersModel(BaseModel):
    """Модель пользователей для ответа."""

    items: List[SpecialUsers]
    total: int
    page: int
    size: int


class VipStatus(BaseModel):
    """Модель изменения вип-статуса."""

    user_id: int
    is_vip: bool

    class Config:
        """Класс с настройками."""

        orm_mode = True


class AdminListDream(BaseModel):
    """Модель списка мечт в админке."""

    id: int  # noqa A003
    created_at: datetime
    closed_at: Optional[datetime]
    title: str
    category: Category
    user: User
    collected: int
    symbol: str
    status: int
    description: str
    picture: str
    type_dream: str

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class AdminDetailDream(AdminListDream):
    """Модель мечты из админки."""

    description: str
    picture: str
    goal: ConvertDisplay
    collected: ConvertDisplay
    symbol: str
    currency_id: int


@as_form
class AdminDream(UploadCloudModel):
    """Модель для создания мечты из панели администратора."""

    title: constr(max_length=settings.LEN_DREAM_TITLE) = Form(...)
    user_id: int = Form(...)
    description: str = Form(...)
    category_id: int = Form(...)
    goal: int = Form(...)
    type_dream: str = Form(...)
    picture: UploadCloudModel.get_type() = File(None)

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True

    @validator("goal")
    def validate_goal(cls, v: int) -> int:
        """Валидация суммы мечты."""
        if v < 0:
            raise ValueError("The amount cannot be less than zero")
        return v * settings.FINANCE_RATIO  # todo переделать в единую точку


class AdminListDonation(BaseModel):
    """Модель списка донатов в админке."""

    id: int  # noqa A003
    first_amount: int
    first_currency_id: int
    symbol: str
    status: int
    created_at: datetime
    sender: Optional[UserForDonationModel]
    recipient: UserForDonationModel

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class DonationSize(BaseModel):
    """Модель размеров донатов."""

    level: int
    size: ConvertOperation

    class Config:
        """Класс с настройками."""

        orm_mode = True


class ResponseDonationSize(BaseModel):
    """Модель размеров донатов."""

    level: int
    size: int

    class Config:
        """Класс с настройками."""

        orm_mode = True


class AdminListCurrencies(BaseModel):
    """Модель списка валют в админке."""

    id: int  # noqa A003
    code: str
    symbol: str
    name: str
    course: float
    sort_number: int
    is_active: bool
    dream_limit: int
    donate_sizes: List[ResponseDonationSize]

    class Config:
        """Класс с настройками."""

        orm_mode = True

    def dict(self, *args: tuple, **kwargs: dict) -> dict:  # noqa A003
        """Добавление поля с размерами валют.

        В виде отсортированного массива для фронта.
        """
        data = super().dict(*args, **kwargs)
        data["sizes"] = sorted(
            [donate_size["size"] for donate_size in data["donate_sizes"]],
            reverse=True,
        )
        return data


class AdminCurrencyModel(BaseModel):
    """Модель для создания и редактирования валют в админке."""

    code: str
    symbol: str
    name: str
    course: ConvertOperation
    sort_number: int
    donation_sizes: List[DonationSize]
    is_active: bool
    dream_limit: int

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True


class SubscribeTillModel(BaseModel):
    """Модель изменения срока окончания подписки пользователя."""

    subscribe_till: str
