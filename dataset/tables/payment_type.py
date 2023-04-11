"""PaymentType model and related items.

Table, graphql_: objects, queries, mutations.
"""
import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import METADATA

# TODO не нужно
payment_type = sa.Table(
    "payment_type",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("title", sa.String(64), nullable=False),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
    CREATED_BY_OPERATOR_COLUMN(),
    UPDATED_BY_OPERATOR_COLUMN(),
)
