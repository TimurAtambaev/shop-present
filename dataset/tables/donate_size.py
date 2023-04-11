"""Currency model and related items."""
import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import db


class DonateSize(db.Model):
    """Модель уровней и размеров донатов по валютам."""

    __tablename__ = "donate_size"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    currency_id = sa.Column(
        "currency_id", sa.ForeignKey("currency.id"), nullable=False
    )
    level = sa.Column("level", sa.Integer, nullable=False)
    size = sa.Column("size", sa.Integer, nullable=False)

    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()
