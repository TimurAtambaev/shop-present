"""Модуль с моделями реквизитов."""
from typing import Any, List, Optional

import phonenumbers
from fastapi import HTTPException
from pydantic import BaseModel, validator
from starlette import status

from dataset.config import settings
from dataset.rest.views.utils import get_phone_info


class EmptyPayment(BaseModel):
    """Базовая пустая модель реквизита."""

    class Config:
        """Класс с настрйоками."""

        orm_mode = True


class BasePaymentData(EmptyPayment):
    """Общая модель оплаты."""

    type: int  # noqa A003
    recipient: Optional[str]
    card_number: Optional[str]
    bank: Optional[str]
    country_id: Optional[int]
    dream_id: int
    account_num: Optional[str]
    comment: Optional[str]
    phone_num: Optional[str]
    is_preference: Optional[bool]
    wallet_id: Optional[int]
    wallet_data: Optional[str]
    token: Optional[str]
    network: Optional[str]
    address: Optional[str]

    def dict(self, *args: tuple, **kwargs: dict):  # noqa A003
        """Добавление кодов стран в выдачу."""
        data = super().dict(*args, **kwargs)
        data["phone_info"] = get_phone_info(data.get("phone_num"))
        return data


class ResponseBasePaymentData(BasePaymentData):
    """Базовый ответ реквизитов."""

    id: int  # noqa A003


class RequestBankPaymentData(EmptyPayment):
    """Модель банковской оплаты."""

    type: int  # noqa A003
    dream_id: int
    recipient: str
    card_number: str
    bank: str
    country_id: int
    comment: Optional[str]


class RequestEPaymentData(EmptyPayment):
    """Модель электронной оплаты."""

    type: int  # noqa A003
    dream_id: int
    wallet_id: int
    wallet_data: str
    comment: Optional[str]


class RequestMobilePaymentData(EmptyPayment):
    """Модель мобильной оплаты."""

    type: int  # noqa A003
    dream_id: int
    recipient: str
    phone_num: str
    comment: str

    @validator("phone_num")
    def validate_phone_num(cls, v: str, values: Any, **kwargs: Any) -> str:
        """Валидация телефонного номера."""
        try:
            phone = phonenumbers.parse(f"+{v}")
        except Exception:
            raise ValueError("Wrong phone format")
        if v and phonenumbers.is_valid_number(phone):
            return v
        raise ValueError("Wrong phone format")


class RequestCustomPaymentData(EmptyPayment):
    """Модель кастомной оплаты."""

    type: int  # noqa A003
    dream_id: int
    recipient: str
    comment: str


class ResponsePaymentModel(EmptyPayment):
    """Модель реквизита для ответа."""

    id: Optional[int]  # noqa A003
    title: Optional[str]
    payments: List[ResponseBasePaymentData]


class RequestPayPalPaymentData(EmptyPayment):
    """Модель оплаты paypal."""

    type: int  # noqa A003
    dream_id: int
    recipient: str
    comment: Optional[str]


class RequestCryptoPaymentData(EmptyPayment):
    """Модель оплаты криптовалютой."""

    type: int  # noqa A003
    dream_id: int
    token: str
    network: str
    address: str
    comment: Optional[str]

    @validator("token")
    def validate_token(
        cls,
        value: str,
        values: Any,
        **kwargs: Any,
    ) -> Optional[str]:
        """Валидация поля token криптовалюты."""
        if not value or 3 > len(value) > settings.LEN_CRYPTO_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid token value",
            )
        return value

    @validator("network")
    def validate_network(
        cls,
        value: str,
        values: Any,
        **kwargs: Any,
    ) -> Optional[str]:
        """Валидация поля network криптовалюты."""
        if not value or 3 > len(value) > settings.LEN_CRYPTO_NETWORK:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid network value",
            )
        return value

    @validator("address")
    def validate_address(
        cls,
        value: str,
        values: Any,
        **kwargs: Any,
    ) -> Optional[str]:
        """Валидация поля address криптовалюты."""
        if not value or 3 > len(value) > settings.LEN_CRYPTO_ADDRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid address value",
            )
        return value
