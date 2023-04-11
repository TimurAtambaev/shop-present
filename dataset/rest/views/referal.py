"""Модуль с представлениями для работы с реф программой."""
import textwrap
from datetime import datetime
from typing import Iterable, List, Optional

from fastapi import Depends, HTTPException
from fastapi_pagination import Params
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import and_, insert
from starlette import status

from dataset.config import settings
from dataset.migrations import db
from dataset.rest.models.donation import ReferalDonation
from dataset.rest.models.referal import (
    PaginateMyCommunity,
    Referal,
    ResponseUsersModel,
    UserReferal,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.dream import get_translation_dream
from dataset.rest.views.utils import get_ratio
from dataset.tables.donate_size import DonateSize
from dataset.tables.donation import Donation, DonationStatus
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.user import User
from dataset.utils.user import user_has_subscribe

router = InferringRouter()


def get_query_user_tree(user_id: int) -> str:
    """Метод возвращает запрос на получение связанных реферов пользователя."""
    query_user_tree = f"""
    WITH RECURSIVE tmp AS
    (SELECT id, referer, refer_code, 0 AS LEVEL , name, avatar
            FROM public.user
           WHERE id = {user_id} UNION ALL
                 SELECT u.id, u.referer, u.refer_code, t.level +1 AS LEVEL , u.name, u.avatar
                   FROM tmp t
             INNER JOIN public.user u ON u.referer = t.refer_code)
     SELECT id, LEVEL , name, avatar
       FROM tmp
      WHERE LEVEL <= {settings.NEED_TO_DONATE_NUM}"""
    return query_user_tree  # noqa R504


@cbv(router)
class ReferalView(BaseView):
    """Представление с реферальными запросами."""

    def top(self) -> Optional[Iterable]:
        """Список активных мечт топ-фандрайзеров и дриммейкеров.

        С действующей подпиской на Имрикс.
        """
        return db.all(
            db.text(
                f"""
            SELECT dream.user_id, dream.id, s
              FROM dream
              JOIN (SELECT id
                      FROM "user"
                     WHERE "user".is_active != FALSE
                       AND "user".id != {self.request.user.id}
                       AND ("user".paid_till >= CURRENT_DATE
                        OR "user".trial_till >= NOW())) u
                        ON u.id = dream.user_id
              JOIN (SELECT user_id, received_at
                      FROM achievement
                     WHERE (type_name = 'top_fundraiser'
                        OR type_name = 'dream_maker')
                       AND received_at IS NOT NULL) ach
                        ON ach.user_id = dream.user_id
         LEFT JOIN (SELECT dream_id, MAX(sub_at) AS s
                      FROM donation
                  GROUP BY dream_id) d ON d.dream_id = dream.id
             WHERE dream.status = {DreamStatus.ACTIVE.value}
               AND dream.type_dream = 'Пользовательская'
               AND dream.user_id != {self.request.user.id}
          GROUP BY dream.user_id, dream.id, ach.received_at, s;"""
            ).gino.query
        )

    def vip(self) -> Optional[Iterable]:
        """Список активных мечт пользователей.

        C вип-статусом, с действующей подпиской на Имрикс.
        """
        return db.all(
            db.text(
                f"""
        SELECT dream.user_id, dream.id, s
          FROM dream
          JOIN (SELECT id
                  FROM "user"
                 WHERE "user".is_active != FALSE
                   AND "user".id != {self.request.user.id}
                   AND "user".is_vip = TRUE
                   AND ("user".paid_till >= CURRENT_DATE
                    OR "user".trial_till >= NOW())) u ON u.id = dream.user_id
     LEFT JOIN (SELECT dream_id, MAX(sub_at) AS s
                  FROM donation
              GROUP BY dream_id) d ON d.dream_id = dream.id
         WHERE dream.status = {DreamStatus.ACTIVE.value}
           AND dream.type_dream = 'Пользовательская'
           AND dream.user_id != {self.request.user.id}
      GROUP BY dream.user_id, dream.id, s;"""
            ).gino.query
        )

    def charity(self) -> Optional[Iterable]:
        """
        Список благотворительных мечт.

        (отсортированный по количеству полученных донатов)
        """
        return db.all(
            db.text(
                f"""
        SELECT dream.user_id, dream.id, s
          FROM dream
          JOIN (SELECT id
                  FROM "user"
                 WHERE "user".is_active != FALSE
                   AND "user".id != {self.request.user.id}
                   AND ("user".paid_till >= CURRENT_DATE
                    OR "user".trial_till >= NOW())) u ON u.id = dream.user_id
     LEFT JOIN (SELECT dream_id, MAX(sub_at) AS s
                  FROM donation
              GROUP BY dream_id) d ON d.dream_id = dream.id
         WHERE dream.type_dream = 'Благотворительная'
           AND dream.status = {DreamStatus.ACTIVE.value}
           AND dream.user_id != {self.request.user.id}
      GROUP BY dream.user_id, dream.id, s;"""
            ).gino.query
        )

    @router.post(
        "/referal",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={404: {}, 403: {}},
    )
    async def subscribe_to_ref(self, ref: Referal) -> None:
        """Связать пользователя с реферером."""
        if ref.ref_code:
            referer = await User.query.where(
                User.refer_code == ref.ref_code
            ).gino.first()
        elif ref.sub_dream_id:
            referer = await User.load(dream=Dream).query.where(
                Dream.id == ref.sub_dream_id
            )

        if not referer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if self.request.user.referer:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        async with db.transaction():
            await User.update.values(referer=referer.refer_code).where(
                User.id == self.request.user.id
            ).gino.status()
            await Dream.update.values(status=DreamStatus.HALF.value).where(
                and_(
                    Dream.status == DreamStatus.QUART.value,
                    Dream.user_id == self.request.user.id,
                )
            ).gino.status()

    @router.get(
        "/dream/{dream_id}/referals",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=List[ReferalDonation],
    )
    async def get_dreams_to_sup(self, dream_id: int) -> List:
        """Получить 4 мечты для реферальных донатов."""
        dream = await (
            Dream.query.where(
                and_(
                    Dream.id == dream_id,
                    Dream.user_id == self.request.user.id,
                    Dream.status == DreamStatus.HALF.value,
                )
            ).gino.first()
        )
        if not dream:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        half_dreams = await Dream.query.where(
            and_(
                Dream.user_id == self.request.user.id,
                Dream.status == DreamStatus.HALF.value,
            )
        ).gino.all()
        users_donations = await Donation.query.where(
            and_(
                Donation.sender_id == self.request.user.id,
                Donation.status > DonationStatus.NEW.value,
                Donation.status < DonationStatus.FAILED.value,
            )
        ).gino.all()
        paid_donations_ids = {donation.id for donation in users_donations}
        dreams_with_paid_referral_donations = []
        for half_dream in half_dreams:
            if not paid_donations_ids.isdisjoint(
                set(half_dream.ref_donations)
            ):
                dreams_with_paid_referral_donations.append(half_dream.id)

        # у пользователя может быть только 1 активируемая мечта
        # (с привязкой к которой совершил хотя бы 1 реферальный донат)
        if (
            dreams_with_paid_referral_donations
            and dream_id not in dreams_with_paid_referral_donations
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        # если есть 4 сформированных реферальных доната,
        # проверяем донаты на актуальность
        if len(dream.ref_donations) == settings.NEED_TO_DONATE_NUM:
            await self.check_ref_donations(dream)

        if (
            not (donations_ids := dream.ref_donations)
            or len(dream.ref_donations) < settings.NEED_TO_DONATE_NUM
        ):
            ids = await self.get_refs_by_dream(dream.user_id)
            donations_ids = await self.create_refs_donations(
                dream_id, ids, dream
            )

        query = (
            await Donation.outerjoin(User, User.id == Donation.recipient_id)
            .outerjoin(Dream, Dream.id == Donation.dream_id)
            .select()
            .where(Donation.id.in_(donations_ids))
            .gino.load(Donation.load(dream=Dream.load(user=User)))
            .query.order_by(Donation.level_number)
            .gino.all()
        )
        for item in query:
            translation = await get_translation_dream(
                item.dream.to_dict(), self.request["language"]
            )
            item.dream.title = translation["title"]
            item.dream.description = textwrap.shorten(
                translation["description"],
                width=settings.SHORT_DESCRIPTION_LEN,
                placeholder="...",
            )
        return query

    async def check_ref_donations(self, dream: Dream) -> None:
        """Проверить и при необходимости заменить мечты для реф.донатов."""
        # TODO отрефакторить
        ref_donations = dream.ref_donations
        dream_ids = [
            donation.dream_id
            for donation in (
                await Donation.query.where(
                    Donation.id.in_(ref_donations)
                ).gino.all()
            )
        ]
        for num, ref_donation in enumerate(ref_donations):
            donation = await Donation.get(ref_donation)
            if donation:
                recipient_dream = await Dream.get(donation.dream_id)
                recipient = await User.get(donation.recipient_id)
                if recipient_dream.id in dream_ids:
                    dream_ids.remove(recipient_dream.id)
            if not donation or (
                donation.status == DonationStatus.NEW.value
                and (
                    recipient_dream.status != DreamStatus.ACTIVE.value
                    or not recipient.is_active
                    or not user_has_subscribe(recipient)
                    or recipient.id == self.request.user.id
                    or recipient_dream.id in dream_ids
                )
            ):
                currency_id = self.request.user.currency_id
                donate_size = (
                    await DonateSize.query.where(
                        and_(
                            DonateSize.currency_id == currency_id,
                            DonateSize.level == num + 1,
                        )
                    ).gino.first()
                ).size
                dreams_replace = await self.get_replace_dreams()
                if not dreams_replace:
                    return
                default_donation_data = []
                donation_data = await self.append_donation_data(
                    default_donation_data,
                    num,
                    dreams_replace[0],
                    currency_id,
                    donate_size,
                )
                donation = (
                    await insert(Donation.__table__)
                    .values(donation_data)
                    .returning(Donation.id)
                    .gino.first()
                )
                ref_donations[num] = donation[0]
                await dream.update(ref_donations=ref_donations).apply()

    async def get_replace_dreams(self) -> List[list]:
        """Получить мечты для замены."""
        dreams_top = await self.top()
        dreams_vip = await self.vip()
        dreams_charity = await self.charity()
        dreams_replace = dreams_top + dreams_vip + dreams_charity
        for num, item in enumerate(dreams_replace):
            if item[2] is None:
                i = list(item)
                i[2] = datetime(2000, 1, 1)
                dreams_replace[num] = i
        return sorted(dreams_replace, key=lambda k: k[2])

    async def create_refs_donations(
        self, dream_id: int, ids: list, dream: Dream
    ) -> List[int]:
        """Создать реферальные донаты."""
        donation_data = []
        dreams_replace = await self.get_replace_dreams()
        dreams_list = iter(dreams_replace)
        general_pair = []

        for item in ids:
            if all(item):
                general_pair.append(item)
                continue
            try:
                next_dream = next(dreams_list)
                while next_dream[1] in [pair[1] for pair in general_pair]:
                    next_dream = next(dreams_list)
                general_pair.append(next_dream)
            except StopIteration:
                break
        currency_id = self.request.user.currency_id
        donate_sizes = await DonateSize.query.where(
            DonateSize.currency_id == currency_id
        ).gino.all()
        level_sizes = {size.level: size.size for size in donate_sizes}
        for num, pair in enumerate(general_pair, start=1):
            amount = level_sizes[num]
            len_data_update = len(donation_data)
            await self.append_donation_data(
                donation_data, len_data_update, pair, currency_id, amount
            )
        if not donation_data:
            return []

        async with db.transaction():
            ids = []
            if len(dream.ref_donations) == settings.FIRST_DONATION:
                donation_data = donation_data[1:]
                ids.append(dream.ref_donations[0])

            donations = (
                await insert(Donation.__table__)
                .values(donation_data)
                .returning(Donation.id)
                .gino.all()
            )
            ids.extend([idx[0] for idx in donations])

            await Dream.update.values(ref_donations=ids).where(
                Dream.id == dream_id
            ).gino.status()
        return ids

    async def append_donation_data(
        self,
        donation_data: list,
        len_data_update: int,
        dreams_reserve: list,
        currency_id: int,
        amount: int,
    ) -> List:
        """Подстановка недостающих мечт в список мечт для донатов."""
        recipient_id = dreams_reserve[0]
        ratio = await get_ratio(currency_id, recipient_id)
        recipient_amount = amount * ratio
        dic = {
            "dream_id": dreams_reserve[1],
            "recipient_id": recipient_id,
            "sender_id": self.request.user.id,
            "amount": recipient_amount,
            "first_amount": amount,
            "currency_id": currency_id,
            "first_currency_id": currency_id,
            "level_number": len_data_update + 1,
            "status": DonationStatus.NEW.value,
            "sub_at": datetime.now(),
        }
        donation_data.append(dic)
        return donation_data

    @staticmethod
    async def get_refs_by_dream(
        user_id: int, limit: int = settings.NEED_TO_DONATE_NUM
    ) -> List[int]:
        """Получить id рефереров."""
        offset = 1  # Чтобы исключить собственный id
        result = await db.all(
            db.text(
                f"""
    WITH RECURSIVE tmp AS
    (SELECT id, referer, refer_code
            FROM public.user
           WHERE id = {user_id} UNION ALL
                 SELECT u.id, u.referer, u.refer_code
                   FROM tmp t
             INNER JOIN public.user u ON u.refer_code = t.referer)
     SELECT id
       FROM tmp
     OFFSET {offset}
      LIMIT {limit};"""
            )
        )
        pre_result = tuple([res[0] for res in result])
        query = f"""
        SELECT u.id, d.id
          FROM public.user AS u
     LEFT JOIN (SELECT id, user_id
                  FROM dream
                 WHERE dream.status = {DreamStatus.ACTIVE.value}
                   AND dream.type_dream != 'Благотворительная') AS d
                    ON d.user_id = u.id
         WHERE u.is_active != FALSE
           AND (u.paid_till >= CURRENT_DATE
            OR u.trial_till >= NOW())
           AND u.id IN """
        if len(pre_result) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user has no referrers",
            )
        if len(pre_result) == 1:
            id_ref = await db.all(db.text(query + f"({pre_result[0]});"))
        else:
            id_ref = await db.all(db.text(query + f"{pre_result};"))

        id_ref = list(  # noqa C413
            sorted(id_ref, key=lambda x: pre_result.index(x[0]))
        )

        while len(id_ref) < settings.NEED_TO_DONATE_NUM:
            id_ref.append((None, None))
        return id_ref

    @router.get("/my-community", response_model=PaginateMyCommunity)
    async def get_my_community(
        self,
        params: Params = Depends(),  # noqa B008
        level: int = None,
        referal_links: str = None,
    ) -> dict:
        """Получение списка пользователей из моего сообщества."""
        query = get_query_user_tree(self.request.user.id)
        if level:
            query = f"{query} AND level={level}"
        if referal_links:
            query = f"{query} AND referer='{referal_links}'"
        """Отнимаем единицу в query чтобы отображение происходило с первого
        элемента, иначе отображение происходит с 50 элемента."""
        total = await db.all(
            db.text(f"SELECT COUNT(*) AS cnt FROM ({query}) AS q;")
        )
        query = (
            f"{query} OFFSET {(params.page - 1) * params.size}"
            f" LIMIT {params.size}"
        )
        result = await db.all(db.text(f"{query};").gino.query)
        return {
            "items": result,
            "total": total[0].cnt,
            "page": params.page,
            "size": params.size,
        }

    @router.get("/referal-links")
    async def get_referal_links(self) -> List:
        """Метод для получения списка реферальных ссылок."""
        query = f"""
        WITH RECURSIVE tmp AS
        (SELECT id, referer, refer_code
                FROM public.user
               WHERE id = {self.request.user.id} UNION ALL
                     SELECT u.id, u.referer, u.refer_code
                       FROM tmp t
                 INNER JOIN public.user u ON u.referer = t.refer_code)
         SELECT DISTINCT referer
           FROM tmp
         OFFSET 1"""
        result = await db.all(db.text(f"{query};").gino.query)
        return [ref[0] for ref in result]

    @router.get("/search-by-refer", response_model=UserReferal)
    async def search_by_refer(self, refer_code: str) -> User:
        """Методя для получения пользователя по рефер коду."""
        user = await (
            User.query.where(User.refer_code == refer_code).gino.first()
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    @router.get("/my-referals", response_model=ResponseUsersModel)
    async def get_my_referals(
        self, params: Params = Depends(), level: int = None  # noqa B008
    ) -> dict:
        """Получить список всех рефералов текущего пользователя с пагинацией.

        До 4-го уровня включительно, с фильтрацией по уровням,
        с информацией есть ли у каждого подтвержденный реферальный донат
        текущему пользователю.
        """
        query = await self.referals_query("LEFT JOIN")
        sort_express = "ORDER BY (confirmed IS NOT NULL) DESC, confirmed DESC"
        referals = (
            f"{query} WHERE level={level} {sort_express}"
            if level
            else f"{query} {sort_express}"
        )
        return await self.get_paginate(referals, params)

    @router.get("/my-donators", response_model=ResponseUsersModel)
    async def get_my_donators(
        self, params: Params = Depends(), level: int = None  # noqa B008
    ) -> dict:
        """Получить список всех задонативших текущему пользователю.

        Зарегистрированные пользователи, подтвержденные донаты.
        """
        referals_with_confirm_donations_query = await self.referals_query(
            "JOIN"
        )
        free_donators_query = f"""
     SELECT donater.id, name, surname, avatar, country_id, NULL AS level,
            TRUE AS confirm_donate, MAX(confirmed_at) AS confirmed
       FROM public.user donater
       JOIN donation ON sender_id = donater.id
      WHERE recipient_id = {self.request.user.id}
        AND status > {DonationStatus.WAITING_FOR_CONFIRMATION.value}
        AND status < {DonationStatus.FAILED.value}
        AND confirmed_at IS NOT NULL
        AND level_number IS NULL
   GROUP BY donater.id, name, surname, avatar, country_id"""
        donators = (
            f"{referals_with_confirm_donations_query} WHERE level={level} "
            f"ORDER BY confirmed DESC"
            if level
            else f"{referals_with_confirm_donations_query} UNION "
            f"{free_donators_query} ORDER BY confirmed DESC"
        )
        return await self.get_paginate(donators, params)

    async def referals_query(self, join_type: str) -> str:
        """Формирование запроса в базу на список рефералов пользователя."""
        # получаем рекурсивно рефералов 1-4 уровней и присоединяем таблицу
        # донатов для отображения информации о наличии
        # реферального доната текущему пользователю у каждого реферала
        return f"""
           SELECT id, name, surname, avatar, country_id, level,
                  CASE WHEN confirmed IS NOT NULL THEN TRUE ELSE FALSE END
                  AS confirm_donate, confirmed
             FROM (WITH RECURSIVE tmp AS
           (SELECT id, refer_code, name, surname, avatar, country_id,
                   0 AS level
              FROM public.user
             WHERE id = {self.request.user.id}
             UNION
            SELECT u.id, u.refer_code, u.name, u.surname, u.avatar,
                   u.country_id, level + 1 AS level
              FROM tmp t
        INNER JOIN public.user u ON u.referer = t.refer_code
             WHERE level < {settings.LIMIT_REFERAL_LEVEL})
            SELECT DISTINCT id, name, surname, avatar, country_id, level
              FROM tmp
             WHERE level > 0) referal
       {join_type}
           (SELECT sender_id, MAX(confirmed_at) AS confirmed
              FROM donation
             WHERE recipient_id = {self.request.user.id}
               AND level_number IS NOT NULL
               AND status > {DonationStatus.WAITING_FOR_CONFIRMATION.value}
               AND status < {DonationStatus.FAILED.value}
               AND confirmed_at IS NOT NULL
          GROUP BY sender_id) donate ON referal.id = donate.sender_id"""

    async def get_paginate(
        self, query: str, params: Params = Depends()  # noqa B008
    ) -> dict:
        """Метод для пагинации."""
        total = await db.all(
            db.text(f"SELECT COUNT(*) AS cnt FROM ({query}) AS q;")
        )
        query_page = (
            f"{query} OFFSET {(params.page - 1) * params.size}"
            f" LIMIT {params.size}"
        )
        users = await db.all(db.text(f"{query_page};"))
        return {
            "items": users,
            "total": total[0].cnt,
            "page": params.page,
            "size": params.size,
        }
