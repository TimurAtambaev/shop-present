"""Модуль для работы с панелью администратора."""
import functools
from datetime import date, datetime
from typing import Callable, List, Optional, Union

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException, Query
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.gino import paginate
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from gino import GinoException
from loguru import logger
from sqlalchemy import String, and_, asc, cast, desc, or_
from sqlalchemy.sql import Select
from starlette import status
from starlette.responses import Response

from dataset.config import settings
from dataset.core.container import Container
from dataset.migrations import db
from dataset.rest.models.admin import (
    AdminCurrencyModel,
    AdminDetailDream,
    AdminDream,
    AdminListCurrencies,
    AdminListDonation,
    AdminListDream,
    AdminNews,
    ResponseSpecialUsersModel,
    SubscribeTillModel,
    VipStatus,
)
from dataset.rest.models.profile import ProfileInfo
from dataset.rest.models.review import ResponseReviewModel, ReviewModel
from dataset.rest.models.utils import SortChoices
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.currency import recalculation
from dataset.rest.views.custom_paginate import custom_paginate
from dataset.rest.views.donation import Recipient, Sender
from dataset.rest.views.utils import (
    get_achievement_sort_qs,
    need_dreams_view_refresh,
    refresh_dreams_view,
)
from dataset.services.review import (
    CreateReviewError,
    ReviewService,
    UpdateReviewError,
)
from dataset.services.subscriptions import SubscriptionService
from dataset.tables.achievement import (
    Achievement,
    AchievementRefNum,
    AchievementType,
)
from dataset.tables.currency import Currency
from dataset.tables.donate_size import DonateSize
from dataset.tables.donation import Donation
from dataset.tables.dream import Category, Dream, DreamStatus
from dataset.tables.post import Post
from dataset.tables.user import User

router = InferringRouter()


def errors_decorator(function: Callable) -> Callable:
    """Обработка ошибок в методах."""

    @functools.wraps(function)
    async def wrapper(*args: tuple, **kwargs: dict) -> Callable:
        """Обертка декоратора."""
        try:
            return await function(*args, **kwargs)
        except HTTPException as exc:
            logger.error(exc)
            raise exc
        except Exception as exc:
            logger.error(exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    return wrapper


@cbv(router)
class AdminNewsView(BaseView):
    """Представление для работы с новостями из админки."""

    @router.post(
        "/news", dependencies=[Depends(AuthChecker(is_operator=True))]
    )
    @errors_decorator
    async def create_news(
        self, data: AdminNews = Depends(AdminNews.as_form)  # noqa B008
    ):  # noqa ANN201
        """Метод для создание новостей."""
        data = data.dict()
        data["published_date"] = datetime.strptime(
            data["published_date"], "%Y-%m-%d"
        )
        await Post.create(**data)
        return Response(status_code=status.HTTP_201_CREATED)

    @router.patch(
        "/news/{news_id}",
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    @errors_decorator
    async def update_news(
        self,
        news_id: int,
        data: AdminNews = Depends(AdminNews.as_form),  # noqa B008
    ):  # noqa ANN201
        """Метод для обновления новости."""
        data = data.dict()
        data["published_date"] = datetime.strptime(
            data["published_date"], "%Y-%m-%d"
        )
        data["tags"] = data["tags"][0].split(",") if data["tags"] else []
        await (
            Post.update.values(**data).where(Post.id == news_id).gino.status()
        )
        return Response(status_code=status.HTTP_200_OK)

    @router.delete(
        "/news/{news_id}",
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    @errors_decorator
    async def delete_news(self, news_id: int):  # noqa ANN201
        """Метод для удаления новости."""
        await (Post.delete.where(Post.id == news_id).gino.status())
        return Response(status_code=status.HTTP_200_OK)


def filter_dream(
    active: Optional[bool] = None,
    categories: Optional[List[str]] = Query([]),  # noqa B008
    is_vip: Optional[bool] = None,
    search: Optional[str] = None,
) -> list:
    """Фильтрация по мечтам из панели администратора."""
    if categories:
        categories = categories[0].split(",")
        categories = [int(i) for i in categories]
    else:
        categories = None
    is_vip = is_vip if is_vip else None
    active = active if active else None
    query_data = (
        # если есть active, categories, is_vip, search, то в result добовляется query.
        (
            active,
            and_(
                Dream.status == DreamStatus.ACTIVE.value,
                or_(
                    User.paid_till >= date.today(),
                    User.trial_till > datetime.now(),
                ),
            )
            if active
            else None,
        ),
        (
            categories,
            Dream.category_id.in_(categories) if categories else None,
        ),
        (
            is_vip,
            or_(
                User.refer_count >= AchievementRefNum.top_fundraiser.value,
                User.is_vip == True,  # noqa E712
            )
            if is_vip
            else None,
        ),
        (
            search,
            Dream.title.ilike(f"%{search}%") if search else None,
        ),
    )

    return [query for value, query in query_data if value is not None]


def sort_dream(
    title: Optional[SortChoices] = None,
    dream_id: Optional[SortChoices] = None,
    name: Optional[SortChoices] = None,
    collected: Optional[SortChoices] = None,
    created_at: Optional[SortChoices] = None,
    closed: Optional[SortChoices] = None,
) -> list:
    """Сортировка полей мечты."""
    sort_type = {SortChoices.asc.value: asc, SortChoices.desc.value: desc}
    query_data = (
        (title, sort_type[title](Dream.title) if title else None),
        (dream_id, sort_type[dream_id](Dream.id) if dream_id else None),
        (name, sort_type[name](User.name) if name else None),
        (
            collected,
            sort_type[collected](Dream.collected) if collected else None,
        ),
        (
            created_at,
            sort_type[created_at](Dream.created_at) if created_at else None,
        ),
        (closed, sort_type[closed](Dream.closed_at) if closed else None),
    )
    return [query for value, query in query_data if value is not None]


@cbv(router)
class AdminDreamView(BaseView):
    """Класс для работы с мечтами из панели администратора."""

    @router.get(
        "/dream",
        dependencies=[Depends(AuthChecker(is_operator=True))],
        response_model=Page[AdminListDream],
    )
    async def get_admin_dreams(
        self,
        filters: dict = Depends(filter_dream),  # noqa B008
        params: Params = Depends(),  # noqa B008
        sort: list = Depends(sort_dream),  # noqa B008
    ) -> dict:
        """Получение списка мечт из панели администратора."""
        sub_qs = get_achievement_sort_qs()
        query = (
            Dream.join(User)
            .outerjoin(sub_qs, sub_qs.c.user_id == User.id)
            .join(Category)
            .join(Currency, Currency.id == Dream.currency_id)
            .select()
        )
        loader = Dream.distinct(Dream.id).load(
            user=User, category=Category, symbol=Currency.symbol
        )
        dreams = query.gino.load(loader).query
        if filters:
            dreams = dreams.where(and_(*filters))
        if sort:
            dreams = dreams.order_by(*sort)
        dreams = dreams.order_by(
            db.case(value=User.is_vip, whens={True: "0", False or None: "1"}),
            sub_qs.c.a_weight,
            desc(sub_qs.c.received_at),
        )
        result = (await paginate(dreams, params)).dict()
        # Перевод размера собранных средств на мечту в реальный размер для отображения пользователю
        # TODO отрефакторить
        for item in result["items"]:
            item["collected"] = item["collected"] / settings.FINANCE_RATIO
        return result

    @router.get(
        "/dream/{idx}",
        dependencies=[Depends(AuthChecker(is_operator=True))],
        response_model=AdminDetailDream,
    )
    async def get_dream(self, idx: int) -> Dream:
        """Получение данных по конкретной мечте из панели администратора."""
        query = (
            Dream.outerjoin(User)
            .outerjoin(Category)
            .join(Currency, Currency.id == Dream.currency_id)
            .select()
        )
        loader = Dream.distinct(Dream.id).load(
            user=User, category=Category, symbol=Currency.symbol
        )
        dream = query.gino.load(loader).query.where(Dream.id == idx)
        return await dream.gino.first()

    @router.post(
        "/dream", dependencies=[Depends(AuthChecker(is_operator=True))]
    )
    async def create_admin_dream(
        self, dream: AdminDream = Depends(AdminDream.as_form)  # noqa B008
    ):  # noqa ANN201
        """Создание мечты из панели администратора."""
        dream_status = DreamStatus.QUART.value
        user = await User.get(dream.user_id)
        currency_id = settings.EURO_ID
        if user:
            currency_id = user.currency_id
        if user and user.referer:
            dream_status = DreamStatus.HALF.value
        data = await self.check_goal(dream, currency_id)
        data.update(
            {
                "status": dream_status,
                "collected": 0,
                "currency_id": currency_id,
            }
        )
        try:
            await Dream.create(**data)
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )

        return Response(status_code=status.HTTP_201_CREATED)

    @router.patch(
        "/dream/{dream_id}",
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    async def update_admin_dream(
        self,
        dream_id: int,
        dream_info: AdminDream = Depends(AdminDream.as_form),  # noqa B008
    ):  # noqa ANN201
        """Обновление мечты из панели администратора."""
        dream = await Dream.get(dream_id)
        if not dream:
            return Response(
                content="dream not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        currency_id = dream.currency_id
        data = await self.check_goal(dream_info, currency_id)
        try:
            (
                await Dream.update.values(**data)
                .where(Dream.id == dream_id)
                .gino.status()
            )
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        await refresh_dreams_view()
        return Response(status_code=status.HTTP_201_CREATED)

    async def check_goal(self, dream: AdminDream, currency_id: int) -> dict:
        """Проверка лимита мечты."""
        data = dream.dict()
        dream_goal = data["goal"]
        currency = await Currency.query.where(
            Currency.id == currency_id
        ).gino.first()
        is_dream_maker = await Achievement.query.where(
            and_(
                Achievement.user_id == data["user_id"],
                Achievement.received_at != None,  # noqa E711
                Achievement.type_name == AchievementType.DREAM_MAKER.value,
            )
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
        return data

    @router.get(
        "/change-dream-status/{dream_id}",
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    async def change_dream_status(self, dream_id: int) -> None:
        """Запрос на изменение статуса закрытой мечты на активную для тестов."""
        dream = await Dream.get(dream_id)
        if not dream or dream.status != DreamStatus.CLOSED.value:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await dream.update(status=DreamStatus.ACTIVE.value).apply()
        await refresh_dreams_view()


def filter_donations(
    created_at_from: Optional[datetime] = None,
    created_at_to: Optional[datetime] = None,
    search: Optional[str] = "",
    statuses: Optional[str] = Query([]),  # noqa B008
) -> list:
    """Фильтры пожертвований."""
    created_at_to = (
        created_at_to.replace(tzinfo=None) if created_at_to else None
    )
    created_at_from = (
        created_at_from.replace(tzinfo=None) if created_at_from else None
    )
    try:
        statuses = [int(item) for item in statuses.split(",")]
    except:  # noqa B001
        statuses = []

    query_data = (
        (
            created_at_to,
            Donation.created_at <= created_at_to if created_at_to else None,
        ),
        (
            created_at_from,
            Donation.created_at >= created_at_from
            if created_at_from
            else None,
        ),
        (
            search,
            or_(
                cast(Donation.sender_id, String).like(f"%{search}%"),
                cast(Donation.recipient_id, String).like(f"%{search}%"),
                Sender.name.ilike(f"%{search}%"),
                Sender.surname.ilike(f"%{search}%"),
                Recipient.name.ilike(f"%{search}%"),
                Recipient.surname.ilike(f"%{search}%"),
                cast(Donation.amount, String).like(f"%{search}%"),
            )
            if search
            else None,
        ),
        (statuses, Donation.status.in_(statuses) if statuses else None),
    )
    return [query for value, query in query_data if query is not None]


def sort_donations(
    sender_id: Optional[SortChoices] = None,
    sender_name: Optional[SortChoices] = None,
    sender_surname: Optional[SortChoices] = None,
    recipient_id: Optional[SortChoices] = None,
    recipient_name: Optional[SortChoices] = None,
    recipient_surname: Optional[SortChoices] = None,
    amount: Optional[SortChoices] = None,
    status: Optional[SortChoices] = None,
    created_at: Optional[SortChoices] = None,
) -> list:
    """Сортировка полей."""
    sort_type = {SortChoices.asc.value: asc, SortChoices.desc.value: desc}
    query_data = (
        (
            sender_id,
            sort_type[sender_id](Donation.sender_id) if sender_id else None,
        ),
        (
            sender_name,
            sort_type[sender_name](Sender.name) if sender_name else None,
        ),
        (
            sender_surname,
            sort_type[sender_surname](Sender.surname)
            if sender_surname
            else None,
        ),
        (
            recipient_id,
            sort_type[recipient_id](Donation.recipient_id)
            if recipient_id
            else None,
        ),
        (
            recipient_name,
            sort_type[recipient_name](Recipient.name)
            if recipient_name
            else None,
        ),
        (
            recipient_surname,
            sort_type[recipient_surname](Recipient.surname)
            if recipient_surname
            else None,
        ),
        (amount, sort_type[amount](Donation.amount) if amount else None),
        (status, sort_type[status](Donation.amount) if status else None),
        (
            created_at,
            sort_type[created_at](Donation.created_at) if created_at else None,
        ),
    )
    return [query for value, query in query_data if query is not None]


@cbv(router)
class AdminDonationsView(BaseView):
    """Класс для работы с пожертвованиями из консоли администратора."""

    def get_donation_qs(
        self, filters: list = None, sort: list = None
    ) -> Select:
        """Получить запрос по пожертвованиям с фильтрами бд."""
        query = (
            (
                Donation.outerjoin(
                    Sender, Sender.id == Donation.sender_id
                ).outerjoin(Recipient, Recipient.id == Donation.recipient_id)
            )
            .join(Currency, Currency.id == Donation.first_currency_id)
            .select()
        )
        donations = query.gino.load(
            Donation.distinct(Donation.id).load(
                recipient=Recipient, sender=Sender, symbol=Currency.symbol
            )
        ).query
        if filters:
            donations = donations.where(and_(*filters))
        if sort:
            donations = donations.order_by(*sort)
        return donations  # noqa R504

    @router.get(
        "/donation",
        response_model=Page[AdminListDonation],
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    async def get_all_donations(
        self,
        filters: list = Depends(filter_donations),  # noqa B008
        sort: list = Depends(sort_donations),  # noqa B008
        params: Params = Depends(),  # noqa B008
    ) -> dict:
        """Получить список пожертвований."""
        donations = self.get_donation_qs(filters=filters, sort=sort)
        result = (await paginate(donations, params)).dict()
        # Перевод размера доната в реальный размер для отображения пользователю
        # TODO отрефакторить
        for item in result["items"]:
            item["first_amount"] = (
                item["first_amount"] / settings.FINANCE_RATIO
            )
        return result

    @router.get(
        "/donation/user/{idx}",
        response_model=Page[AdminListDonation],
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    async def get_user_donations(
        self,
        idx: int,
        filters: list = Depends(filter_donations),  # noqa B008
        sort: list = Depends(sort_donations),  # noqa B008
        params: Params = Depends(),  # noqa B008
    ) -> dict:
        """Получить список пожертвований пользователя(лю)."""
        donations = self.get_donation_qs(filters=filters, sort=sort).where(
            or_(Donation.sender_id == idx, Donation.recipient_id == idx)
        )
        result = (await paginate(donations, params)).dict()
        # Перевод размера доната в реальный размер для отображения пользователю
        # TODO отрефакторить
        for item in result["items"]:
            item["first_amount"] = (
                item["first_amount"] / settings.FINANCE_RATIO
            )
        return result


@cbv(router)
class AdminCurrenciesView(BaseView):
    """Класс для работы с валютами из консоли администратора."""

    @router.get(
        "/currencies",
        response_model=Page[AdminListCurrencies],
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    async def get_admin_currencies(
        self, params: Params = Depends()  # noqa B008
    ) -> dict:
        """Получить список валют с размерами донатов."""
        query = Currency.outerjoin(DonateSize).select()
        loader = Currency.distinct(Currency.id).load(
            add_donate_size=DonateSize
        )
        currency = query.gino.load(loader).query.order_by(Currency.sort_number)
        count_query = currency.with_only_columns((Currency.id,)).alias()
        total = (
            await db.select(
                [db.func.count(db.func.distinct(count_query.c.id))]
            )
            .select_from(count_query)
            .gino.scalar()
        )
        result = (await custom_paginate(currency, total, params)).dict()
        # Перевод курса валюты в реальный для отображения пользователю
        # TODO отрефакторить
        for item in result["items"]:
            item["course"] = item["course"] / settings.FINANCE_RATIO
            for level in item["donate_sizes"]:
                level["size"] = level["size"] / settings.FINANCE_RATIO
            item["donate_sizes"] = sorted(
                item["donate_sizes"], key=lambda donate: donate["level"]
            )
        return result

    @router.post(
        "/currencies", dependencies=[Depends(AuthChecker(is_operator=True))]
    )
    async def create_currency(self, data: AdminCurrencyModel):  # noqa ANN201
        """Метод для создания валюты."""
        data = data.dict()
        donation_sizes = self.check_donation_sizes(data)
        try:
            currency_id = (await Currency.create(**data)).id
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        donation_sizes = sorted(donation_sizes, key=lambda k: k["level"])
        try:
            for donation_size in donation_sizes:
                donation_size["currency_id"] = currency_id
            await DonateSize.insert().gino.all(donation_sizes)
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        return Response(status_code=status.HTTP_201_CREATED)

    @router.patch(
        "/currencies/{currency_id}",
        dependencies=[Depends(AuthChecker(is_operator=True))],
    )
    async def update_currency(
        self, currency_id: int, data: AdminCurrencyModel
    ):  # noqa ANN201
        """Метод для редактирования валюты."""
        if currency_id == settings.EURO_ID and (
            data.code != settings.EURO_CODE
            or data.symbol != settings.EURO_SYMBOL
            or data.name != settings.EURO_NAME
            or data.is_active != True  # noqa E712
        ):
            return Response(
                content="euro is not edited",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        data = data.dict()
        donation_sizes = self.check_donation_sizes(data)
        try:
            await (
                Currency.update.values(**data)
                .where(Currency.id == currency_id)
                .gino.status()
            )
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        try:
            async with db.transaction():
                for donation_size in donation_sizes:
                    await (
                        DonateSize.update.values(size=donation_size["size"])
                        .where(
                            and_(
                                DonateSize.currency_id == currency_id,
                                DonateSize.level == donation_size["level"],
                            )
                        )
                        .gino.status()
                    )
        except GinoException as exc:
            return Response(
                content=str(exc), status_code=status.HTTP_400_BAD_REQUEST
            )
        if not data["is_active"]:
            users_with_inactive_currency = await User.query.where(
                User.currency_id == currency_id
            ).gino.all()
            for user in users_with_inactive_currency:
                await recalculation(
                    user.id, user.currency_id, settings.EURO_ID
                )
            (
                await User.update.values(currency_id=settings.EURO_ID)
                .where(User.currency_id == currency_id)
                .gino.status()
            )
        return Response(status_code=status.HTTP_201_CREATED)

    def check_donation_sizes(self, data):  # noqa ANN201
        donation_sizes = data.pop("donation_sizes")
        if len(donation_sizes) != settings.NEED_TO_DONATE_NUM:
            return Response(
                content=f"quantity of donation sizes should be "
                f"{settings.NEED_TO_DONATE_NUM}",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return donation_sizes


@cbv(router)
class AdminUserView(BaseView):
    """Представление для работы с пользователями из админки."""

    @router.get(
        "/special-users",
        dependencies=[Depends(AuthChecker(is_admin=True))],
        response_model=ResponseSpecialUsersModel,
    )
    async def get_special_users(
        self, search: str = "", params: Params = Depends()  # noqa B008
    ) -> dict:
        """Получить список всех пользователей с достижением.

        Топ-фандрайзер, или имеющих вип-статус,
        или имеющих благотворительные мечты, отсортированный
        по дате получения донатов.
        """
        query = f"""
        SELECT id, name, surname, STRING_AGG(type_name, ', ') AS status
          FROM (SELECT "user".id, name, surname, 'top_fundraiser'
                        AS type_name, last_donate_date
                  FROM "user"
                  JOIN (SELECT user_id, type_name
                          FROM achievement
                         WHERE type_name = 'top_fundraiser'
                           AND received_at IS NOT NULL) ach ON ach.user_id = "user".id
             LEFT JOIN (SELECT recipient_id, MAX(sub_at) AS last_donate_date
                          FROM donation
                      GROUP BY recipient_id) d ON d.recipient_id = "user".id
              GROUP BY "user".id, type_name, last_donate_date
                 UNION
                        SELECT "user".id, name, surname, 'vip' AS is_vip, last_donate_date
                          FROM "user"
                     LEFT JOIN (SELECT recipient_id, MAX(sub_at) AS last_donate_date
                                  FROM donation
                              GROUP BY recipient_id) d ON d.recipient_id = "user".id
                         WHERE is_vip = TRUE
                      GROUP BY "user".id, last_donate_date
                         UNION
                                SELECT "user".id, name, surname, 'benefactor' AS type_dream, last_donate_date
                                  FROM "user"
                                  JOIN (SELECT user_id, type_dream
                                          FROM dream
                                         WHERE type_dream = 'Благотворительная') p
                                            ON p.user_id = "user".id
                             LEFT JOIN (SELECT recipient_id, MAX(sub_at) AS last_donate_date
                                          FROM donation
                                      GROUP BY recipient_id) d ON d.recipient_id = "user".id
                              GROUP BY "user".id, type_dream, last_donate_date
                              ORDER BY last_donate_date) AS s
         WHERE name ILIKE '%{search}%'
            OR surname ILIKE '%{search}%'
      GROUP BY id, name, surname"""

        total = await db.all(
            db.text(f"SELECT COUNT(*) AS cnt FROM ({query}) AS q;")
        )

        query_page = (
            f"{query} OFFSET {(params.page - 1) * params.size}"
            f" LIMIT {params.size}"
        )
        users = await db.all(db.text(f"{query_page};"))
        special_users = []
        for user in users:
            user = dict(user)
            user["status"] = user["status"].split(", ")
            special_users.append(user)
        return {
            "items": special_users,
            "total": total[0].cnt,
            "page": params.page,
            "size": params.size,
        }

    @router.post(
        "/change-vip-status",
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    @need_dreams_view_refresh
    async def change_vip_status(self, user_info: VipStatus) -> dict:
        """Изменить вип-статус пользователя."""
        user = await User.get(user_info.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await user.update(is_vip=user_info.is_vip).apply()
        return {"result": "ok"}

    @router.get(
        "/user/{user_id}",
        response_model=ProfileInfo,
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    async def get_profile_info(self, user_id: int) -> User:
        """Запрос на получение данных пользователя."""
        user = await User.get(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    @router.post(
        "/user/{user_id}/change-subscribe",
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    @errors_decorator
    async def change_subscribe(
        self, user_id: int, info: SubscribeTillModel
    ) -> None:
        """Запрос на изменение срока окончания подписки пользователя."""
        if not (user := await User.get(user_id)):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
            )
        subscribe_till = datetime.strptime(info.subscribe_till, "%Y-%m-%d")
        service = SubscriptionService(
            self.request.app, self.request.app.state.redis
        )
        if not await service.change_subscribe_till(
            self.request.headers["Authorization"], user, subscribe_till
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    @router.post(
        "/create-review",
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    @inject
    async def create_review(
        self,
        review: ReviewModel = Depends(ReviewModel.as_form),  # noqa B008
        review_service: ReviewService = Depends(  # noqa: B008
            Provide[Container.review_service]
        ),
    ) -> ResponseReviewModel:
        """Запрос на создание отзыва."""
        try:
            created_review = await review_service.create_review(review.dict())
        except CreateReviewError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        return ResponseReviewModel(**created_review.to_dict())

    @router.patch(
        "/update-review/{review_id}",
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    @inject
    async def update_review(
        self,
        review_id: int,
        review: ReviewModel = Depends(ReviewModel.as_form),  # noqa B008
        review_service: ReviewService = Depends(  # noqa: B008
            Provide[Container.review_service]
        ),
    ) -> ResponseReviewModel:
        """Запрос на редактирование отзыва."""
        try:
            updated_review = await review_service.update_review(
                review_id, review.dict()
            )
        except UpdateReviewError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        return ResponseReviewModel(**updated_review.to_dict())

    @router.get(
        "/reviews",
        response_model=Page[ResponseReviewModel],
        dependencies=[Depends(AuthChecker(is_admin=True))],
    )
    @inject
    async def get_admin_reviews(
        self,
        lang: Optional[str] = None,
        params: Params = Depends(),  # noqa B008
        review_service: ReviewService = Depends(  # noqa: B008
            Provide[Container.review_service]
        ),
    ) -> Union[AbstractPage, dict]:
        """Получение списка отзывов для админки."""
        return await review_service.get_reviews(params, lang)
