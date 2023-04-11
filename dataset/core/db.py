"""Module for db handlers, helpers and other classes and functions."""
import sqlalchemy as sa
from sqlalchemy import func

CREATED_AT_COLUMN = lambda: sa.Column(  # noqa E731
    "created_at", sa.TIMESTAMP, server_default=func.now()
)

UPDATED_AT_COLUMN = lambda: sa.Column(  # noqa E731
    "updated_at",
    sa.TIMESTAMP,
    server_default=func.now(),
    server_onupdate=func.now(),
    default=func.now(),
    onupdate=func.now(),
)

get_operator_fk = lambda: sa.ForeignKey("operator.id")  # noqa E731
get_user_fk = lambda: sa.ForeignKey("user.id")  # noqa E731
# WARNING COLUMNS WITH "AS" IN NAMES DONT USE SUFFIX "by_operator" or "by_user"
CREATED_BY_COLUMN_AS_OPERATOR = lambda n=None: sa.Column(  # noqa E731
    "created_by_id", sa.Integer, get_operator_fk(), nullable=True, name=n
)

CREATED_BY_COLUMN_AS_USER = lambda n=None: sa.Column(  # noqa E731
    "created_by_id", sa.Integer, get_user_fk(), nullable=True, name=n
)

UPDATED_BY_COLUMN_AS_USER = lambda n=None: sa.Column(  # noqa E731
    "updated_by_id", sa.Integer, get_user_fk(), nullable=True, name=n
)

# WARNING IF YOU NEED created_by_id COLUMN REFERING TO OPERATOR SEE COLUMNS
# ABOVE WITH "AT" IN NAME
CREATED_BY_OPERATOR_COLUMN = lambda n=None: sa.Column(  # noqa E731
    "created_by_operator_id",
    sa.Integer,
    get_operator_fk(),
    nullable=True,
    name=n,
)

# WARNING IF YOU NEED created_by_id COLUMN REFERING TO USER SEE COLUMNS
# ABOVE WITH "AT" IN NAME
CREATED_BY_USER_COLUMN = lambda n=None: sa.Column(  # noqa E731
    "created_by_user_id", sa.Integer, get_user_fk(), nullable=True, name=n
)

UPDATED_BY_OPERATOR_COLUMN = lambda n=None: sa.Column(  # noqa E731
    "updated_by_operator_id",
    sa.Integer,
    get_operator_fk(),
    nullable=True,
    name=n,
)

UPDATED_BY_USER_COLUMN = lambda n=None: sa.Column(  # noqa E731
    "updated_by_user_id", sa.Integer, get_user_fk(), nullable=True, name=n
)
