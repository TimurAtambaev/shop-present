"""Сервис для управления подписками."""
from datetime import date, datetime, timedelta

import requests
from aioredis import Redis
from fastapi import FastAPI
from loguru import logger

from dataset.config import settings
from dataset.tables.user import User
from dataset.utils.hooks import create_user_refer_code, update_dream_status


class SubscriptionService:
    """Сервис для управления подписками."""

    def __init__(self, app: FastAPI, redis: Redis) -> None:
        """Инициализация класса."""
        self.app = app
        self.redis = redis

    async def change_subscribe_till(
        self, token: str, user: User, subscribe_till: datetime
    ) -> bool:
        """Измененить срок окончания подписки пользователя."""
        if user.imrix_id and not await self.change_imrix_subscribe(
            token, user.imrix_id, subscribe_till
        ):
            return False
        await user.update(paid_till=subscribe_till).apply()
        if subscribe_till.date() >= date.today():
            await update_dream_status(self.redis, user)
            await create_user_refer_code(self.app, user)
        return True

    async def change_imrix_subscribe(
        self, token: str, imrix_id: int, subscribe_till: datetime
    ) -> bool:
        """Отправить запрос на изменение подписки в Имриксе."""
        # прибавляем 1 день чтобы подписка в Имриксе была до конца текущей даты как и в Юфандао
        target_subscribed_till = subscribe_till + timedelta(days=1)
        try:
            response = requests.post(
                f"{settings.IMRIX_HOST}/api/rest/1.0/admin/change-subscribe",
                json={
                    "user_id": imrix_id,
                    "subscribe_till": str(target_subscribed_till),
                },
                headers={"Authorization": token},
            )
        except Exception as exc:
            logger.error(exc)
            return False
        return bool(response.ok)
