"""Event model and related items."""
from enum import Enum

import sqlalchemy as sa

from dataset.core.db import CREATED_AT_COLUMN
from dataset.migrations import db


class TypeEvent(Enum):
    """Типы уведомлений."""

    MAKER = "dream_maker"
    EXECUTE = "execute_dream"
    MESSAGE = "message"
    DONATE = "donate"
    CONFIRM_DONATE = "confirm_donate"
    PARTICIPANT = "new_participant"
    FRIEND = "new_friend"


class Event(db.Model):
    """Модель событий."""

    __tablename__ = "event"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id = sa.Column(
        "user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False
    )
    sender_id = sa.Column(
        "sender_id", sa.Integer, sa.ForeignKey("user.id"), nullable=True
    )
    dream_id = sa.Column(
        "dream_id", sa.Integer, sa.ForeignKey("dream.id"), nullable=True
    )
    donation_id = sa.Column(
        "donation_id", sa.Integer, sa.ForeignKey("donation.id"), nullable=True
    )
    data = sa.Column("data", sa.JSON(), nullable=True)
    is_read = sa.Column("is_read", sa.Boolean(), default=False, nullable=False)
    type_event = sa.Column("type_event", sa.String(50), nullable=False)

    created_at = CREATED_AT_COLUMN()
