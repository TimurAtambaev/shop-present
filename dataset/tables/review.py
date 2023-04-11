"""Таблица отзывов."""
import sqlalchemy as sa

from dataset.core.db import CREATED_AT_COLUMN, UPDATED_AT_COLUMN
from dataset.migrations import db


class Review(db.Model):
    """Модель отзывов."""

    __tablename__ = "review"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    name = sa.Column("name", sa.String(30), nullable=False)
    photo = sa.Column("photo", sa.String(2048), nullable=False)
    lang = sa.Column("lang", sa.String(8), nullable=False)
    text = sa.Column("text", sa.String(400), nullable=False)
    sort = sa.Column("sort", sa.Integer, default=500, nullable=False)
    is_active = sa.Column(
        "is_active", sa.Boolean, default=False, nullable=False
    )
    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
