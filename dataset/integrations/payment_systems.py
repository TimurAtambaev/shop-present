"""Модуль с платежными для работы с платежными системами."""
import sys
from abc import ABC
from typing import Union
from urllib.parse import urlencode

from fastapi import HTTPException
from loguru import logger
from paypalcheckoutsdk.core import (
    LiveEnvironment,
    PayPalHttpClient,
    SandboxEnvironment,
)
from paypalcheckoutsdk.orders import OrdersCreateRequest
from paypalhttp import HttpError
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse

from dataset.config import settings
from dataset.migrations import db
from dataset.rest.models.donation import DonationSystem, FreeDonationSystem
from dataset.tables.currency import Currency
from dataset.tables.donation import Donation
from dataset.tables.payment_data import BasePaymentData, PayPalPaymentData
from dataset.tables.user import User

logger.add(sys.stdout, format="[{time:HH:mm:ss}, level=DEBUG]")


class BasePaymentSys(ABC):  # noqa: B024  TODO пофиксить наследование
    """Базовый класс платежных систем."""

    async def make_transfer(
        self,
        request: Request,
        payment: BasePaymentData,
        donation: Donation,
        data,  # noqa ANN001
        *args: tuple,
        **kwargs: dict,
    ) -> None:
        """Совершить перевод."""
        # TODO дубль логики с ручным донатом
        recipient: User = await User.get(donation.recipient_id)
        await User.update.values(referer=recipient.refer_code).where(
            User.id == donation.sender_id
        ).gino.status()

    async def handle_callback(self, *args: tuple, **kwargs: dict) -> None:
        """Обработать callback от системы."""
        raise NotImplementedError

    @classmethod
    async def pre_init(cls) -> None:  # noqa: B027
        """Метод pre_init."""  # TODO Методя для будущих платёжных систем
        pass


class PayPal(BasePaymentSys):
    """Класс для работы с Paypal."""

    client_id = settings.PAYPAL_CLIENT_ID
    client_secret = settings.PAYPAL_CLIENT_SECRET
    environment = SandboxEnvironment(
        client_id=settings.PAYPAL_CLIENT_ID,
        client_secret=settings.PAYPAL_CLIENT_SECRET,
    )
    if settings.PAYPAL_PROD:
        environment = LiveEnvironment(
            client_id=settings.PAYPAL_CLIENT_ID,
            client_secret=settings.PAYPAL_CLIENT_SECRET,
        )

    client = PayPalHttpClient(environment)

    async def create_order(
        self,
        amount: Union[int, float],
        currency_code: str,
        recipient: str,
        donation_id: int,
        data_donate: DonationSystem,
        req: Request,
    ) -> JSONResponse:
        """Создать заявку в системе paypal."""
        request = OrdersCreateRequest()
        request.prefer("return=representation")
        amount_with_commission = round(amount * settings.WITH_COMISSION, 2)
        data = {
            "intent": "CAPTURE",
            "application_context": {
                "return_url": f"{data_donate.redirect_url}"
                f'?{urlencode({"success": True})}',
                "cancel_url": f"{data_donate.redirect_url}"
                f'?{urlencode({"success": False})}',
            },
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency_code,
                        "value": str(amount_with_commission),
                    },
                    "payee": {"email_address": recipient},
                    "custom_id": str(donation_id),
                }
            ],
        }
        if data_donate.sender_dream_id:
            donation_count = await (
                db.select([db.func.count()])
                .where(Donation.sender_id == req.user.id)
                .gino.scalar()
            )
            is_first_donate = donation_count == 1
            success_redir = urlencode(
                {
                    "success": True,
                    "first_donate": is_first_donate,
                    "dream_id": (data_donate.sender_dream_id),
                }
            )
            data["application_context"]["return_url"] = (
                f"{data_donate.redirect_url}" f"?{success_redir}"
            )
        request.request_body(data)
        try:
            links = self.client.execute(request).result.links
            redir_link = {link.rel: link.href for link in links}.get(
                "approve", ""
            )
            return JSONResponse({"url": redir_link})
        except IOError as ioe:
            logger.debug(data)
            if isinstance(ioe, HttpError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=ioe.message
                )

    async def make_transfer(
        self,
        request: Request,
        payment: PayPalPaymentData,
        donation: Donation,
        data: [DonationSystem, FreeDonationSystem],
        *args: tuple,
        **kwargs: dict,
    ):  # noqa ANN201
        """Метод для переводов."""
        await super().make_transfer(
            request,
            payment,
            donation,
            data,
            *args,
            **kwargs,
        )
        sender = await User.get(donation.sender_id)
        sender_course = (await Currency.get(settings.EURO_ID)).course
        sender_currency_code = settings.EURO_CODE
        if sender:
            sender_currency_code = (
                await Currency.get(sender.currency_id)
            ).code
            sender_course = (await Currency.get(sender.currency_id)).course
        elif data.currency_id:
            sender_currency_code = (await Currency.get(data.currency_id)).code
            sender_course = (await Currency.get(data.currency_id)).course
        if sender_currency_code in settings.PAYPAL_CURRENCIES:
            amount = donation.first_amount / settings.FINANCE_RATIO
        else:
            # Если пэйпал не поддерживает валюту отправителя, переводим в евро
            amount = donation.first_amount / sender_course
            sender_currency_code = settings.EURO_CODE
        return await self.create_order(
            amount,
            sender_currency_code,
            payment.recipient,
            donation.id,
            data,
            request,
        )


SYSTEMS = {"paypal": PayPal}
