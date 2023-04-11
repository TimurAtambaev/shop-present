"""Модель с настройками для редактирования в админке."""
import sqlalchemy as sa

from dataset.migrations import db


class AdminSettings(db.Model):
    """Модель настроек для админа."""

    __tablename__ = "admin_settings"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    dream_limit = sa.Column(
        "dream_limit", sa.Integer, default=5000, nullable=False
    )
    exchange_rate = sa.Column("exchange_rate", sa.Float, nullable=True)
