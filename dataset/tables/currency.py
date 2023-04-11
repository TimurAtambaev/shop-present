"""Currency model and related items."""
import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import db
from dataset.tables.donate_size import DonateSize


class Currency(db.Model):
    """Модель валюты."""

    __tablename__ = "currency"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    code = sa.Column("code", sa.String(10), nullable=False)
    symbol = sa.Column("symbol", sa.String(5), nullable=False)
    name = sa.Column("name", sa.String(200), nullable=False)
    course = sa.Column("course", sa.Integer, nullable=False)
    sort_number = sa.Column("sort_number", sa.Integer, nullable=False)
    is_active = sa.Column("is_active", sa.Boolean(), nullable=False)
    dream_limit = sa.Column("dream_limit", sa.Integer, nullable=False)

    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()

    def __init__(self, **kw: dict) -> None:
        """Метод для добавления поля donate_sizes."""
        super().__init__(**kw)
        self._donate_sizes = list()  # noqa C408

    @property
    def donate_sizes(self) -> list:
        """Метод возвращения размера валюты."""
        return self._donate_sizes

    @donate_sizes.setter
    def add_donate_size(self, donate_size: DonateSize) -> None:
        """Метод добавления размера валюты."""
        self._donate_sizes.append(donate_size)
