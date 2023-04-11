"""Модуль с представлениями мечт."""
from __future__ import annotations

import asyncio
import random
import textwrap
from datetime import date, datetime
from typing import List, NamedTuple, Optional, Union
from uuid import uuid4

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException, Query
from fastapi_pagination import Page, Params
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from gino import GinoException
from loguru import logger
from sqlalchemy import and_, func, or_
from sqlalchemy.engine import RowProxy
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dataset.config import settings
from dataset.core.container import Container
from dataset.core.mail.utils import send_mail
from dataset.mail_templates import (
    ConfirmEmailLandingRegTemplate,
    ConfirmEmailLandingTemplate,
)
from dataset.migrations import db
from dataset.rest.models.dream import (
    CharityDreamModel,
    DreamChangeModel,
    DreamDraftModel,
    DreamFormModel,
    DreamModel,
    DreamSettingsModel,
    EmailCodeModel,
    PaginateDreamsList,
    ResponseDreamCurrencyModel,
    ResponseDreamLimitModel,
    ResponseDreamListItem,
    ResponseDreamModel,
    ResponseDreamUsPmModel,
    ResponseModalWindowModel,
)
from dataset.rest.models.utils import EmptyResponse
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.custom_paginate import custom_paginate
from dataset.rest.views.profile import get_active_dream_info
from dataset.rest.views.utils import (
    activate_another_dream,
    email_validate,
    refresh_dreams_view,
)
from dataset.services.translations import TranslateService
from dataset.tables.achievement import (
    Achievement,
    AchievementRefNum,
    AchievementType,
)
from dataset.tables.admin_settings import AdminSettings
from dataset.tables.currency import Currency
from dataset.tables.donation import Donation, DonationStatus
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.dream_form import DreamForm
from dataset.tables.user import User
from dataset.utils.user import user_has_subscribe

router = InferringRouter()


class EmailCode:
    """Класс для генерации, хранения и проверки емейл-кодов."""

    @classmethod
    async def set_code(cls, email: str, request: Request) -> str:
        """Сгенерировать код, сохранить в редис на заданное время."""
        email_code = uuid4().hex
        await request.app.state.redis.setex(
            email_code, settings.EMAIL_CODE_LIFETIME, email
        )
        return email_code

    @classmethod
    async def get_code(cls, code: str, request: Request) -> Optional[str]:
        """Получить емейл по коду из редиса."""
        return await request.app.state.redis.get(code)

    @classmethod
    async def delete_code(cls, code: str, request: Request) -> Optional[str]:
        """Удалить код из редиса."""
        return await request.app.state.redis.delete(code)


@inject
async def get_translation_dream(
    data: dict,
    lang: str,
    translate_service: TranslateService = Provide[Container.translate_service],
) -> dict:
    """Перевести мечту."""
    return await translate_service.get_translation(data, lang)


@inject
async def detect_language_dream(
    dream: Union[
        DreamForm, DreamDraftModel, DreamChangeModel, CharityDreamModel
    ],
    translate_service: TranslateService = Provide[Container.translate_service],
) -> str:
    """Определить язык мечты."""
    if dream.description:
        return translate_service.detect_language(dream.description)
    return translate_service.detect_language(dream.title)


async def create_dream_draft(dream_form: DreamForm, user: User) -> None:
    """Создать черновик мечты из заполненной на лендинге формы мечты."""
    if not dream_form:
        return
    course_dream_form = (
        await Currency.query.where(
            Currency.id == dream_form.currency_id
        ).gino.first()
    ).course
    course_user = (
        await Currency.query.where(
            Currency.id == user.currency_id
        ).gino.first()
    ).course
    ratio = course_user / course_dream_form
    dream_goal = dream_form.goal * ratio
    language = await detect_language_dream(dream_form) or user.language
    await Dream.create(
        user_id=user.id,
        status=DreamStatus.DRAFT.value,
        title=dream_form.title,
        description=dream_form.description,
        goal=dream_goal,
        collected=settings.DREAM_START_VALUE,
        currency_id=user.currency_id,
        language=language,
    )


def filter_dream(
    request: Request,
    categories_id: Optional[List[int]] = Query(None),  # noqa B008
) -> list:
    """Фильтрация по мечтам."""
    if popular := (
        categories_id and settings.POPULAR_CATEGORY_ID in categories_id
    ):
        categories_id.remove(settings.POPULAR_CATEGORY_ID)
    categories_id = categories_id if categories_id else None
    popular = popular if popular else None
    query_data = (
        (
            categories_id,
            Dream.category_id.in_(categories_id) if categories_id else None,
        ),
        (
            popular,
            or_(
                User.refer_count >= AchievementRefNum.top_fundraiser.value,
                User.is_vip == True,  # noqa E712
                User.id == request.user.id,
            )
            if popular
            else None,
        ),
    )

    return [query for value, query in query_data if value is not None]


# TODO Представление на 1000 стро разбить
@cbv(router)
class DreamView(BaseView):
    """Представление для работы с мечтой."""

    @router.post("/dreams/draft", responses={400: {}, 201: {}})
    async def post_draft(
        self,
        dream: DreamDraftModel = Depends(DreamDraftModel.as_form),  # noqa B008
    ):  # noqa ANN201
        """Запрос на создание черновика мечты."""
        return await self.create_dream(dream, DreamStatus.DRAFT.value)

    @router.post(
        "/dreams",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={400: {}, 201: {}},
    )
    async def post(
        self, dream: DreamModel = Depends(DreamModel.as_form)  # noqa B008
    ):  # noqa ANN201
        """Запрос на создание мечты."""
        status = DreamStatus.QUART.value
        if self.request.user.referer:
            status = DreamStatus.HALF.value
        return await self.create_dream(dream, status)

    @router.post(
        "/admin/edit-dream-settings",
        dependencies=[Depends(AuthChecker(is_auth=True, is_admin=True))],
    )
    async def edit_settings(self, dream: DreamSettingsModel):  # noqa ANN201
        """Запрос на редактирование максимального размера мечты админом."""
        settings = dream.dict()
        try:
            await (
                AdminSettings.update.values(**settings)
                .where(AdminSettings.id == 1)
                .gino.status()
            )
        except Exception as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        return {"result": True}

    @router.post(
        "/charity-dreams/draft",
        dependencies=[Depends(AuthChecker(is_auth=True, is_admin=True))],
        responses={400: {}, 201: {}},
    )
    async def post_draft_charity(
        self,
        dream: DreamDraftModel = Depends(DreamDraftModel.as_form),  # noqa B008
    ):  # noqa ANN201
        """Запрос на создание черновика благотворительной мечты."""
        return await self.create_charity_dream(dream, DreamStatus.DRAFT.value)

    @router.post(
        "/charity-dreams",
        dependencies=[Depends(AuthChecker(is_auth=True, is_admin=True))],
        responses={400: {}, 201: {}},
        response_model=EmptyResponse,
    )
    async def post_charity(
        self,
        dream: CharityDreamModel = Depends(  # noqa B008
            CharityDreamModel.as_form
        ),
    ) -> Response:
        """Запрос на создание благотворительной мечты."""
        return await self.create_charity_dream(dream, DreamStatus.QUART.value)

    @router.get(
        "/dreams-count",
    )
    async def get_dreams_count(
        self,
        country_id: Optional[int] = None,
        categories_id: Optional[List[int]] = Query(None),  # noqa B008
    ) -> dict:
        """Получить количество мечт участников."""
        filter_dreams = self.prepare_filter(country_id, categories_id)
        count = await self.dreams_count(
            self.get_raw_dreams(filter_dreams)["dreams"]
        )
        return {"total": count}

    @router.get(
        "/dreams",
        response_model=PaginateDreamsList,
    )
    async def get_dreams_list(
        self,
        country_id: Optional[int] = None,
        categories_id: Optional[list[int]] = Query(None),  # noqa B008
        params: Params = Depends(),  # noqa B008
    ) -> dict:
        """Получить пагинированный список мечт участников."""
        filter_dreams = self.prepare_filter(country_id, categories_id)
        dreams = self.get_raw_dreams(filter_dreams)["dreams"]
        count = await self.dreams_count(dreams)
        linking_operator = self.get_raw_dreams(filter_dreams)["operator"]
        dreams = await self.get_dreams_paginate(
            dreams, linking_operator, params
        )

        dreams_page = []
        for dream_query in dreams:
            dreams_page.append(await self.prepare_dream(dream_query))

        return {
            "items": dreams_page,
            "total": count,
            "page": params.page,
            "size": params.size,
        }

    def get_raw_dreams(self, filter_dreams: str) -> dict:
        """Получить запрос на список мечт участников из materialized view."""
        sql = "SELECT * FROM dreams_list"
        linking_operator = "WHERE"
        if filter_dreams:
            sql += f" WHERE {filter_dreams}"
            linking_operator = "AND"
        return {"dreams": sql, "operator": linking_operator}

    def prepare_filter(self, country_id: int, categories_id: list) -> str:
        """Подготовить список мечт с фильтрацией.

        По стране, категории, популярности.
        """
        conds = []
        if country_id:
            conds.append(f"country_id = {country_id}")
        if popular := (
            categories_id and settings.POPULAR_CATEGORY_ID in categories_id
        ):
            categories_id.remove(settings.POPULAR_CATEGORY_ID)
        if categories_id:
            categories_id = [str(category_id) for category_id in categories_id]
            conds.append(f"category_id IN ({','.join(categories_id)}) ")
        join_term = ""
        if popular:
            join_term = "OR" if categories_id else "AND"

        conds = " AND ".join(conds)
        # если пользователь неавторизован подставляем несуществующий id
        current_user_id = self.request.user.id if self.request.user else -1
        if join_term:
            join_term = join_term if conds else ""
            conds += (
                f"{join_term} (refer_count >= "
                f"{AchievementRefNum.top_fundraiser.value} "
                f"OR is_vip = true OR user_id = {current_user_id})"
            )
        return conds

    async def dreams_count(self, filter_dreams: str) -> int:
        """Подсчитать количество мечт после фильтрации."""
        return (
            await db.all(
                db.text(
                    f"SELECT COUNT(*) AS total "
                    f"FROM ({filter_dreams}) AS dreams_list;"
                )
            )
        )[0].total

    async def get_dreams_paginate(
        self, dreams: str, operator: str, params: Params
    ) -> list:
        """Подготовить пагинированный список мечт."""
        # если пользователь неавторизован подставляем несуществующий id
        current_user_id = self.request.user.id if self.request.user else -1
        return await db.all(
            db.text(
                f"{dreams} {operator} user_id = {current_user_id} "
                "UNION ALL "
                f"{dreams} {operator} user_id != {current_user_id} "
                f"OFFSET {(params.page - 1) * params.size} LIMIT {params.size};"
            ).gino.query
        )

    @inject
    async def prepare_dream(
        self,
        dream_query: RowProxy | NamedTuple,
        translate_service: TranslateService = Provide[
            Container.translate_service
        ],
    ) -> dict:
        """Подготовить поля мечты для передачи фронту."""
        dream = dict(dream_query)
        translation = await translate_service.get_translation(
            dream, self.request["language"]
        )
        dream["title"] = translation["title"]
        dream["description"] = textwrap.shorten(
            translation["description"],
            width=settings.SHORT_DESCRIPTION_LEN,
            placeholder="...",
        )
        user_fields = {
            "user_id": "id",
            "name": "name",
            "surname": "surname",
            "avatar": "avatar",
            "country_id": "country_id",
            "trial_till": "trial_till",
            "paid_till": "paid_till",
            "refer_count": "refer_count",
        }
        dream["user"] = {
            field: dream[key] for key, field in user_fields.items()
        }
        return dream

    @router.get("/dream/{dream_id}", response_model=ResponseDreamCurrencyModel)
    async def get_dream(
        self,
        dream_id: int,
        currency_id: Optional[int] = None,
        sender_dream_id: int = None,
    ) -> ResponseDreamCurrencyModel:
        """Получить конкретную мечту для страницы мечты."""
        query = Dream.join(User).select().where(Dream.id == dream_id)
        loader = Dream.load(user=User)
        dream_info = await query.gino.load(loader).first()
        data = await self.add_currency(dream_id, dream_info, currency_id)
        support_dream = (
            bool(
                (await get_active_dream_info(self.request.user.id))
                or sender_dream_id
            )
            if self.request.user
            else True
        )
        translation = await get_translation_dream(
            data, self.request["language"]
        )
        data["title"] = translation["title"]
        data["description"] = translation["description"]
        return ResponseDreamCurrencyModel(
            **data,
            user=dream_info.user,
            support_dream=support_dream,
        )

    async def add_currency(
        self, dream_id: int, dream_info: Dream, currency_id: int = None
    ) -> dict:
        """Перерасчет суммы на мечту.

        Из собранных средства в валюту текущего пользователя.
        """
        dream = await Dream.get(dream_id)
        if not dream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="dream not found"
            )
        owner_dream = await User.query.where(
            User.id == dream.user_id
        ).gino.first()
        can_get_dream = (
            dream.status == DreamStatus.ACTIVE.value
            and user_has_subscribe(owner_dream)
        ) or (
            dream.status == DreamStatus.CLOSED.value
            and dream.collected >= dream.goal
        )
        if not can_get_dream:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        course_dream = (
            await Currency.query.where(
                Currency.id == dream.currency_id
            ).gino.first()
        ).course
        currency = await Currency.query.where(
            Currency.id == settings.EURO_ID
        ).gino.first()
        if not self.request.user and currency_id:
            currency = await Currency.query.where(
                Currency.id == currency_id
            ).gino.first()
        if self.request.user:
            currency = await Currency.query.where(
                Currency.id == self.request.user.currency_id
            ).gino.first()
        ratio = currency.course / course_dream
        # TODO отрефакторить деление на 100
        currency_info = {
            "currency_code": currency.code,
            "currency_symbol": currency.symbol,
            "dream_goal": (int(dream.goal * ratio) / settings.FINANCE_RATIO),
            "dream_collected": (
                int(dream.collected * ratio) / settings.FINANCE_RATIO
            ),
        }
        return {**dream_info.to_dict(), **currency_info}

    @router.post("/dream-form", responses={400: {}, 201: {}})
    async def create_dream_form(
        self,
        dream_form: DreamFormModel,
    ):  # noqa ANN201
        """Запрос на создание формы мечты на лендинге."""
        data = dream_form.dict()
        currency_id = data["currency_id"]
        email = data["email"]
        email_validate(email)
        del data["re_token"]
        name = data.pop("name")
        await self.check_dream_sum(data["goal"], currency_id)
        email_code = await EmailCode.set_code(email, self.request)
        data["code"] = email_code
        try:
            await DreamForm.create(**data)
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        is_reg = bool(
            await User.query.where(User.verified_email == email).gino.first()
        )
        language = self.request["language"]
        lang = (
            language if language in ("ru", "en") else settings.DEFAULT_LANGUAGE
        )
        template = (
            ConfirmEmailLandingRegTemplate
            if is_reg
            else ConfirmEmailLandingTemplate
        )
        asyncio.create_task(
            send_mail(
                email,
                template(
                    self.request.app,
                    name=name,
                    email=email,
                    code=email_code,
                    lang=lang,
                ),
                lang,
            )
        )
        return Response(status_code=status.HTTP_201_CREATED, content="Ok")

    @router.post("/dream-form-confirm", responses={400: {}, 201: {}})
    async def dream_form_confirm(
        self, email_code: EmailCodeModel
    ):  # noqa ANN201
        """Запрос на создание черновика мечты из заполненной на лендинге формы.

        После переходы по ссылке из письма.
        """
        email = await EmailCode.get_code(email_code.code, self.request)
        if email is None:
            return JSONResponse({"status": "code expired"})
        user = await User.query.where(User.email == email).gino.first()
        if not user:
            await EmailCode.delete_code(email_code.code, self.request)
            return JSONResponse({"status": "not registered"})
        dream_form = await DreamForm.query.where(
            and_(DreamForm.code == email_code.code, DreamForm.email == email)
        ).gino.first()
        try:
            await create_dream_draft(dream_form, user)
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        await EmailCode.delete_code(email_code.code, self.request)
        return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "/dreams/my",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=Page[ResponseDreamModel],
    )
    async def my_dream_list(self, status: str = None) -> dict:
        """Получение списка мечт конкретного пользователя."""
        my_dreams = Dream.query.where(Dream.user_id == self.request.user.id)
        if status == "active":
            my_dreams = my_dreams.where(
                Dream.status != DreamStatus.CLOSED.value
            )
        elif status == "closed":
            my_dreams = my_dreams.where(
                Dream.status == DreamStatus.CLOSED.value,
            )
        response = await self.get_dreams(my_dreams)
        return response.dict(exclude={"updated_at"})

    async def get_dreams(self, dreams: Dream) -> Page[ResponseDreamModel]:
        """Получить пагинированные мечты отфильтрованные по статусу."""
        count_query = dreams.with_only_columns((Dream.id,)).alias()
        total = (
            await db.select(
                [db.func.count(db.func.distinct(count_query.c.id))]
            )
            .select_from(count_query)
            .gino.scalar()
        )
        result = await custom_paginate(dreams, total=total)
        # Перевод суммы мечты в реальный размер для отображения,
        # добавление меток возможности изменения мечты
        # и совершать реферальные донаты с привязкой к мечте
        # TODO отрефакторить деление на settings.FINANCE_RATIO

        paid_referral_donations = []
        send_donations = await Donation.query.where(
            and_(
                Donation.sender_id == self.request.user.id,
                Donation.status > DonationStatus.NEW.value,
                Donation.status < DonationStatus.FAILED.value,
            )
        ).gino.all()
        received_donations = await Donation.query.where(
            and_(
                Donation.recipient_id == self.request.user.id,
                Donation.status
                > DonationStatus.WAITING_FOR_CONFIRMATION.value,
                Donation.status < DonationStatus.FAILED.value,
            )
        ).gino.all()
        send_donations_ids = {donate.id for donate in send_donations}
        received_donations_dream_ids = {
            donate.dream_id for donate in received_donations
        }
        for item in result.items:
            item.collected /= settings.FINANCE_RATIO
            item.goal /= settings.FINANCE_RATIO
            received_donate = item.id in received_donations_dream_ids
            paid_referral_donate = not send_donations_ids.isdisjoint(
                set(item.ref_donations)
            )
            item.update_ = item.support_dreams = False
            if item.status < DreamStatus.CLOSED.value and not received_donate:
                item.update_ = True
            if item.status == DreamStatus.HALF.value and paid_referral_donate:
                item.support_dreams = True
                paid_referral_donations.append(True)
        if not paid_referral_donations:
            for item in result.items:
                item.support_dreams = item.status == DreamStatus.HALF.value
        return result

    async def check_dream_sum(self, dream_goal: int, currency_id: int) -> None:
        """Проверка введенной пользователем суммы мечты.

        На соответствие лимиту.
        """
        if is_dream_maker := self.request.user:
            is_dream_maker = await Achievement.query.where(
                and_(
                    Achievement.user_id == self.request.user.id,
                    Achievement.received_at != None,  # noqa E711
                    Achievement.type_name == AchievementType.DREAM_MAKER.value,
                )
            ).gino.first()
        currency = await Currency.query.where(
            Currency.id == currency_id
        ).gino.first()
        limit_factor = settings.DREAM_MAKER_RISE_LIMIT if is_dream_maker else 1
        if (
            dream_goal
            and currency
            and (
                dream_goal <= 0
                or dream_goal
                > (
                    currency.dream_limit
                    * limit_factor
                    * settings.FINANCE_RATIO
                )
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You exceed the limit",
            )

    @router.get(
        "/dreams/{num}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=ResponseDreamUsPmModel,
        responses={404: {"description": "Dream not found"}},
    )
    async def retrieve(self, num: int) -> Response:
        """Получить подробную информацию по мечте текущего пользователя."""
        dream_obj = await Dream.query.where(
            and_(Dream.id == num, Dream.user_id == self.request.user.id)
        ).gino.first()
        if dream_obj:
            # Перевод суммы мечты в реальный размер для отображения,
            # добавление метки возможности удаления мечты
            # TODO отрефакторить
            dream_obj.goal = dream_obj.goal / settings.FINANCE_RATIO
            dream_obj.collected = dream_obj.collected / settings.FINANCE_RATIO
            dream_obj.delete_ = (
                dream_obj.status < DreamStatus.ACTIVE.value
                and not await self.check_bound_donation(dream_obj)
            )
            return dream_obj
        return Response(
            content="Dream not found", status_code=status.HTTP_404_NOT_FOUND
        )

    @inject
    async def create_dream(
        self,
        dream: Union[DreamModel, DreamDraftModel],
        dream_status: int,
        translate_service: TranslateService = Provide[
            Container.translate_service
        ],
    ) -> Response:
        """Создать мечту."""
        query = Dream.select().where(Dream.user_id == self.request.user.id)
        dream_count = (
            await func.count()
            .select()
            .select_from(query.alias())
            .gino.scalar()
        )
        currency_id = self.request.user.currency_id
        if dream.goal:
            await self.check_dream_sum(dream.goal, currency_id)
        if dream_count >= settings.MAX_DREAM_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exceeded the limit of the number of " "dreams",
            )

        data = dream.dict()
        if not dream.goal:
            data["goal"] = settings.DREAM_START_VALUE

        if dream.description:
            lang = translate_service.detect_language(dream.description)
        else:
            lang = translate_service.detect_language(dream.title)
        language = lang or self.request.user.language
        data.update(
            {
                "user_id": self.request.user.id,
                "status": dream_status,
                "collected": settings.DREAM_START_VALUE,
                "currency_id": currency_id,
                "language": language,
            }
        )
        try:
            dream_id = (await Dream.create(**data)).id  # noqa F841
        except Exception as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )

        return Response(status_code=status.HTTP_201_CREATED)

    @router.post(
        "/dreams/{num}/close",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def close_dream(self, num: int):  # noqa ANN201
        """Закрыть активную мечту."""
        user = self.request.user
        dream_obj = await Dream.query.where(
            and_(Dream.id == num, Dream.user_id == user.id)
        ).gino.first()
        if not dream_obj:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        if dream_obj.status != DreamStatus.ACTIVE.value:
            return HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        (
            await Dream.update.values(
                status=DreamStatus.CLOSED.value, closed_at=func.now()
            )
            .where(and_(Dream.id == num, Dream.user_id == user.id))
            .gino.status()
        )
        await activate_another_dream(user)
        await refresh_dreams_view()
        return Response(status_code=status.HTTP_201_CREATED)

    @router.patch(
        "/dreams/draft/{draft_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def update_draft(
        self,
        draft_id: int,
        dream: DreamDraftModel = Depends(DreamDraftModel.as_form),  # noqa B008
    ):  # noqa ANN201
        """Обновление черновика мечты."""
        draft_dream = await Dream.query.where(
            and_(
                Dream.user_id == self.request.user.id,
                Dream.status == DreamStatus.DRAFT.value,
                Dream.id == draft_id,
            )
        ).gino.first()
        if not draft_dream:
            return Response(status_code=status.HTTP_403_FORBIDDEN)
        if dream.goal:
            currency_id = self.request.user.currency_id
            await self.check_dream_sum(dream.goal, currency_id)
        if not dream.goal:
            dream.goal = settings.DREAM_START_VALUE
        dream.language = (
            await detect_language_dream(dream) or draft_dream.language
        )
        async with db.transaction():
            await (
                Dream.update.values(**dream.dict())
                .where(Dream.id == draft_id)
                .gino.status()
            )
        return Response(status_code=status.HTTP_200_OK)

    @router.post(
        "/dreams/issue-draft/{draft_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={200: {}, 422: {}},
    )
    async def issue_draft(
        self,
        draft_id: int,
        dream: DreamModel = Depends(DreamModel.as_form),  # noqa B008
    ):  # noqa ANN201
        """Запрос на смену статуса черновика мечты."""
        draft_dream = await Dream.query.where(
            and_(Dream.id == draft_id, Dream.user_id == self.request.user.id)
        ).gino.first()
        if not draft_dream:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        dream_status = DreamStatus.QUART.value
        if self.request.user.referer:
            dream_status = DreamStatus.HALF.value
        currency_id = self.request.user.currency_id
        await self.check_dream_sum(dream.goal, currency_id)
        await draft_dream.update(**dream.dict(), status=dream_status).apply()
        return Response(status_code=status.HTTP_200_OK)

    async def create_charity_dream(
        self, dream: CharityDreamModel, dream_status: int
    ) -> Response:
        """Создать благотворительную мечту."""
        data = dream.dict()
        language = (
            await detect_language_dream(dream) or self.request.user.language
        )
        data.update(
            {
                "user_id": self.request.user.id,
                "status": dream_status,
                "type_dream": "Благотворительная",
                "collected": 0,
                "language": language,
            }
        )
        try:
            await Dream.create(**data)
        except Exception as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )

        return Response(status_code=status.HTTP_201_CREATED)

    @router.get(
        "/dream/{dream_id}/receipt",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def get_receipt(self, dream_id: int) -> str:
        """Получить чек по мечте."""
        donation = await Donation.query.where(
            and_(
                Donation.dream_id == dream_id,
                Donation.sender_id == self.request.user.id,
            )
        ).gino.first()

        if not donation:
            return ""

        return donation.receipt

    @router.get(
        "/dream/{dream_id}/forecast",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={
            200: {
                "content": {"application/json": {"example": {"forecast": 0}}}
            }
        },
    )
    async def get_forecast(self, dream_id: int) -> Optional[int]:
        """
        Расчет прогнозируемого кол-ва дней до закрытия мечты.

        Алгоритм расчета остаток для сбора делиться на среднюю сумму
         пожертвований за день
        """
        sub_query = f"""
        SELECT dream.id, (goal - SUM(amount) OVER()) AS left_sum,
               SUM(amount) OVER(
      ORDER BY confirmed_at::date) AS day_sum, confirmed_at
          FROM dream
          JOIN donation ON dream.id = donation.dream_id
         WHERE confirmed_at IS NOT NULL
           AND dream_id = {dream_id}"""
        forecast = """CEILING(left_sum / AVG(day_sum) OVER(
        ORDER BY confirmed_at::date))"""
        query = f"SELECT {forecast} as forecast FROM ({sub_query}) s1;"  # noqa Q440

        res = await db.all(db.text(query))
        return int(res[0][0]) if res and res[0] else None

    @router.get("/dream-limit", response_model=ResponseDreamLimitModel)
    async def dream_limit(
        self, currency_id: Optional[int] = None
    ) -> JSONResponse:
        """Получение лимита мечты с учетом выбранной валюты."""
        if not self.request.user and not currency_id:
            currency = await Currency.query.where(
                Currency.id == settings.EURO_ID
            ).gino.first()
            return JSONResponse(
                {
                    "dream_limit": currency.dream_limit,
                    "symbol": currency.symbol,
                }
            )
        if not self.request.user:
            currency = await Currency.query.where(
                Currency.id == currency_id
            ).gino.first()
            return JSONResponse(
                {
                    "dream_limit": currency.dream_limit,
                    "symbol": currency.symbol,
                }
            )
        is_dream_maker = await Achievement.query.where(
            and_(
                Achievement.user_id == self.request.user.id,
                Achievement.received_at != None,  # noqa E711
                Achievement.type_name == AchievementType.DREAM_MAKER.value,
            )
        ).gino.first()
        currency_id = self.request.user.currency_id
        currency = await Currency.query.where(
            Currency.id == currency_id
        ).gino.first()
        if is_dream_maker:
            return JSONResponse(
                {
                    "dream_limit": (
                        currency.dream_limit * settings.DREAM_MAKER_RISE_LIMIT
                    ),
                    "symbol": currency.symbol,
                }
            )
        return JSONResponse(
            {"dream_limit": currency.dream_limit, "symbol": currency.symbol}
        )

    @router.get("/landing-dreams", response_model=List[ResponseDreamModel])
    async def get_landing_dreams(self, currency_id: int = None) -> List:
        """Получение списка мечт для лендинга."""
        currency_id = currency_id or settings.EURO_ID
        user_currency = await Currency.get(currency_id)
        if not user_currency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid currency_id",
            )
        result = await self.get_landing_dreams_from_db(
            user_currency.course, user_currency.symbol
        )
        landing_dreams_list = []
        for dream in result:
            dream_to_dict = dict(dream)
            translation = await get_translation_dream(
                dream_to_dict, self.request["language"]
            )
            dream_to_dict["title"] = translation["title"]
            dream_to_dict["description"] = translation["description"]
            landing_dreams_list.append(dream_to_dict)
        return landing_dreams_list

    async def get_landing_dreams_from_db(
        self, user_course: int, user_symbol: str
    ) -> List:
        """Получение списка мечт для лендинга из БД."""
        dreams_active_where = (
            f"dream.status = {DreamStatus.ACTIVE.value} "
            f"AND (trial_till > NOW() "
            f"OR paid_till >= CURRENT_DATE)"
        )
        dreams_closed_where = (
            f"dream.status = {DreamStatus.CLOSED.value} AND "
            f"collected >= goal AND closed_at >= NOW() - INTERVAL "
            f"'{settings.DREAM_CLOSED_SHOW_TIME} HOUR'"
        )
        landing_dreams = await self.get_dreams_query(
            dreams_active_where,
            settings.LEN_LANDING_DREAMS,
            user_course,
            user_symbol,
        )
        random.shuffle(landing_dreams)
        dreams_closed = await self.get_dreams_query(
            dreams_closed_where,
            settings.LEN_CLOSED_DREAMS,
            user_course,
            user_symbol,
        )
        # отнимаем единицу так как индексация списка идет с 0
        index = settings.LEN_DREAMS_GROUP_LANDING - 1
        for dream in dreams_closed:
            random_place = random.randint(0, 2)
            landing_dreams.insert(index - random_place, dream)
            index += settings.LEN_DREAMS_GROUP_LANDING
        return landing_dreams[: settings.LEN_LANDING_DREAMS]

    async def get_dreams_query(
        self,
        where: str,
        limit: int,
        user_course: int,
        user_symbol: str,
    ) -> RowProxy:
        """Запрос в БД на список мечт для лендинга с заданными условиями."""
        return await db.all(
            db.text(
                f"""
         SELECT dream.id, user_id, status, title, description,
                ROUND((collected / {settings.FINANCE_RATIO})
                      * ({user_course}::DECIMAL / course))
                AS collected,
                ROUND((goal / {settings.FINANCE_RATIO})
                      * ({user_course}::DECIMAL / course))
                AS goal,
                picture, category_id, type_dream, dream.currency_id,
                '{user_symbol}' AS symbol, dream.updated_at, dream.language
           FROM dream
           JOIN "user" ON "user".id = user_id
           JOIN currency ON currency.id = dream.currency_id
          WHERE type_dream != 'Благотворительная'
            AND {where}
            AND "user".is_active = TRUE
       ORDER BY collected / course DESC LIMIT({limit});"""
            )
        )

    @router.get(
        "/modal-window",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=ResponseModalWindowModel,
    )
    async def show_modal_window(self) -> JSONResponse:
        """Функция для определения необходимости показа модельного окна.

        С предложением оформить подписку.
        """
        user = self.request.user
        email = user.verified_email
        is_shown = await self.request.app.state.redis.get(email)
        if (
            is_shown is not None
            or (user.paid_till and user.paid_till >= date.today())
            or (user.trial_till and user.trial_till >= datetime.now())
            or not user.is_active
        ):
            return JSONResponse({"show": False})
        target_dreams = await Dream.query.where(
            and_(
                Dream.user_id == user.id,
                or_(
                    Dream.status == DreamStatus.ACTIVE.value,
                    Dream.status == DreamStatus.WHOLE.value,
                ),
            )
        ).gino.all()
        statuses = [dream.status for dream in target_dreams]
        if (
            DreamStatus.ACTIVE.value in statuses
            or DreamStatus.WHOLE.value not in statuses
        ):
            return JSONResponse({"show": False})
        await self.request.app.state.redis.setex(
            email, settings.EMAIL_CODE_LIFETIME, "is_shown"
        )
        return JSONResponse({"show": True})

    @router.patch(
        "/update-dream/{dream_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def update_dream(
        self,
        dream_id: int,
        info: DreamChangeModel = Depends(  # noqa B008
            DreamChangeModel.as_form
        ),
    ):  # noqa ANN201
        """Метод редактирования мечты."""
        dream = await self.check_existence_dream(dream_id)
        if not dream or dream.status == DreamStatus.DRAFT.value:
            return Response(status_code=status.HTTP_403_FORBIDDEN)
        if await self.check_existence_confirm_donation(dream):
            return Response(
                status_code=status.HTTP_403_FORBIDDEN,
                content="user has confirmed donation for this dream",
            )
        currency_id = self.request.user.currency_id
        await self.check_dream_sum(info.goal, currency_id)
        updated_fields = info.dict()
        language = await detect_language_dream(info) or dream.language
        updated_fields.update({"language": language})
        async with db.transaction():
            await (
                Dream.update.values(**updated_fields)
                .where(Dream.id == dream_id)
                .gino.status()
            )
            await refresh_dreams_view()
        return Response(status_code=status.HTTP_201_CREATED)

    @router.delete(
        "/delete-dream/{dream_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def delete_dream(self, dream_id: int):  # noqa ANN201
        """Метод удаления мечты."""
        dream = await self.check_existence_dream(dream_id)
        if not dream:
            return Response(status_code=status.HTTP_403_FORBIDDEN)
        if await self.check_bound_donation(dream):
            return Response(
                status_code=status.HTTP_403_FORBIDDEN,
                content="user has bound donation with this dream",
            )
        try:
            await dream.delete()
        except Exception as exc:
            logger.exception(str(exc))  # noqa G200
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    async def check_existence_dream(self, dream_id: int) -> Dream:
        """Проверить наличие и статус мечты."""
        return await Dream.query.where(
            and_(
                Dream.id == dream_id,
                Dream.user_id == self.request.user.id,
                Dream.status >= DreamStatus.DRAFT.value,
                Dream.status < DreamStatus.CLOSED.value,
            )
        ).gino.first()

    async def check_existence_confirm_donation(self, dream: Dream) -> Donation:
        """Проверить наличие подтвержденного доната на мечту."""
        return await Donation.query.where(
            and_(
                Donation.recipient_id == self.request.user.id,
                Donation.dream_id == dream.id,
                Donation.status
                > DonationStatus.WAITING_FOR_CONFIRMATION.value,
                Donation.status < DonationStatus.FAILED.value,
            )
        ).gino.first()

    async def check_bound_donation(self, dream: Dream) -> Donation:
        """Проверить наличие доната связанного с мечтой."""
        return await Donation.query.where(
            or_(
                and_(
                    Donation.dream_id == dream.id,
                    Donation.recipient_id == self.request.user.id,
                ),
                and_(
                    Donation.sender_id == self.request.user.id,
                    Donation.id.in_(dream.ref_donations),
                    Donation.status > DonationStatus.NEW.value,
                    Donation.status < DonationStatus.FAILED.value,
                ),
            )
        ).gino.first()

    @router.get(
        "/dreams/active/{user_id}",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=ResponseDreamListItem,
    )
    async def translate_active_dream(self, user_id: int):  # noqa ANN201
        """Запрос на перевод активной мечты для чата."""
        dream = await Dream.query.where(
            and_(
                Dream.user_id == user_id,
                Dream.status == DreamStatus.ACTIVE.value,
            )
        ).gino.first()
        if not dream:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="dream not found"
            )
        dream_to_dict = dream.to_dict()
        translation = await get_translation_dream(
            dream_to_dict, self.request["language"]
        )
        dream_to_dict["title"] = translation["title"]
        return dream_to_dict
