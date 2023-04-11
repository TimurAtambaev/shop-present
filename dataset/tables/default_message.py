"""Default message model and related items."""
import sqlalchemy as sa

from dataset.migrations import db


class StandartMessage(db.Model):
    """Модель сообщений."""

    __tablename__ = "standart_message"

    id = sa.Column(  # noqa A002
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    text = sa.Column("text", sa.String(256), nullable=False)
    type_message = sa.Column(
        "type_message",
        sa.String(50),
        default="standart_message",
        nullable=False,
    )
