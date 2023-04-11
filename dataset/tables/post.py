"""Post models and related items."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import db


class Post(db.Model):
    """Модель новостей."""

    __tablename__ = "post"

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    title = sa.Column("title", sa.String(128), nullable=False)
    cover_url = sa.Column("cover_url", sa.String(256), nullable=True)
    language = sa.Column("language", sa.String(2))
    markup_text = sa.Column("markup_text", sa.String(4096), nullable=False)
    is_published = sa.Column(
        "is_published", sa.Boolean, default=False, nullable=False
    )
    text = sa.Column("text", sa.String(4096), nullable=False)
    tags = sa.Column("tags", pg.ARRAY(sa.Text))
    published_date = sa.Column("published_date", sa.DATE)
    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()


post = Post()
