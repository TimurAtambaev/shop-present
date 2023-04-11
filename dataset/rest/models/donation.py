"""Модуль с моделями для донатов."""
from datetime import date, datetime
from mimetypes import guess_type
from typing import List, Optional, Union

from fastapi import File, Form, HTTPException
from pydantic import BaseModel, validator
from starlette import status
from starlette.datastructures import UploadFile

from dataset.config import settings
from dataset.rest.models.dream import ResponseDreamUsPmModel
from dataset.rest.models.images import ReceiptUploadCloudModel
from dataset.rest.models.recaptcha import FreeDonateTokenModel, TokenModel
from dataset.rest.models.types import UploadFileOrLink
from dataset.rest.models.utils import as_form
from dataset.rest.views.hooks import ConvertDisplay, ConvertOperation


class DonationCost(BaseModel):
    """Модель стоимости доната."""

    donation: int


class ReferalDonation(BaseModel):
    """Модель реферальных донатов."""

    id: int  # noqa A003
    status: int
    receipt: Optional[str]
    first_amount: ConvertDisplay
    dream: ResponseDreamUsPmModel

    class Config:
        """Класс с настройками."""

        orm_mode = True


class DonationModel(BaseModel):
    """Модель доната."""

    first_amount: ConvertDisplay
    currency_id: int
    status: int
    receipt: Optional[str]

    class Config:
        """Класс с настройками."""

        orm_mode = True


class DreamForDonationModel(BaseModel):
    """Модель мечты для доната."""

    title: Optional[str]
    language: Optional[str]
    id: Optional[int]  # noqa A003
    updated_at: Optional[datetime]

    class Config:
        """Класс с настройками."""

        orm_mode = True


@as_form
class RequestDonation(ReceiptUploadCloudModel):
    """Модель доната."""

    sender_dream_id: Optional[int] = Form(None)
    currency_id: Optional[int] = Form(None)

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True

    @staticmethod
    def validate_reciept(
        v: Union[UploadFile, str]
    ) -> Optional[Union[UploadFile, str]]:
        """Валидация квитанции."""
        if not v:
            return None
        type_image = [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.oasis.opendocument.spreadsheet",
            "text/csv",
            "application/vnd.ms-excel",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.oasis.opendocument.text",
            "application/pdf",
            "text/plain",
            "application/rtf",
            "application/vnd.openxmlformats-officedocument.presentationml.template",
            "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.oasis.opendocument.graphics",
            "application/vnd.ms-powerpoint",
            "image/jpeg",
            "image/jpg",
            "image/png",
        ]
        if isinstance(v, str):
            content_type = guess_type(v)[0]
        else:
            content_type = getattr(v, "content_type")  # noqa B009
        if content_type not in type_image:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        funcs = {
            UploadFile: lambda: RequestDonation.upload_file(v),
            str: lambda: v,
        }
        if func := funcs.get(type(v)):
            return func()
        raise ValueError(f"The {type(v)} type is not supported")

    receipt: UploadFileOrLink(validator=validate_reciept) = File(...)


@as_form
class RequestFreeDonation(RequestDonation, FreeDonateTokenModel):
    """Модель свободного доната."""

    amount: int = Form(...)

    @validator("amount")
    def validate_amount(cls, v: int) -> int:
        """Валидация размера доната."""
        if v <= 0:
            raise ValueError("Amount must be positive value")
        return v * settings.FINANCE_RATIO  # todo переделать в единую точку


class UserForDonationModel(BaseModel):
    """Модель юзера для доната."""

    id: int  # noqa A003
    name: Optional[str]
    surname: Optional[str]
    refer_code: Optional[str]
    country_id: Optional[int]
    avatar: Optional[str]
    refer_code: Optional[str]

    class Config:
        """Класс с настройками."""

        orm_mode = True


class AllDonationModel(BaseModel):
    """Модель всех донатов."""

    id: int  # noqa A003
    status: int
    first_amount: int
    first_currency_id: int
    symbol: str
    recipient_type: Optional[bool]
    receipt: Optional[str]
    confirmed_at: Optional[date]
    dream: Optional[DreamForDonationModel]
    recipient: Optional[UserForDonationModel]
    sender: Optional[UserForDonationModel]
    level_number: Optional[int]
    receipt: Optional[str]

    class Config:
        """Класс с настройками."""

        arbitrary_types_allowed = True
        orm_mode = True


class IntervalModel(BaseModel):
    """Модель статистики донатов по временным интервалам."""

    sum: Optional[int]  # noqa A003
    count: Optional[int]


class DonationStatisticsModel(BaseModel):
    """Модель статистики донатов по уровням."""

    count: Optional[int]
    sum: Optional[int]  # noqa A003
    level: Optional[int]


class GeneralStatisticsModel(BaseModel):
    """Модель общей статистики по донатам."""

    day: Optional[IntervalModel]
    week: Optional[IntervalModel]
    month: Optional[IntervalModel]
    donat_stat: Optional[List[DonationStatisticsModel]]


class DonationSystem(BaseModel):
    """Модель для доната через платежную систему."""

    id: int  # noqa A003
    type: str  # noqa A003
    system: str  # paypal
    payment_id: int
    redirect_url: str
    sender_dream_id: Optional[int]


class FreeDonationSystem(DonationSystem, TokenModel):
    """Модель для свободного доната через платежную систему."""

    amount: ConvertOperation
    currency_id: int


class ResponseDonateSize(BaseModel):
    """Модель размеров донатов."""

    size: ConvertDisplay

    class Config:
        """Класс с настройками."""

        orm_mode = True
