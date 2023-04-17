"""Модель наборов жителей."""
import sqlalchemy as sa
from sqlalchemy import func
from dataset.tables import Base


class Kit(Base):
    """Модель наборов жителей."""

    __tablename__ = "kit"
    __table_args__ = (
        sa.UniqueConstraint("import_id", "citizen_id",
                            name="unique_import_citizen"),
        )

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    import_id = sa.Column("import_id", sa.String(128), nullable=False)
    citizen_id = sa.Column("citizen_id", sa.Integer, nullable=False)
    town = sa.Column("town", sa.String(256), nullable=False)
    street = sa.Column("street", sa.String(256), nullable=False)
    building = sa.Column("building", sa.String(256), nullable=False)
    apartment = sa.Column("apartment", sa.Integer, nullable=False)
    name = sa.Column("name", sa.String(256), nullable=False)
    birth_date = sa.Column("birth_date", sa.Date, nullable=False)
    gender = sa.Column("gender", sa.String(6), nullable=False)
    relatives = sa.Column("relatives", sa.ARRAY(sa.Integer),
                          nullable=False, default={})
    created_at = lambda: sa.Column(  # noqa E731
    "created_at", sa.TIMESTAMP, server_default=func.now()
)
    updated_at = UPDATED_AT_COLUMN = lambda: sa.Column(  # noqa E731
    "updated_at",
    sa.TIMESTAMP,
    server_default=func.now(),
    server_onupdate=func.now(),
    default=func.now(),
    onupdate=func.now(),
)
