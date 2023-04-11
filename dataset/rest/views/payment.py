"""Модуль с реквизитами."""
import datetime
from typing import List

from fastapi import Depends, Response
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import and_, func
from sqlalchemy.orm import Query
from starlette import status
from starlette.exceptions import HTTPException

from dataset.config import settings
from dataset.migrations import db
from dataset.rest.models.payment import (
    BasePaymentData as RequestBasePaymentData,
)
from dataset.rest.models.payment import (
    RequestBankPaymentData,
    RequestCryptoPaymentData,
    RequestCustomPaymentData,
    RequestEPaymentData,
    RequestMobilePaymentData,
    RequestPayPalPaymentData,
    ResponseBasePaymentData,
    ResponsePaymentModel,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.custom_paginate import custom_paginate
from dataset.rest.views.profile import get_active_dream_info
from dataset.rest.views.utils import recount_refs
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.payment_data import BankPaymentData
from dataset.tables.payment_data import (
    BasePaymentData as ModelBasePaymentData,
)
from dataset.tables.payment_data import (
    CryptoPaymentData,
    CustomPaymentData,
    EPaymentData,
    MobilePaymentData,
    PaymentType,
    PayPalPaymentData,
)
from dataset.tables.user import User
from dataset.utils.user import user_has_subscribe

router = InferringRouter()


@cbv(router)
class PaymentView(BaseView):
    """Представление для работы с реквизитами."""

    LAST_PAYMENT: int = 1
    data = {
        PaymentType.BANK.value: (BankPaymentData, RequestBankPaymentData),
        PaymentType.E_PAY.value: (EPaymentData, RequestEPaymentData),
        PaymentType.MOBILE.value: (
            MobilePaymentData,
            RequestMobilePaymentData,
        ),
        PaymentType.CUSTOM.value: (
            CustomPaymentData,
            RequestCustomPaymentData,
        ),
        PaymentType.PAYPAL.value: (
            PayPalPaymentData,
            RequestPayPalPaymentData,
        ),
        PaymentType.CRYPTO.value: (
            CryptoPaymentData,
            RequestCryptoPaymentData,
        ),
    }

    def get_related_payments(self) -> Query:
        """Получение реквизитов связанных с мечтой."""
        query = Dream.outerjoin(ModelBasePaymentData).select()
        loader = Dream.distinct(Dream.id).load(
            add_payment=ModelBasePaymentData
        )
        return query.gino.load(loader).query

    @router.get(
        "/payment",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=Page[ResponsePaymentModel],
    )
    async def get_all_payment(
        self, params: Params = Depends()  # noqa B008
    ) -> AbstractPage:
        """Получение всех реквизитов мечты."""
        result = self.get_related_payments()
        count_query = result.with_only_columns((Dream.id,)).alias()
        total = (
            await db.select(
                [db.func.count(db.func.distinct(count_query.c.id))]
            )
            .select_from(count_query)
            .gino.scalar()
        )
        return await custom_paginate(result, total, params)

    @router.get(
        "/payment/my",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=Page[ResponsePaymentModel],
    )
    async def get_my_payment(
        self, params: Params = Depends()  # noqa B008
    ) -> AbstractPage:
        """Получение своих реквизитов мечты."""
        result = self.get_related_payments().where(
            Dream.user_id == self.request.user.id
        )
        count_query = result.with_only_columns((Dream.id,)).alias()
        total = (
            await db.select(
                [db.func.count(db.func.distinct(count_query.c.id))]
            )
            .select_from(count_query)
            .gino.scalar()
        )
        return await custom_paginate(result, total, params)

    @router.get(
        "/payment/{dream_id}",
        response_model=List[ResponseBasePaymentData],
    )
    async def get_payment(
        self, dream_id: int, sender_dream_id: int = None
    ):  # noqa ANN201
        """Получение реквизитов мечты."""
        dream = await Dream.get(dream_id)

        if not dream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="dream not found"
            )
        owner_dream = await User.query.where(
            User.id == dream.user_id
        ).gino.first()
        support_dream = (
            bool(
                (await get_active_dream_info(self.request.user.id))
                or sender_dream_id
            )
            if self.request.user
            else True
        )
        can_get_payment = (
            dream.status == DreamStatus.ACTIVE.value
            and user_has_subscribe(owner_dream)
        ) or (
            dream.status == DreamStatus.CLOSED.value
            and dream.collected >= dream.goal
        )
        if sender_dream_id:
            can_get_payment = True
        if not support_dream or not can_get_payment:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        result = self.get_related_payments().where(Dream.id == dream_id)
        if not self.request.user:
            result = result.where(
                ModelBasePaymentData.type != PaymentType.BANK.value
            )
        payments = await result.gino.all()
        return (
            sorted(payments[0].add_payment, key=lambda item: item.type)
            if payments
            else []
        )

    @router.get(
        "/payment-data/{payment_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=ResponseBasePaymentData,
    )
    async def get_payment_id(self, payment_id: int):  # noqa ANN201
        """Получение реквизита по id."""
        obj = await ModelBasePaymentData.get(payment_id)
        if obj:
            return obj
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    @router.post(
        "/payment-data",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={201: {}},
    )
    async def create_payment(
        self, payment: RequestBasePaymentData
    ):  # noqa ANN201
        """Создание реквизита."""
        if (
            payment.type == PaymentType.MOBILE.value
            and self.request.user.country_id not in settings.RU_COUNTRIES
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="mobile type only for users in ru zone",
            )
        dream = await Dream.query.where(
            and_(
                Dream.user_id == self.request.user.id,
                Dream.id == payment.dream_id,
            )
        ).gino.first()
        if (
            dream
            and (
                DreamStatus.CLOSED.value <= dream.status
                or dream.status < DreamStatus.THREE_QUARTERS.value
            )
        ) or not dream:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        status_code = DreamStatus.WHOLE.value

        if await self.can_activate():
            status_code = DreamStatus.ACTIVE.value
        g_model, p_model = self.data[payment.type]
        await g_model.create(**p_model(**payment.dict()).dict())
        await (
            Dream.update.values(status=status_code)
            .where(
                and_(
                    Dream.id == dream.id,
                    dream.status == DreamStatus.THREE_QUARTERS.value,
                )
            )
            .gino.status()
        )
        # TODO нужно придумать другой способ вызывать recount, возможно celery.
        if not self.request.user.refer_code:
            await recount_refs(
                self.request.app.state.redis, self.request.user.referer
            )
        return Response(status_code=status.HTTP_201_CREATED)

    async def can_activate(self) -> bool:
        """Проверить возможность активации мечты на данном этапе."""
        paid_till = self.request.user.paid_till
        trial_till = self.request.user.trial_till
        has_active_dream = await Dream.query.where(
            and_(
                Dream.user_id == self.request.user.id,
                Dream.status == DreamStatus.ACTIVE.value,
            )
        ).gino.all()
        now = datetime.datetime.now
        if (
            paid_till
            and (
                paid_till >= now().date()
                and paid_till > (trial_till or now()).date()
            )
            or (trial_till and trial_till > now())
        ) and not has_active_dream:
            return True
        return False

    @router.delete(
        "/payment-data/{payment_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def delete_payment(self, payment_id: int):  # noqa ANN201
        """Удаление реквизита."""
        payment = await self.check_payment_access(
            payment_id, self.request.user.id
        )
        query = ModelBasePaymentData.load(dream=Dream).where(
            and_(
                Dream.user_id == self.request.user.id,
                ModelBasePaymentData.dream_id == payment.dream_id,
            )
        )
        dream_payments = (
            await func.count()
            .select()
            .select_from(query.alias())
            .gino.scalar()
        )
        if dream_payments == self.LAST_PAYMENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="cannot delete last payment",
            )
        try:
            await (
                ModelBasePaymentData.delete.where(
                    ModelBasePaymentData.id == payment_id
                ).gino.status()
            )
            return Response(status_code=status.HTTP_200_OK)
        except Exception:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

    @router.patch(
        "/payment-data/{payment_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def update_payment(
        self, payment_id: int, payment: RequestBasePaymentData
    ):  # noqa ANN201
        """Обновление реквизита."""
        await self.check_payment_access(payment_id, self.request.user.id)
        try:
            g_model, p_model = self.data[payment.type]
            await (
                g_model.update.values(**p_model(**payment.dict()).dict())
                .where(ModelBasePaymentData.id == payment_id)
                .gino.status()
            )
            return Response(status_code=status.HTTP_200_OK)
        except Exception:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

    async def check_payment_access(
        self, payment_id: int, user_id: int
    ) -> ModelBasePaymentData:
        """Проверить принадлежность реквизита к пользователю."""
        payment = (
            await ModelBasePaymentData.load(dream=Dream)
            .where(
                and_(
                    Dream.user_id == user_id,
                    ModelBasePaymentData.id == payment_id,
                )
            )
            .gino.first()
        )
        if not payment:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        return payment

    @router.post(
        "/payment/change-pref/{dream_id}/{payment_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def change_pref(self, dream_id: int, payment_id: int):  # noqa ANN201
        """Изменение реквизита на предпочтительный."""
        dream = await Dream.query.where(
            and_(Dream.user_id == self.request.user.id, Dream.id == dream_id)
        ).gino.first()
        if not dream:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        await (
            ModelBasePaymentData.update.values(is_preference=False)
            .where(ModelBasePaymentData.dream_id == dream_id)
            .gino.status()
        )
        await (
            ModelBasePaymentData.update.values(is_preference=True)
            .where(ModelBasePaymentData.id == payment_id)
            .gino.status()
        )
        return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "/payment-types",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def get_payment_types(self) -> List:  # noqa ANN201
        """Получить типы оплаты доступные для добавления пользователем."""
        return [
            PaymentType.BANK.value,
            PaymentType.E_PAY.value,
            PaymentType.CUSTOM.value,
            PaymentType.PAYPAL.value,
            PaymentType.CRYPTO.value,
        ]
