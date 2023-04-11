"""Donation model and related items."""
from __future__ import annotations

from enum import Enum
from typing import Any

import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import METADATA, db
from dataset.tables.dream import Dream


class DonationLevel(Enum):
    """Donation levels enum."""

    REFERAL = 1
    GOLD = 2
    SILVER = 3
    BRONZE = 4


class DonationStatus(Enum):
    """Valid donation status enum."""

    NEW = 10
    WAITING_FOR_CONFIRMATION = 20
    CONFIRMED = 30
    AUTO_CONFIRMED = 40
    FAILED = 99


class Donation(db.Model):
    """Модель доната."""

    __tablename__ = "donation"
    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    dream_id = sa.Column(
        "dream_id", sa.Integer, sa.ForeignKey("dream.id"), nullable=True
    )
    receipt = sa.Column("receipt", sa.String(256), nullable=True)
    recipient_id = sa.Column(
        "recipient_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False
    )
    sender_id = sa.Column(
        "sender_id", sa.Integer, sa.ForeignKey("user.id"), nullable=True
    )
    level_number = sa.Column("level_number", sa.Integer, nullable=True)
    is_primary = sa.Column("is_primary", sa.Boolean())
    amount = sa.Column("amount", sa.Integer, nullable=True)
    status = sa.Column("status", sa.SmallInteger(), nullable=False)
    comment = sa.Column("comment", sa.String(2048))
    expires_at = sa.Column("expires_at", sa.TIMESTAMP)
    paid_at = sa.Column("paid_at", sa.TIMESTAMP)
    confirmed_at = sa.Column("confirmed_at", sa.TIMESTAMP)
    donation_type = sa.Column("donation_type", sa.Boolean())
    sub_at = sa.Column("sub_at", sa.TIMESTAMP)
    currency_id = sa.Column("currency_id", sa.ForeignKey("currency.id"))
    first_currency_id = sa.Column("first_currency_id", sa.Integer)
    first_amount = sa.Column("first_amount", sa.Integer, nullable=True)

    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()

    @classmethod
    async def create(cls, *args: Any, **kwargs: Any) -> Donation:
        """Добавлен подсчет донатов в метод сохранения."""
        donation = await super().create(*args, **kwargs)
        await cls._update_dream_donation_cnt(kwargs[Donation.dream_id.key])
        return donation  # noqa R504

    async def update_w_cnt(self, **kwargs: Any) -> Donation:
        """Добавлен подсчет донатов в метод обновления."""
        donation = await self.update(**kwargs).apply()
        if kwargs.get("status") == DonationStatus.CONFIRMED.value:
            await self._update_dream_donation_cnt(self.dream_id)

        return donation  # noqa R504

    @classmethod
    async def _update_dream_donation_cnt(
        cls, dream_id: int, update: bool = False
    ) -> None:
        """Подсчет кол-ва задонативших на мечту."""
        donations_num = await (
            db.select([db.func.count()])
            .where(
                sa.and_(
                    Donation.dream_id == dream_id,
                    Donation.confirmed_at != None,  # noqa E711
                )
            )
            .gino.scalar()
        )
        await (
            Dream.update.values(donations_count=donations_num)
            .where(Dream.id == dream_id)
            .gino.status()
        )


donation_purpose = sa.Table(
    "donation_purpose",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("is_active", sa.Boolean(), default=False),
    CREATED_BY_OPERATOR_COLUMN(),
    UPDATED_BY_OPERATOR_COLUMN(),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
)

donation_purpose_language = sa.Table(
    "donation_purpose_language",
    METADATA,
    sa.Column(
        "donation_purpose_id", sa.Integer, sa.ForeignKey("donation_purpose.id")
    ),
    sa.Column("language", sa.String(64)),
    sa.Column("title", sa.String(64)),
    CREATED_BY_OPERATOR_COLUMN(),
    UPDATED_BY_OPERATOR_COLUMN(),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
    sa.PrimaryKeyConstraint("donation_purpose_id", "language"),
)
