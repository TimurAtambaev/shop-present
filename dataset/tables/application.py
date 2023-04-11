"""Application model and related items.

Table, graphql_: objects, queries, mutations
"""

import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
    UPDATED_BY_OPERATOR_COLUMN,
)
from dataset.migrations import METADATA

CLIENT_ID_LENGTH = 48
CLIENT_SECRET_LENGTH = 96
get_app_fk = lambda: sa.ForeignKey("application.id")  # noqa E731

application = sa.Table(
    "application",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("name", sa.String(64), unique=True),
    sa.Column("description", sa.String(512)),
    sa.Column("color", sa.String(16)),
    sa.Column("logo", sa.String(256)),
    sa.Column("parent_key_name", sa.String(64)),
    sa.Column("key_name", sa.String(64)),
    sa.Column("is_active", sa.Boolean()),
    sa.Column(
        "oauth2_client_identifier",
        sa.String(256),
        unique=True,
        nullable=False,
        server_default="",
    ),
    sa.Column(
        "oauth2_client_secret",
        sa.String(256),
        nullable=False,
        server_default="",
    ),
    sa.Column(
        "redirect_uri", sa.String(512), nullable=False, server_default=""
    ),
    sa.Column("integration_url", sa.String(512), nullable=False),
    sa.Column("integration_token", sa.String(512), nullable=False),
    CREATED_BY_OPERATOR_COLUMN(),
    UPDATED_BY_OPERATOR_COLUMN(),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
)
referent_level = sa.Table(
    "referent_level",
    METADATA,
    sa.Column("name", sa.String(64)),
    sa.Column("number", sa.Integer(), primary_key=True, index=True),
    sa.Column("amount", sa.DECIMAL()),
    sa.Column("is_primary", sa.Boolean(), nullable=False, default=False),
    sa.Column("application_id", get_app_fk(), primary_key=True, index=True),
)

oauth2_authorization_code = sa.Table(
    "oauth2_authorization_code",
    METADATA,
    sa.Column(
        "user_id",
        sa.Integer,
        sa.ForeignKey("user.id"),
        nullable=False,
        primary_key=True,
    ),
    sa.Column(
        "application_id",
        sa.Integer,
        get_app_fk(),
        nullable=False,
        primary_key=True,
    ),
    sa.Column("code", sa.String(256), unique=True, nullable=False),
    sa.Column("is_used", sa.Boolean(), nullable=False, server_default="false"),
    sa.Column("expires_at", sa.TIMESTAMP, nullable=False),
)

oauth2_token = sa.Table(
    "oauth2_token",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("user.id"), nullable=False),
    sa.Column("application_id", sa.Integer, get_app_fk(), nullable=False),
    sa.Column("token", sa.String(256), unique=True, nullable=False),
    sa.Column(
        "is_revoked", sa.Boolean(), nullable=False, server_default="false"
    ),
    sa.Column("issued_at", sa.TIMESTAMP, nullable=False),
    sa.Column("expires_at", sa.TIMESTAMP, nullable=False),
)
