"""Модуль с табличек уведомлений."""
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint

from dataset.migrations import db


class NotificationType(str, Enum):
    """Enum с типами уведомлений."""

    NEW_CHAT_MESSAGE_EMAIL = "new_chat_message-email"


class Notification(db.Model):
    """Модель Уведомлений."""

    __tablename__ = "notifications"

    user_id = sa.Column(
        "user_id",
        sa.Integer,
        sa.ForeignKey("user.id"),
        nullable=False,
        primary_key=True,
    )

    notification_type = sa.Column(
        "notification_type", sa.String(64), primary_key=True
    )
    is_active = sa.Column("is_active", sa.Boolean(), default=False)
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "notification_type",
            name="user_id_notification_type_unique",
        ),
    )
