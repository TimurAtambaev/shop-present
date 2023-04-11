"""User model and related items."""
from enum import Enum

import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import METADATA, db


class AchievementCode(Enum):
    """User achievement code list enum."""

    CERTIFICATE_ACTIVATION = "certificate_activation"
    UFANDAO_FRIEND = "ufandao_friend"
    SHARING_FRIEND = "sharing_friend"
    SHARING_MASTER = "sharing_master"
    SHARING_EXPERT = "sharing_expert"
    SHARING_PRO = "sharing_pro"


# TODO переделать все запросы с пользователем на новый формат
class User(db.Model):
    """Модель пользователя."""

    __tablename__ = "user"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    imrix_id = sa.Column("imrix_id", sa.Integer, unique=True, nullable=True)
    name = sa.Column("name", sa.String(64))
    surname = sa.Column("surname", sa.String(64))
    email = sa.Column("email", sa.String(128))
    verified_email = sa.Column("verified_email", sa.String(128), nullable=True)
    phone = sa.Column("phone", sa.String(64))
    password = sa.Column("password", sa.String(128))
    reset_token = sa.Column("reset_token", sa.String(256), nullable=True)
    reset_token_valid_till = sa.Column(
        "reset_token_valid_till", sa.TIMESTAMP, nullable=True
    )
    birth_date = sa.Column("birth_date", sa.Date)
    country_id = sa.Column("country_id", sa.ForeignKey("country.id"))
    is_female = sa.Column("is_female", sa.Boolean(), nullable=True)
    is_active = sa.Column(
        "is_active", sa.Boolean(), default=True, nullable=False
    )
    language = sa.Column(
        "language", sa.String(2), default="en", nullable=False
    )
    avatar = sa.Column("avatar", sa.String(2048), nullable=True)
    fb_id = sa.Column("fb_id", sa.BigInteger, nullable=True)
    refer_code = sa.Column(
        "refer_code", sa.String(18), unique=True, nullable=True
    )
    referer = sa.Column(
        "referer",
        sa.String(18),
        sa.ForeignKey("user.refer_code"),
        nullable=True,
    )
    paid_till = sa.Column("paid_till", sa.Date, nullable=True)
    trial_till = sa.Column("trial_till", sa.TIMESTAMP, nullable=True)
    refer_count = sa.Column("refer_count", sa.Integer, default=0)
    is_superuser = sa.Column(
        "is_superuser", sa.Boolean(), default=False, nullable=True
    )
    is_vip = sa.Column("is_vip", sa.Boolean(), default=False, nullable=True)
    currency_id = sa.Column("currency_id", sa.ForeignKey("currency.id"))
    telegram = sa.Column("telegram", sa.String(64), nullable=True)

    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()


user_history = sa.Table(
    "user_history",
    METADATA,
    sa.Column("user_id", sa.ForeignKey("user.id"), nullable=False),
    sa.Column("version", sa.Integer, index=True, nullable=False),
    sa.Column("name", sa.String(64)),
    sa.Column("email", sa.String(128)),
    sa.Column("is_female", sa.Boolean(), nullable=True),
    sa.Column("birth_date", sa.Date),
    sa.Column("country_id", sa.ForeignKey("country.id")),
    sa.Column("avatar", sa.String(256), nullable=True),
    CREATED_BY_OPERATOR_COLUMN(),
    UPDATED_BY_OPERATOR_COLUMN(),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
    sa.PrimaryKeyConstraint("user_id", "version"),
)

blacklist = sa.Table(
    "blacklist",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("jti", sa.String(32), nullable=False),
)
