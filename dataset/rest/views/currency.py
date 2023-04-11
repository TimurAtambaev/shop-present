"""Модуль с представлениями валют."""
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.gino import paginate
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import Float, and_, cast
from starlette import status
from starlette.responses import Response

from dataset.config import settings
from dataset.migrations import db
from dataset.rest.models.currency import (
    CurrenciesModel,
    CurrencyIdModel,
    CurrencyModel,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.tables.currency import Currency
from dataset.tables.donate_size import DonateSize
from dataset.tables.donation import Donation
from dataset.tables.dream import Dream
from dataset.tables.user import User

router = InferringRouter()


async def recalculation(
    user_id: int, old_currency_id: int, currency_id: int
) -> None:
    """Перерасчет всех полученных пользователем донатов.

    Собранных средств на мечты,
    размеров мечт в соответствии с выбранной валютой.
    """
    old_course = (
        await Currency.query.where(Currency.id == old_currency_id).gino.first()
    ).course
    current_course = (
        await Currency.query.where(Currency.id == currency_id).gino.first()
    ).course
    ratio = current_course / old_course
    await Donation.update.values(
        amount=Donation.amount * cast(ratio, Float),
        currency_id=currency_id,
    ).where(Donation.recipient_id == user_id).gino.status()
    await Dream.update.values(
        collected=Dream.collected * cast(ratio, Float),
        goal=Dream.goal * cast(ratio, Float),
        currency_id=currency_id,
    ).where(Dream.user_id == user_id).gino.status()


@cbv(router)
class CurrencyView(BaseView):
    """Класс для работы с валютами."""

    @router.get("/currencies", response_model=Page[CurrenciesModel])
    async def get_all_currencies(
        self, params: Params = Depends()  # noqa B008
    ) -> AbstractPage:
        """Получить список валют для пользователя."""
        return await paginate(
            Currency.query.where(
                Currency.is_active == True  # noqa E712
            ).order_by(Currency.sort_number),
            params,
        )

    @router.get("/currency", response_model=CurrencyModel)
    async def get_currency(
        self, currency_id: Optional[int] = None
    ) -> Currency:
        """Получить данные по валюте пользователя."""
        if self.request.user:
            currency_id = self.request.user.currency_id
        return await self.check_currency(currency_id)

    async def check_currency(self, currency_id):  # noqa ANN201
        currency = await Currency.get(currency_id)
        if not currency:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        if not currency.is_active:
            return Response(
                content="currency is not active",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return currency

    @router.get("/user-currency/{user_id}", response_model=CurrencyModel)
    async def get_currency_by_user(self, user_id: int) -> Currency:
        """Получить валюту пользователя."""
        user = await User.query.where(
            and_(User.id == user_id, User.is_active == True)  # noqa E712
        ).gino.first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        currency_by_user_id = await Currency.query.where(
            and_(
                Currency.id == user.currency_id,
                Currency.is_active == True,  # noqa E712
            )
        ).gino.first()
        if not currency_by_user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency_by_user_id

    @router.patch(
        "/change-currency", dependencies=[Depends(AuthChecker(is_auth=True))]
    )
    async def change_currency(self, currency: CurrencyIdModel) -> dict:
        """Метод для изменения валюты авторизованного пользователя."""
        currency_id = currency.currency_id
        await self.check_currency(currency_id)
        old_currency_id = self.request.user.currency_id
        async with db.transaction():
            await self.request.user.update(currency_id=currency_id).apply()
            await recalculation(
                self.request.user.id, old_currency_id, currency_id
            )
        return {"result": True}

    @router.get("/donate-size")
    async def get_donate_sizes(
        self, currency_id: Optional[int] = None
    ):  # noqa ANN201
        """Получить данные по размерам донатов для валюты пользователя."""
        if self.request.user:
            currency_id = self.request.user.currency_id
        if not currency_id:
            return Response(
                content="currency_id required",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        donate_sizes = (
            await DonateSize.query.where(DonateSize.currency_id == currency_id)
            .order_by(DonateSize.level)
            .gino.all()
        )
        return sorted(
            [size.size / settings.FINANCE_RATIO for size in donate_sizes],
            reverse=True,
        )
