"""Order model and related items.

table, graphql_: objects, queries, mutations.
"""
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY as pgArray  # noqa N811

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_USER_COLUMN,
)
from dataset.migrations import METADATA


class OrderStatus(Enum):
    """Order possible status enum."""

    NEW = 10
    IN_PROCESS = 20
    COMPLETE = 30
    AUTO_COMPLETE = 40
    FAILED = 50


order = sa.Table(
    "order",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("user_id", sa.Integer, nullable=False),
    sa.Column("user_version", sa.Integer, nullable=False),
    sa.Column(
        "application_id", sa.ForeignKey("application.id"), nullable=False
    ),
    sa.Column("product_id", sa.String(64), nullable=False, unique=True),
    sa.Column("status", sa.SmallInteger(), nullable=False),
    sa.Column("available_certificates", pgArray(sa.String(64)), nullable=True),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
    CREATED_BY_OPERATOR_COLUMN(),
    UPDATED_BY_USER_COLUMN(),
    sa.ForeignKeyConstraint(
        (
            "user_id",
            "user_version",
        ),
        ("user_history.user_id", "user_history.version"),
        ondelete="RESTRICT",
    ),
)
