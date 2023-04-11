"""Модуль Pydantic моделей уведомлений."""
from typing import Optional

from pydantic import BaseModel

from dataset.rest.models.utils import as_form


@as_form
class NotificationSendModel(BaseModel):
    """Тип отправки уведомлений."""

    email: Optional[bool]


class NotificationsResponseModel(BaseModel):
    """Pydantic модель ответа уведомлений."""

    new_chat_message: NotificationSendModel


class SendNotificationsModel(BaseModel):
    """Pydantic модель для обработки запроса с сокетов."""

    recipient_id: int
    notification_type: str
