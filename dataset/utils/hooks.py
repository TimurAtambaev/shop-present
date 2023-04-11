"""Модуль с хуками проекта."""
import asyncio

import shortuuid
from aioredis import Redis
from fastapi import FastAPI
from sqlalchemy import and_

from dataset.core.mail.utils import send_mail
from dataset.mail_templates import SendReferLinkTemplate
from dataset.rest.views.utils import assign_received_at, recount_refs
from dataset.tables.achievement import AchievementType
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.user import User


async def create_user_refer_code(app: FastAPI, user: User) -> None:
    """Функция для создания реферального токена у юзера."""
    if user.refer_code:
        return
    await user.update(
        refer_code=str(shortuuid.ShortUUID().random(length=18))
    ).apply()
    asyncio.create_task(
        send_mail(
            user.verified_email,
            SendReferLinkTemplate(
                app,
                refer_code=user.refer_code,
                name=user.name,
                email=user.verified_email,
            ),
            user.language,
        )
    )


async def update_dream_status(redis: Redis, user: User) -> None:
    """Функция для обновления статуса мечты."""
    is_active_dream = await Dream.query.where(
        and_(
            Dream.user_id == user.id,
            Dream.status == DreamStatus.ACTIVE.value,
        )
    ).gino.first()
    if is_active_dream:
        return
    whole_dream = await Dream.query.where(
        and_(
            Dream.user_id == user.id,
            Dream.status == DreamStatus.WHOLE.value,
        )
    ).gino.first()
    if not whole_dream:
        return
    await whole_dream.update(status=DreamStatus.ACTIVE.value).apply()
    await assign_received_at(user.id, AchievementType.UFANDAO_MEMBER.value)
    if user.referer and not user.refer_code:
        await recount_refs(redis, user.referer)
