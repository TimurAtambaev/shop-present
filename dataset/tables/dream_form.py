"""DreamForm model and related items."""
import sqlalchemy as sa

from dataset.core.db import CREATED_AT_COLUMN
from dataset.migrations import db


class DreamForm(db.Model):
    """Модель формы мечты."""

    __tablename__ = "dream_form"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    title = sa.Column("title", sa.String(64), nullable=False)
    description = sa.Column("description", sa.String(512), nullable=False)
    goal = sa.Column("goal", sa.Integer, nullable=False)
    email = sa.Column("email", sa.String(128), nullable=False)
    currency_id = sa.Column("currency_id", sa.ForeignKey("currency.id"))
    code = sa.Column("code", sa.String(256), nullable=False)

    created_at = CREATED_AT_COLUMN()
