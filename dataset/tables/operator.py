"""Operator model and related items.

table, graphql_: objects, queries, mutations.
"""

import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import db


class Operator(db.Model):
    """Operator model."""

    __tablename__ = "operator"
    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    name = sa.Column("name", sa.String(128))
    email = sa.Column("email", sa.String(128), unique=True)
    password = sa.Column("password", sa.String(128), nullable=False)
    is_superuser = sa.Column("is_superuser", sa.Boolean)
    is_active = sa.Column(
        "is_active", sa.Boolean, default=True, nullable=False
    )
    is_content_manager = sa.Column(
        "is_content_manager", sa.Boolean, default=False, nullable=False
    )
    imrix_id = sa.Column("imrix_id", sa.Integer, unique=True, nullable=True)
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()
    updated_by_operator_id = UPDATED_BY_OPERATOR_COLUMN()
    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
