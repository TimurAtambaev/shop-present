"""Dream model and related items."""
from enum import Enum

import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import db
from dataset.tables.payment_data import BasePaymentData


class DreamStatus(Enum):
    """dream possible status enum."""

    DRAFT = 10
    QUART = 20
    HALF = 30
    THREE_QUARTERS = 40
    WHOLE = 50
    ACTIVE = 60
    CLOSED = 70


class DreamType(Enum):
    """Список типов мечт."""

    USER = "Пользовательская"
    CHARITY = "Благотворительная"


class Dream(db.Model):
    """Модель мечт."""

    __tablename__ = "dream"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id = sa.Column(
        "user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False
    )
    status = sa.Column("status", sa.SmallInteger(), nullable=False)
    title = sa.Column("title", sa.String(64), nullable=True)
    description = sa.Column("description", sa.String(10000), nullable=True)
    collected = sa.Column("collected", sa.Integer, nullable=True)
    goal = sa.Column("goal", sa.Integer, nullable=True)
    picture = sa.Column("picture", sa.String(256), nullable=True)
    category_id = sa.Column(
        "category_id",
        sa.SmallInteger(),
        sa.ForeignKey("category.id"),
        nullable=True,
    )
    ref_donations = sa.Column(
        "ref_donations", sa.ARRAY(sa.Integer), nullable=False, default={}
    )
    type_dream = sa.Column(
        "type_dream", sa.String(64), default="Пользовательская", nullable=False
    )
    currency_id = sa.Column("currency_id", sa.ForeignKey("currency.id"))

    created_at = CREATED_AT_COLUMN()
    closed_at = sa.Column("closed_at", sa.TIMESTAMP, nullable=True)
    updated_at = UPDATED_AT_COLUMN()
    donations_count = sa.Column("donations_count", sa.Integer, default=0)
    language = sa.Column("language", sa.String(10))

    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()

    def __init__(self, **kw: dict) -> None:
        """Метод для добавления поля payments."""
        super().__init__(**kw)
        self._payments = set()

    @property
    def payments(self) -> set:
        """Метод возвращения реквизитов."""
        return self._payments

    @payments.setter
    def add_payment(self, payment: BasePaymentData) -> None:
        """Метод добавления реквизита."""
        self._payments.add(payment)


class Category(db.Model):
    """Модель категорий."""

    __tablename__ = "category"
    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    title_cat = sa.Column("title_cat", sa.String(128), nullable=False)
    image = sa.Column("image", sa.ARRAY(sa.Text), nullable=False)
