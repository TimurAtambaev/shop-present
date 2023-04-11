"""Chat message model and related items."""
import sqlalchemy as sa

from dataset.core.db import CREATED_AT_COLUMN
from dataset.migrations import db


class Message(db.Model):
    """Модель сообщений."""

    __tablename__ = "message"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    author_id = sa.Column(
        "author_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False
    )
    users_ids = sa.Column("users_ids", sa.ARRAY(sa.Integer), nullable=False)
    text = sa.Column("text", sa.String(512), nullable=True)
    is_read = sa.Column("is_read", sa.Boolean(), default=False, nullable=False)
    type_message = sa.Column(
        "type_message", sa.String(12), default="text", nullable=False
    )

    created_at = CREATED_AT_COLUMN()
