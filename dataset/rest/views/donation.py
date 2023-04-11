"""Модуль с представлениями для работы с донатами."""
from datetime import datetime
from typing import List, Optional, Union

from fastapi import Depends, HTTPException
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import and_, func, or_
from sqlalchemy.dialects.postgresql import Any
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dataset.config import settings
from dataset.integrations.payment_systems import SYSTEMS, BasePaymentSys
from dataset.migrations import db
from dataset.rest.models.donation import (
    AllDonationModel,
    DonationCost,
    DonationModel,
    DonationStatisticsModel,
    DonationSystem,
    FreeDonationSystem,
    GeneralStatisticsModel,
    ReferalDonation,
    RequestDonation,
    RequestFreeDonation,
    ResponseDonateSize,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.custom_paginate import custom_paginate, paginate_qs
from dataset.rest.views.dream import get_translation_dream
from dataset.rest.views.event_tasks import (
    event_confirm_donate,
    event_donate,
    event_dream,
    event_new_person,
)
from dataset.rest.views.utils import (
    activate_another_dream,
    donate_notice_email,
    get_ratio,
    handle_error,
    read_one_event,
    send_notification,
)
from dataset.tables.currency import Currency
from dataset.tables.donate_size import DonateSize
from dataset.tables.donation import Donation, DonationLevel, DonationStatus
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.event import TypeEvent
from dataset.tables.payment_data import BasePaymentData
from dataset.tables.user import User
from dataset.utils.user import user_has_subscribe

router = InferringRouter()
Recipient: User = User.alias()
Sender: User = User.alias()


async def filter_dreams(
    referer: Optional[str] = None,
    dream_title: Optional[str] = None,
    sender_name: Optional[str] = None,
    amount: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_before: Optional[datetime] = None,
    confirm: Optional[bool] = None,
    sender_id: Optional[int] = None,
    recipient_id: Optional[int] = None,
    level_number: Optional[int] = None,
) -> List:
    """Метод с фильтрацией."""
    query_data = [
        (
            referer,
            or_(Sender.refer_code == referer, Recipient.refer_code == referer),
        ),
        (dream_title, Dream.title.ilike(f"%{dream_title}%")),
        (sender_name, Sender.name.ilike(f"%{sender_name}%")),
        (amount, Donation.first_amount == amount),
        (date_from, Donation.confirmed_at >= date_from if date_from else None),
        (
            date_before,
            Donation.confirmed_at <= date_before if date_before else None,
        ),
        (
            confirm,
            Donation.confirmed_at != None  # noqa E711
            if confirm
            else None
            if confirm is None
            else and_(
                Donation.confirmed_at.is_(None),
                Donation.status != DonationStatus.NEW.value,
            ),
        ),
        (
            sender_id,
            and_(
                Donation.sender_id == sender_id,  # отправленные донаты
                Donation.status  # исключаем не оплаченные реферальные донаты и донаты не прошедшие через PayPal
                != DonationStatus.NEW.value,
            ),
        ),
        (recipient_id, Donation.recipient_id == recipient_id),
        (level_number, Donation.level_number == level_number),
    ]
    return [fil for val, fil in query_data if val is not None]


async def recalc_donate(donation: Donation, currency_id: int) -> None:
    """Пересчет первоначальной суммы существующего доната."""
    first_amount = (
        await DonateSize.query.where(
            and_(
                DonateSize.currency_id == currency_id,
                DonateSize.level == donation.level_number,
            )
        ).gino.first()
    ).size
    await donation.update_w_cnt(
        first_currency_id=currency_id, first_amount=first_amount
    )


@cbv(router)
class DreamView(BaseView):
    """Представление мечты."""

    @router.get(
        "/donations/{dream_id}/{user_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=DonationCost,
    )
    async def get_dream_donation(self, dream_id: int, user_id: int) -> dict:
        """Получить донат."""
        dream = await Dream.get(dream_id)
        if not dream or user_id not in dream.dreams:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return {"donation": dream.dreams[user_id]}

    class ModifiedParams(Params):
        """Расширенный класс параметров."""

        donation_id: int = -1

    @router.get(
        "/donations/my",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=Page[AllDonationModel],
    )
    async def get_my_donations(
        self,
        params: ModifiedParams = Depends(),  # noqa B008
        data: dict = Depends(filter_dreams),  # noqa B008
    ) -> Union[AbstractPage, dict]:
        """Получение списка донатов пользователя."""
        query = (
            Donation.join(Currency, Currency.id == Donation.first_currency_id)
            .outerjoin(Sender, Sender.id == Donation.sender_id)
            .outerjoin(Recipient, Recipient.id == Donation.recipient_id)
            .outerjoin(Dream, Donation.dream_id == Dream.id)
            .select()
            .where(
                or_(
                    Donation.recipient_id == self.request.user.id,
                    Donation.sender_id == self.request.user.id,
                )
            )
            .order_by(Donation.confirmed_at.desc())
        )
        if data:
            query = query.where(and_(*data))

        donations = query.gino.load(
            Donation.distinct(Donation.id).load(
                dream=Dream,
                recipient=Recipient,
                sender=Sender,
                symbol=Currency.symbol,
            )
        ).query
        que = donations.where(
            or_(
                Dream.status == DreamStatus.ACTIVE.value,
                Dream.status == DreamStatus.CLOSED.value,
            )
        ).order_by(Donation.first_amount)
        result = await paginate_qs(que, params=params)
        if not result:
            return await custom_paginate(result, params=params)

        # TODO отрефакторить
        first = await que.where(Donation.id == params.donation_id).gino.first()
        if first:
            ind = [
                result.index(item)
                for item in result
                if item.id == params.donation_id
            ]
            (result.insert(0, result.pop(ind[0]) if ind else first))
        page = await custom_paginate(result, params=params)
        result = page.dict()
        # Перевод размера доната в реальный для отображения пользователю
        for item in result["items"]:
            translation = await get_translation_dream(
                item["dream"], self.request["language"]
            )
            item["dream"]["title"] = translation["title"]
            item["recipient_type"] = (
                item["recipient"]["id"] == self.request.user.id
            )
            item["first_amount"] /= settings.FINANCE_RATIO
        return result

    @router.get(
        "/donations/{donation_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=DonationModel,
    )
    async def get_donation(self, donation_id: int) -> Donation:
        """Получение информации по донату."""
        donation = await Donation.query.where(
            and_(
                or_(
                    Donation.recipient_id == self.request.user.id,
                    Donation.sender_id == self.request.user.id,
                ),
                Donation.id == donation_id,
            )
        ).gino.first()
        if not donation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return donation

    async def check_refer_donation(self, recipient_id: int) -> None:
        """Проверка возможности задонатить собственному рефералу."""
        recipient: User = await User.get(recipient_id)
        if (
            recipient.referer
            and self.request.user.refer_code
            and recipient.referer == self.request.user.refer_code
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    @router.get(
        "/size-ref-donation/{donation_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=ResponseDonateSize,
    )
    async def get_size_ref_donation(
        self, donation_id: int
    ) -> ResponseDonateSize:
        """Получение актуального размера реферального доната.

        В соответствии с текущей валютой отправителя и уровнем доната.
        """
        donation = await Donation.get(donation_id)
        if not donation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if not donation.level_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="not referal donate",
            )
        return await DonateSize.query.where(
            and_(
                DonateSize.currency_id == self.request.user.currency_id,
                DonateSize.level == donation.level_number,
            )
        ).gino.first()

    @router.patch(
        "/donations/{donation_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def donate_by_id(
        self,
        donation_id: int,
        data: RequestDonation = Depends(RequestDonation.as_form),  # noqa B008
    ) -> dict:
        """Задонатить по существующему донату."""
        donation = await Donation.get(donation_id)

        if not donation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Пересчитываем первоначальную сумму совершаемого доната если
        # пользователь после формирования реферальных донатов изменил валюту
        first_amount = (
            await DonateSize.query.where(
                and_(
                    DonateSize.currency_id == self.request.user.currency_id,
                    DonateSize.level == donation.level_number,
                )
            ).gino.first()
        ).size
        async with db.transaction():
            await donation.update_w_cnt(
                first_currency_id=self.request.user.currency_id,
                first_amount=first_amount,
                receipt=data.receipt,
                status=DonationStatus.WAITING_FOR_CONFIRMATION.value,
            )
            donation_recipient = await User.get(donation.recipient_id)
            donation_dream = await Dream.get(donation.dream_id)
            currency = await Currency.get(donation.first_currency_id)
        await event_donate(
            donation_recipient,
            self.request.user,
            donation_dream,
            donation,
            currency,
        )
        await send_notification(
            self.request.app.state.redis, donation.recipient_id, True
        )
        await donate_notice_email(
            donation_recipient.email,
            donation_recipient.name,
            self.request.app,
            donation_recipient.language,
        )

        return {
            "receipt": data.receipt,
            "status": DonationStatus.WAITING_FOR_CONFIRMATION,
        }

    @router.post(
        "/donations/dreams/{dream_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={201: {}, 404: {}},
    )
    async def donate_by_dream(
        self,
        dream_id: int,
        data: RequestDonation = Depends(RequestDonation.as_form),  # noqa B008
    ):  # noqa ANN201
        """Задонатить по мечте."""
        dream = await Dream.get(dream_id)
        if not dream:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if self.request.user.referer:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        await self.check_refer_donation(dream.user_id)

        user_for_donation = await User.get(dream.user_id)
        donation_level = DonationLevel.REFERAL.value
        currency_id = self.request.user.currency_id
        sender_amount = (
            await DonateSize.query.where(
                and_(
                    DonateSize.currency_id == currency_id,
                    DonateSize.level == donation_level,
                )
            ).gino.first()
        ).size
        sender_dream = await Dream.get(data.sender_dream_id)
        ratio = await get_ratio(currency_id, dream.user_id)
        recipient_amount = sender_amount * ratio
        async with db.transaction():
            donation = await Donation.create(
                status=DonationStatus.WAITING_FOR_CONFIRMATION.value,
                receipt=data.receipt,
                dream_id=dream_id,
                recipient_id=dream.user_id,
                amount=recipient_amount,
                level_number=donation_level,
                sender_id=self.request.user.id,
                currency_id=currency_id,
                first_currency_id=currency_id,
                first_amount=sender_amount,
            )
            await sender_dream.update(ref_donations=[donation.id]).apply()
            recipient: User = await User.get(donation.recipient_id)
            await User.update.values(referer=recipient.refer_code).where(
                User.id == donation.sender_id
            ).gino.status()
        dream_user = await User.get(dream.user_id)
        currency = await Currency.get(donation.first_currency_id)
        await event_donate(
            dream_user, self.request.user, dream, donation, currency
        )
        await event_new_person(
            dream_user,
            self.request.user,
            type_event=TypeEvent.PARTICIPANT.value,
        )
        await send_notification(
            self.request.app.state.redis, dream.user_id, True
        )
        donation_count = await (
            db.select([db.func.count()])
            .where(Donation.sender_id == self.request.user.id)
            .gino.scalar()
        )
        if sender_dream and sender_dream.status == DreamStatus.QUART.value:
            await sender_dream.update(status=DreamStatus.HALF.value).apply()
            await User.update.values(
                referer=user_for_donation.refer_code
            ).where(User.id == donation.sender_id).gino.status()
        await Dream.update.values(status=DreamStatus.HALF.value).where(
            and_(
                Dream.user_id == self.request.user.id,
                Dream.status == DreamStatus.QUART.value,
            )
        ).gino.status()
        await donate_notice_email(
            recipient.email,
            recipient.name,
            self.request.app,
            recipient.language,
        )
        if donation_count == 1:
            return JSONResponse(
                {"first_donate": True}, status_code=status.HTTP_201_CREATED
            )
        return JSONResponse({}, status_code=status.HTTP_201_CREATED)

    @router.post("/donate", dependencies=[Depends(AuthChecker(is_auth=True))])
    @handle_error
    async def donate(
        self, request: Request, data: DonationSystem
    ):  # noqa ANN201
        """Задонатить по используя платежную систему."""
        donation = None
        system: BasePaymentSys = SYSTEMS.get(data.system)
        if is_supported_type := (data.type == "dream"):
            dream = await Dream.get(data.id)
            currency_id = self.request.user.currency_id
            donation_level = DonationLevel.REFERAL.value
            sender_amount = (
                await DonateSize.query.where(
                    and_(
                        DonateSize.currency_id == currency_id,
                        DonateSize.level == donation_level,
                    )
                ).gino.first()
            ).size
            ratio = await get_ratio(currency_id, dream.user_id)
            recipient_amount = sender_amount * ratio
            donation = await Donation.create(
                timeout=None,
                status=DonationStatus.NEW.value,
                dream_id=data.id,
                recipient_id=dream.user_id,
                amount=recipient_amount,
                level_number=DonationLevel.REFERAL.value,
                sender_id=self.request.user.id,
                currency_id=currency_id,
                first_currency_id=currency_id,
                first_amount=sender_amount,
            )
            await (
                Dream.update.values(ref_donations=[donation.id])
                .where(Dream.id == data.sender_dream_id)
                .gino.status()
            )
            dream_user = User.get(dream.user_id)
            currency = Currency.get(donation.first_currency_id)
            await event_donate(
                dream_user, self.request.user, dream, donation, currency
            )
            await send_notification(
                self.request.app.state.redis, dream.user_id, True
            )
        elif is_supported_type := (data.type == "donation"):
            donation = await Donation.get(data.id)
            await recalc_donate(donation, self.request.user.currency_id)
        if not all((system, donation, is_supported_type)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        payment = await BasePaymentData.get(data.payment_id)
        return await system().make_transfer(request, payment, donation, data)

    @router.get(
        "/receipt/donations/{donation_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def get_receipt(self, donation_id: int) -> Optional[str]:
        """Получить чек по донату."""
        donation = await Donation.get(donation_id)

        if not donation:
            return None

        return donation.receipt

    @router.get(
        "/donation-statistics/{dream_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=GeneralStatisticsModel,
    )
    async def get_donation_statistics(self, dream_id: int) -> dict:
        """Получение статистики по донатам."""
        query_receipts = f"""
        SELECT SUM(amount), COUNT(*)
          FROM donation
         WHERE donation.recipient_id = {self.request.user.id}
           AND donation.dream_id = {dream_id}
           AND donation.confirmed_at >= (NOW() - INTERVAL"""
        donation = await db.all(
            db.text(
                f"""
            {query_receipts}'1 DAY')
             UNION ALL {query_receipts}'7 DAY')
             UNION ALL {query_receipts}'30 DAY');"""
            )
        )
        donat_stat = await db.all(
            db.text(
                f"""
                SELECT COUNT(*), SUM(amount), level_number
                  FROM donation
                 WHERE recipient_id = {self.request.user.id}
                   AND donation.dream_id = {dream_id}
                   AND confirmed_at IS NOT NULL
              GROUP BY level_number;
                             """
            )
        )
        donation_day, donation_week, donation_month = donation
        donations_day = (
            None
            if donation_day[0] is None
            else donation_day[0] / settings.FINANCE_RATIO
        )
        donations_week = (
            None
            if donation_week[0] is None
            else donation_week[0] / settings.FINANCE_RATIO
        )
        donations_month = (
            None
            if donation_month[0] is None
            else donation_month[0] / settings.FINANCE_RATIO
        )
        for num, donat in enumerate(donat_stat):
            count, stat_sum, level = donat
            if stat_sum is not None:
                stat_sum = stat_sum / settings.FINANCE_RATIO
                donat_stat[num] = DonationStatisticsModel(
                    count=count, sum=stat_sum, level=level
                )
        return {
            "day": {"sum": donations_day, "count": donation_day[1]},
            "week": {"sum": donations_week, "count": donation_week[1]},
            "month": {"sum": donations_month, "count": donation_month[1]},
            "donat_stat": donat_stat,
        }

    @router.post(
        "/confirm-donation/{donation_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def confirm_donation(self, donation_id: int):  # noqa ANN201
        """Запрос для подтверждения донатов."""
        donation = await self.confirm_donate(donation_id)

        await self.update_dream(donation)
        await self.change_dream_status(donation)
        return Response(status_code=status.HTTP_200_OK)

    async def confirm_donate(self, donation_id: int) -> Donation:
        """Подтверждение доната."""
        donate = await (
            Donation.query.where(
                and_(
                    Donation.id == donation_id,
                    Donation.recipient_id == self.request.user.id,
                    Donation.status
                    == DonationStatus.WAITING_FOR_CONFIRMATION.value,
                )
            ).gino.first()
        )
        if not donate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await donate.update_w_cnt(
            confirmed_at=datetime.now(), status=DonationStatus.CONFIRMED.value
        )
        await event_confirm_donate(sender=self.request.user, donation=donate)
        await read_one_event(
            self.request.app.state.redis, self.request.user, True
        )
        await send_notification(self.request.app.state.redis, donate.sender_id)
        return donate

    async def update_dream(self, donate: Donation) -> None:
        """Обновление мечты."""
        dream = await Dream.get(donate.dream_id)
        (
            await Dream.update.values(
                collected=Dream.collected + donate.amount
            )
            .where(Dream.id == donate.dream_id)
            .gino.status()
        )
        dream_closed = await (
            Dream.update.values(
                status=DreamStatus.CLOSED.value, closed_at=func.now()
            )
            .where(
                and_(
                    Dream.id == donate.dream_id,
                    (dream.collected + donate.amount) >= dream.goal,
                    dream.status == DreamStatus.ACTIVE.value,
                )
            )
            .gino.status()
        )
        if dream_closed[0] == "UPDATE 1":
            user = await User.get(dream.user_id)
            await activate_another_dream(user)
            await event_dream(
                user=self.request.user,
                dream=dream,
                type_event=TypeEvent.EXECUTE.value,
            )
            await send_notification(self.request.app.state.redis, user.id)

    async def change_dream_status(self, donation: Donation) -> Optional[int]:
        """Изменение статуса мечты, если все донаты подтверждены."""
        dream_sender = await (
            Dream.query.where(
                Any(donation.id, Dream.ref_donations)
            ).gino.first()
        )
        if not dream_sender:
            return  # noqa R502
        query = Donation.query.where(
            and_(
                Donation.id.in_(dream_sender.ref_donations),
                Donation.confirmed_at != None,  # noqa E711
            )
        )
        donation_count = (
            await func.count()
            .select()
            .select_from(query.alias())
            .gino.scalar()
        )
        if dream_sender.status == DreamStatus.QUART.value:
            await dream_sender.update(status=DreamStatus.HALF.value).apply()
        if donation_count == settings.NEED_TO_DONATE_NUM:
            (
                await dream_sender.update(
                    status=DreamStatus.THREE_QUARTERS.value
                ).apply()
            )

        return donation_count

    @router.get(
        "/donation/ref/{donation_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=List[ReferalDonation],
    )
    async def get_ref_donate(self, donation_id: int) -> Donation:
        """Запрос для информации по реф донату."""
        return (
            await Donation.join(Currency)
            .outerjoin(User, User.id == Donation.recipient_id)
            .outerjoin(Dream, Dream.id == Donation.dream_id)
            .select()
            .where(Donation.id == donation_id)
            .gino.load(
                Donation.load(
                    symbol=Currency.symbol, dream=Dream.load(user=User)
                )
            )
            .query.order_by(Donation.first_amount.desc())
            .gino.all()
        )

    @router.post("/free-donate/pay-pal")
    @handle_error
    async def free_donate_paypal(
        self, request: Request, data: FreeDonationSystem
    ) -> None:
        """Задонатить по используя платежную систему."""
        donation = None
        system: BasePaymentSys = SYSTEMS.get(data.system)
        if is_supported_type := (data.type == "dream"):
            dream = await Dream.get(data.id)
            if not dream:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="dream_not_found",
                )
            ratio = await get_ratio(data.currency_id, dream.user_id)
            recipient_amount = data.amount * ratio
            donation = await Donation.create(
                timeout=None,
                status=DonationStatus.WAITING_FOR_CONFIRMATION.value,
                dream_id=data.id,
                recipient_id=dream.user_id,
                amount=recipient_amount,
                currency_id=data.currency_id,
                first_currency_id=data.currency_id,
                first_amount=data.amount,
                sender_id=self.request.user.id if self.request.user else None,
            )
        elif is_supported_type := (data.type == "donation"):
            donation = await Donation.get(data.id)
            dream = await Dream.get(donation.dream_id)
            if not donation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="donation_not_found",
                )
            await recalc_donate(donation, data.currency_id)

        recipient = await User.get(dream.user_id)
        currency = await Currency.get(data.currency_id)
        await event_donate(
            recipient,
            self.request.user if self.request.user else None,
            dream,
            donation,
            currency,
        )
        await send_notification(
            self.request.app.state.redis, dream.user_id, True
        )
        if not all((system, donation, is_supported_type)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        payment = await BasePaymentData.get(data.payment_id)
        return await system().make_transfer(request, payment, donation, data)

    @router.post(
        "/free-donate/{dream_id}",
        responses={201: {}, 404: {}},
    )
    async def free_donate(
        self,
        dream_id: int,
        data: RequestFreeDonation = Depends(  # noqa B008
            RequestFreeDonation.as_form,
        ),  # noqa B008
    ):  # noqa ANN201
        """Свободный донат по мечте."""
        dream = await Dream.get(dream_id)
        if not dream or dream.status != DreamStatus.ACTIVE.value:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        user = await User.get(dream.user_id)
        if not user_has_subscribe(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        currency_id = data.currency_id or settings.EURO_ID
        if self.request.user:
            currency_id = self.request.user.currency_id
        ratio = await get_ratio(currency_id, dream.user_id)
        recipient_amount = data.amount * ratio
        recipient = await User.get(dream.user_id)
        async with db.transaction():
            donation = await Donation.create(
                status=DonationStatus.WAITING_FOR_CONFIRMATION.value,
                receipt=data.receipt,
                dream_id=dream_id,
                recipient_id=dream.user_id,
                amount=recipient_amount,
                sender_id=self.request.user.id if self.request.user else None,
                currency_id=currency_id,
                first_currency_id=currency_id,
                first_amount=data.amount,
            )
            currency = await Currency.get(donation.first_currency_id)
            await event_donate(
                recipient,
                self.request.user if self.request.user else None,
                dream,
                donation,
                currency,
            )
            await send_notification(
                self.request.app.state.redis, dream.user_id, True
            )
        await donate_notice_email(
            recipient.email,
            recipient.name,
            self.request.app,
            recipient.language,
        )
        return JSONResponse({}, status_code=status.HTTP_201_CREATED)
