"""Модели таблиц импортов, жителей, родственных связей."""
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Imports(Base):
    """Модель идентификаторов импортов наборов жителей."""

    __tablename__ = "imports"
    import_id = sa.Column("import_id", sa.Integer, primary_key=True)


class Citizens(Base):
    """Модель информации о жителе."""

    __tablename__ = "citizens"

    import_id = sa.Column("import_id", sa.Integer,
                          sa.ForeignKey("imports.import_id"),
                          primary_key=True)
    citizen_id = sa.Column("citizen_id", sa.Integer, primary_key=True)
    town = sa.Column("town", sa.String(256), nullable=False, index=True)
    street = sa.Column("street", sa.String(256), nullable=False)
    building = sa.Column("building", sa.String(256), nullable=False)
    apartment = sa.Column("apartment", sa.Integer, nullable=False)
    name = sa.Column("name", sa.String(256), nullable=False)
    birth_date = sa.Column("birth_date", sa.Date, nullable=False)
    gender = sa.Column("gender", sa.String(6), nullable=False)
    created_at = sa.Column(  # noqa E731
    "created_at",
    sa.TIMESTAMP,
    server_default=sa.func.now()
)
    updated_at = sa.Column(  # noqa E731
    "updated_at",
    sa.TIMESTAMP,
    server_default=sa.func.now(),
    server_onupdate=sa.func.now(),
    default=sa.func.now(),
    onupdate=sa.func.now(),
)


class Relations(Base):
    """Модель родственных связей жителей."""

    __tablename__ = "relations"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ('import_id', 'citizen_id'),
            ('citizens.import_id', 'citizens.citizen_id')
        ),
        sa.ForeignKeyConstraint(
            ('import_id', 'relative_id'),
            ('citizens.import_id', 'citizens.citizen_id')
        ),
        )
    import_id = sa.Column("import_id", sa.Integer, primary_key=True)
    citizen_id = sa.Column("citizen_id", sa.Integer, primary_key=True)
    relative_id = sa.Column("relative_id", sa.Integer, primary_key=True)
