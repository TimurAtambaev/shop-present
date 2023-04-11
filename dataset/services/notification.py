"""Сервисы по уведомлениям."""
import asyncio
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from gino import GinoException
from starlette import status

from dataset.core.mail.utils import send_mail
from dataset.mail_templates import NewMessageChatNotification
from dataset.migrations import db
from dataset.tables.notification import Notification, NotificationType
from dataset.tables.user import User


class NewChatMessageEmailAction:
    """Класс отправки уведомления о новом сообщении по email."""

    def __init__(self, user: User, app: FastAPI) -> None:
        """Конструктор класса."""
        self.user = user
        self.app = app

    async def send(self) -> None:
        """Отправить уведомление по email."""
        asyncio.create_task(
            send_mail(
                self.user.verified_email,
                NewMessageChatNotification(
                    self.app,
                    email=self.user.verified_email,
                    name=self.user.name,
                    language=self.user.language,
                ),
                self.user.language,
            )
        )


class NotificationsUserService:
    """Сервисный класс уведомлений."""

    def __init__(self, app: FastAPI) -> None:
        """Конструктор класса."""
        self.app = app

    actions = {"new_chat_message-email": NewChatMessageEmailAction}

    async def send_notification(
        self, user_id: int, notification_type: str
    ) -> None:
        """Отправить уведомления получателю."""
        user = await User.query.where(User.id == user_id).gino.first()
        notifications = await self.get_notifications(user_id)
        for send_type, is_active in notifications[notification_type].items():
            if not is_active:
                continue
            notification = f"{notification_type}-{send_type}"
            action = self.actions[notification](user, self.app)
            await action.send()

    def _get_user_notifications_status(
        self, user_notifications: list[Notification]
    ) -> dict:
        """Получить словарь со статусом активности подписок юзера."""
        notify_status = {}
        for notification in user_notifications:
            notify_status[
                notification.notification_type
            ] = notification.is_active
        return notify_status

    def _get_user_notifications_config(self, status_dict: dict) -> dict:
        """Получить список список уведомлений юзера для ответа."""
        notifications_config = defaultdict(dict)
        for item in NotificationType:
            notify_type, send_type = item.value.split("-")
            notifications_config[notify_type].update(
                {send_type: status_dict.get(item.value, False)}
            )
        return notifications_config

    async def _get_user_notifications(self, user_id: int) -> list:
        """Получить список объектов Notification."""
        query = Notification.query.where(Notification.user_id == user_id)
        return await query.gino.all()

    async def get_notifications(self, user_id: int) -> dict:
        """Получить подписки на уведомления по юзеру."""
        user_notifications = await self._get_user_notifications(user_id)
        status_dict = self._get_user_notifications_status(user_notifications)
        return self._get_user_notifications_config(status_dict)

    def _parse_form_data(self, data: dict, user_id: int) -> list[tuple]:
        """Спарсить dict в list of tuples.

        Список кортежей требуется сформировать для INSERT/UPDATE запроса в БД.
        """
        parsed_form_data = []
        for notification_key, dict_value in data.items():
            for send_type, is_active in dict_value.items():
                notification_type = f"{notification_key}-{send_type}"
                parsed_form_data.append(
                    (user_id, notification_type, is_active)
                )
        return parsed_form_data

    async def _commit_notifications(self, values: str) -> None:
        """Сделать запрос в БД.

        Если у пользователя уже подписан на обновление -> обновить статус.
        """
        # TODO позже надо перенести на алхимию
        try:
            await db.status(
                db.text(
                    f"""
                INSERT INTO notifications (user_id, notification_type, is_active)
                     VALUES {values}
                ON CONFLICT ON CONSTRAINT user_id_notification_type_unique
                DO   UPDATE
                        SET is_active = EXCLUDED.is_active
                """
                )
            )
        except GinoException:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(GinoException),
            )

    async def update_notifications(self, data: dict, user_id: int) -> None:
        """Обновить подписки на обновления по юзеру."""
        parsed_form_data = self._parse_form_data(data, user_id)
        values = str(parsed_form_data).strip("[]")
        await self._commit_notifications(values)
