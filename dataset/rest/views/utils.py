"""Модуль с счётчиком реферов."""
import asyncio
import functools
import json
import re
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Union

from aioredis import Redis
from fastapi import FastAPI, HTTPException
from phonenumbers import parse, region_code_for_country_code
from sqlalchemy import and_, func
from sqlalchemy.sql import Select
from starlette import status

from dataset.config import settings
from dataset.core.log import LOGGER
from dataset.core.mail.utils import send_mail
from dataset.mail_templates import DonateNotificationTemplate
from dataset.migrations import db
from dataset.rest.views.achievement import create_achievement
from dataset.rest.views.event_tasks import event_dream
from dataset.tables.achievement import (
    Achievement,
    AchievementRefNum,
    AchievementType,
)
from dataset.tables.currency import Currency
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.event import Event, TypeEvent
from dataset.tables.user import User


async def refresh_dreams_view() -> None:
    """Команда обновления вью в БД с мечтами."""
    await db.status(db.text("REFRESH MATERIALIZED VIEW dreams_list;"))


def need_dreams_view_refresh(function: Callable) -> Callable:
    """Декоратор для обновления вью в базе."""

    @functools.wraps(function)
    async def wrapper(*args: tuple, **kwargs: dict) -> Any:
        """Функция-обертка."""
        result = await function(*args, **kwargs)
        await refresh_dreams_view()
        return result  # noqa: R504

    return wrapper


@need_dreams_view_refresh
async def recount_refs(redis: Redis, ref_code: str) -> None:
    """Метод для обновления счётчика реферов."""
    if not ref_code:
        return
    query = (
        User.outerjoin(Dream, Dream.user_id == User.id)
        .select()
        .where(
            and_(
                User.referer == ref_code,
                Dream.status == DreamStatus.ACTIVE.value,
            )
        )
    )
    count = (
        await func.count().select().select_from(query.alias()).gino.scalar()
    )
    await (
        User.update.values(refer_count=count)
        .where(User.refer_code == ref_code)
        .gino.status()
    )
    referer = await User.query.where(User.refer_code == ref_code).gino.first()
    await receive_achievement(redis, referer)


async def receive_achievement(redis: Redis, user: User) -> None:
    """Функция выдачи достижений."""
    active_dream = await (
        Dream.query.where(Dream.user_id == user.id)
        .where(Dream.status == DreamStatus.ACTIVE.value)
        .gino.first()
    )
    if active_dream:
        await assign_received_at(user.id, AchievementType.UFANDAO_MEMBER.value)
    refer_count = user.refer_count or 0
    for item in AchievementRefNum:
        if refer_count >= item.value:
            await assign_received_at(user.id, item.name)
    has_dream_maker_event = await Event.query.where(
        and_(
            Event.user_id == user.id,
            Event.type_event == AchievementType.DREAM_MAKER.value,
        )
    ).gino.first()
    if (
        refer_count >= settings.DREAM_MAKER_INVITATIONS
        and not has_dream_maker_event
    ):
        await event_dream(
            user=user,
            dream=active_dream,
            type_event=TypeEvent.MAKER.value,
        )
        await send_notification(redis, user.id)


async def assign_received_at(user_id: int, type_name: str) -> None:
    """Функция присвоения достижению даты и времени получения."""
    await create_achievement(user_id)
    await (
        Achievement.update.values(received_at=datetime.now())
        .where(Achievement.user_id == user_id)
        .where(Achievement.type_name == type_name)
        .where(Achievement.received_at.is_(None))
        .gino.status()
    )


def handle_error(func: Callable) -> Callable:
    """Декоратор обработчик ошибок."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Выполнить обертку над функцией."""
        try:
            return await func(*args, **kwargs)
        except AssertionError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return wrapper


async def get_unread_events(
    redis: Redis, user: User
) -> List[Union[str, bytes]]:
    """Получить все непрочитанные сообытия пользователя."""
    data = []
    for key in settings.NOTIFICATION_EVENTS:
        data.append((await redis.get(f"{key}-user-{user.id}")))

    return data


async def read_all_events(redis: Redis, user: User) -> None:
    """Прочитать все непрочитанные события пользователя."""
    for key in settings.NOTIFICATION_EVENTS:
        await redis.set(
            f"{key}-user-{user.id}", json.dumps({"label": key, "count": 0})
        )
        await redis.publish(
            f"user-{user.id}", json.dumps({"label": key, "count": 0})
        )


async def read_one_event(
    redis: Redis, user: User, donate: bool = None
) -> None:
    """Прочитать одно событие пользователя."""
    events = (
        [settings.UNREAD_EVENTS, settings.UNCONFIRMED_DONATIONS]
        if donate
        else [settings.UNREAD_EVENTS]
    )
    for key in events:
        data = await redis.get(f"{key}-user-{user.id}")
        update_count = 0
        if data and json.loads(data)["count"] > 0:
            update_count = json.loads(data)["count"] - 1
        await redis.set(
            f"{key}-user-{user.id}",
            json.dumps({"label": key, "count": update_count}),
        )
        await redis.publish(
            f"user-{user.id}",
            json.dumps({"label": key, "count": update_count}),
        )


def get_phone_info(phone: str) -> Dict:
    """Получить код страны в формате dial/iso."""
    try:
        if phone:
            dial = parse(f"+{phone}").country_code
            return {"iso2": region_code_for_country_code(dial), "dial": dial}
    except Exception as err:
        LOGGER.error(err)  # noqa G200
    return {}


def get_achievement_sort_qs() -> Select:
    """Получить запрос для сортировки по достижениям."""
    achievements_case = db.case(
        value=Achievement.type_name,
        whens={
            "ufandao_member": "4",
            "ufandao_friend": "3",
            "ufandao_fundraiser": "2",
            "top_fundraiser": "1",
            "dream_maker": "0",
        },
    )
    return (
        Achievement.query.with_only_columns(
            [
                Achievement.user_id,
                func.min(achievements_case).label("a_weight"),
                func.max(Achievement.received_at).label("received_at"),
            ]
        )
        .where(Achievement.received_at != None)  # noqa E711
        .group_by(Achievement.user_id)
        .alias()
    )


async def get_ratio(currency_id: int, user_id: int) -> float:
    """Получить отношение курсов валют."""
    user = await User.get(user_id)
    sender_course = (
        await Currency.query.where(Currency.id == currency_id).gino.first()
    ).course
    recipient_course = (
        await Currency.query.where(
            Currency.id == user.currency_id
        ).gino.first()
    ).course
    return recipient_course / sender_course


@need_dreams_view_refresh
async def activate_another_dream(user: User) -> None:
    """Активация мечты в статусе 4/4 при наличии подписки или триала.

    В случае, если активная мечта закрыта или исполнена.
    """
    dream_whole = await Dream.query.where(
        and_(
            Dream.user_id == user.id,
            Dream.status == DreamStatus.WHOLE.value,
        )
    ).gino.first()
    dream_active = await Dream.query.where(
        and_(
            Dream.user_id == user.id,
            Dream.status == DreamStatus.ACTIVE.value,
        )
    ).gino.first()
    if (
        dream_whole
        and not dream_active
        and (
            (user.paid_till and user.paid_till >= date.today())
            or (user.trial_till and user.trial_till > datetime.now())
        )
    ):
        await dream_whole.update(status=DreamStatus.ACTIVE.value).apply()


async def donate_notice_email(
    email: str,
    name: str,
    app: FastAPI,
    language: str,
) -> None:
    """Отправить уведомление получателю доната."""
    asyncio.create_task(
        send_mail(
            email,
            DonateNotificationTemplate(
                app, email=email, name=name, language=language
            ),
            language,
        )
    )


async def send_notification(
    redis: Redis, user_id: int, donate: bool = None
) -> None:
    """Отправить пользователю уведомление о событии в редис."""
    if not user_id:
        return
    events = (
        [settings.UNREAD_EVENTS, settings.UNCONFIRMED_DONATIONS]
        if donate
        else [settings.UNREAD_EVENTS]
    )
    for key in events:
        data = await redis.get(f"{key}-user-{user_id}")
        update_count = 1
        if data:
            update_count = json.loads(data)["count"] + 1
        await redis.set(
            f"{key}-user-{user_id}",
            json.dumps({"label": key, "count": update_count}),
        )
        await redis.publish(
            f"user-{user_id}",
            json.dumps({"label": key, "count": update_count}),
        )


def email_validate(email: str) -> None:
    """Валидация поля email."""
    if not re.match(settings.EMAIL_PATTERN, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid email"
        )
