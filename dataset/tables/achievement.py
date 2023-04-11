"""Achievement model and related items."""

from enum import Enum

import sqlalchemy as sa

from dataset.migrations import db

NAMES = {
    "ufandao_member": "Ufandao member",
    "ufandao_friend": "Ufandao friend",
    "ufandao_fundraiser": "Ufandao fundraiser",
    "top_fundraiser": "Top fundraiser",
    "dream_maker": "Dream maker",
}

DESCRIPTIONS = {
    "ufandao_member": "Моя мечта появляется в реестре желаний "
    "(регистрация и активация сертификата на мечту)",
    "ufandao_friend": "Мечта появляется в приоритетном порядке. Первыми "
    "показываются мечты тех, кто сделал 3 приглашения",
    "ufandao_fundraiser": "Моя мечта всегда на виду и выше в списке "
    "(5 приглашений)",
    "top_fundraiser": "Возможность получать дополнительные донаты "
    'на свои мечты. Мечта появляется в разделе "Популярное" '
    "(7 приглашений)",
    "dream_maker": "Увеличение лимита сбора средств на мечту "
    "в три раза (10 приглашений)",
}


class AchievementType(Enum):
    """Achievement type enum."""

    UFANDAO_MEMBER = "ufandao_member"
    UFANDAO_FRIEND = "ufandao_friend"
    UFANDAO_FUNDRAISER = "ufandao_fundraiser"
    TOP_FUNDRAISER = "top_fundraiser"
    DREAM_MAKER = "dream_maker"


class AchievementRefNum(Enum):
    """Enum кол-ва пользователей для получения достижения."""

    ufandao_friend = 3
    ufandao_fundraiser = 5
    top_fundraiser = 7
    dream_maker = 10


class Achievement(db.Model):
    """Achievement model."""

    __tablename__ = "achievement"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id = sa.Column(
        "user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False
    )
    title = sa.Column(
        "title", sa.String(64), nullable=True, default="Заголовок"
    )
    description = sa.Column(
        "description", sa.String(256), nullable=True, default="Описание"
    )
    type_name = sa.Column("type_name", sa.String(64), nullable=False)
    received_at = sa.Column("received_at", sa.TIMESTAMP, nullable=True)
