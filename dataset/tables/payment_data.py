"""PaymentData model and related items."""
from enum import Enum

import sqlalchemy as sa

from dataset.core.db import (
    CREATED_AT_COLUMN,
    CREATED_BY_OPERATOR_COLUMN,
    UPDATED_AT_COLUMN,
)
from dataset.migrations import METADATA, db


class PaymentType(Enum):
    """Payment enum types."""

    BANK = 10
    E_PAY = 20
    MOBILE = 30
    CUSTOM = 40
    PAYPAL = 50
    CRYPTO = 60


class BasePaymentData(db.Model):
    """Base payment data class."""

    __tablename__ = "general_payment_data"
    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column("type", sa.SmallInteger, nullable=False)  # noqa A003
    recipient = sa.Column("recipient", sa.String(64), nullable=True)
    card_number = sa.Column("card_number", sa.String(64), nullable=True)
    bank = sa.Column("bank", sa.String(64), nullable=True)
    country_id = sa.Column("country_id", sa.Integer)
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    account_num = sa.Column("account_num", sa.String(64), nullable=True)
    comment = sa.Column("comment", sa.String(126), nullable=True)
    phone_num = sa.Column("phone_num", sa.String(12), nullable=True)
    is_preference = sa.Column("is_preference", sa.Boolean, nullable=True)
    wallet_id = sa.Column("wallet_id", sa.Integer, nullable=True)
    wallet_data = sa.Column("wallet_data", sa.String(512), nullable=True)
    token = sa.Column("token", sa.String(256), nullable=True)
    network = sa.Column("network", sa.String(256), nullable=True)
    address = sa.Column("address", sa.String(256), nullable=True)

    created_at = CREATED_AT_COLUMN()
    updated_at = UPDATED_AT_COLUMN()
    created_by_operator_id = CREATED_BY_OPERATOR_COLUMN()


class BankPaymentData(db.Model):
    """Requisites for bank payment."""

    __tablename__ = "general_payment_data"
    __table_args__ = {"extend_existing": True}

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column(  # noqa A003
        "type", sa.SmallInteger, default=PaymentType.BANK.value
    )
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    recipient = sa.Column("recipient", sa.String(64))
    card_number = sa.Column("card_number", sa.String(64))
    bank = sa.Column("bank", sa.String(64))
    country_id = sa.Column("country_id", sa.Integer)
    comment = sa.Column("comment", sa.String(126), nullable=True)


class EPaymentData(db.Model):
    """Requisites for electronic payment."""

    __tablename__ = "general_payment_data"
    __table_args__ = {"extend_existing": True}

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column(  # noqa A003
        "type", sa.SmallInteger, default=PaymentType.E_PAY.value
    )
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    wallet_id = sa.Column("wallet_id", sa.Integer, nullable=True)
    wallet_data = sa.Column("wallet_data", sa.String(512), nullable=True)
    comment = sa.Column("comment", sa.String(126), nullable=True)


class MobilePaymentData(db.Model):
    """Requisites for mobile payment."""

    __tablename__ = "general_payment_data"
    __table_args__ = {"extend_existing": True}

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column(  # noqa A003
        "type", sa.SmallInteger, default=PaymentType.MOBILE.value
    )
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    recipient = sa.Column("recipient", sa.String(64))
    phone_num = sa.Column("phone_num", sa.String(12))
    comment = sa.Column("comment", sa.String(126), nullable=True)


class CustomPaymentData(db.Model):
    """Requisites for custom payment method."""

    __tablename__ = "general_payment_data"
    __table_args__ = {"extend_existing": True}

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column(  # noqa A003
        "type", sa.SmallInteger, default=PaymentType.CUSTOM.value
    )
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    recipient = sa.Column("recipient", sa.String(64))
    comment = sa.Column("comment", sa.String(126))


class PayPalPaymentData(db.Model):
    """Requisites for custom payment method."""

    __tablename__ = "general_payment_data"
    __table_args__ = {"extend_existing": True}

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column(  # noqa A003
        "type", sa.SmallInteger, default=PaymentType.PAYPAL.value
    )
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    recipient = sa.Column("recipient", sa.String(64))
    comment = sa.Column("comment", sa.String(126), nullable=True)


class CryptoPaymentData(db.Model):
    """Модель реквизитов криптовалюты."""

    __tablename__ = "general_payment_data"
    __table_args__ = {"extend_existing": True}

    id = sa.Column(  # noqa A003
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    )
    type = sa.Column(  # noqa A003
        "type", sa.SmallInteger, default=PaymentType.CRYPTO.value
    )
    dream_id = sa.Column("dream_id", sa.ForeignKey("dream.id"))
    token = sa.Column("token", sa.String(256))
    network = sa.Column("network", sa.String(256))
    address = sa.Column("address", sa.String(256))
    comment = sa.Column("comment", sa.String(126), nullable=True)


payment_data_history = sa.Table(
    "payment_data_history",
    METADATA,
    sa.Column(
        "payment_data_id", sa.ForeignKey("payment_data.id"), nullable=False
    ),
    sa.Column("version", sa.Integer, index=True, nullable=False),
    sa.Column("user_id", sa.ForeignKey("user.id"), nullable=False),
    sa.Column("country_id", sa.ForeignKey("country.id"), nullable=True),
    sa.Column("bank_name", sa.String(64), nullable=True),
    sa.Column("account_number", sa.String(64), nullable=True),
    sa.Column("internal_account_number", sa.String(64), nullable=True),
    sa.Column("holder_name", sa.String(64), nullable=False),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column(
        "purpose_id", sa.ForeignKey("donation_purpose.id"), nullable=True
    ),
    sa.Column("primary_payment_type_id", sa.Integer, nullable=True),
    sa.Column("reserve_payment_type_id", sa.Integer, nullable=True),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
    CREATED_BY_OPERATOR_COLUMN(),
    sa.PrimaryKeyConstraint("payment_data_id", "version"),
)

payment_data = sa.Table(
    "payment_data",
    METADATA,
    sa.Column(
        "id", sa.Integer, primary_key=True, index=True, autoincrement=True
    ),
    sa.Column("order_id", sa.ForeignKey("order.id"), nullable=False),
    sa.Column("country_id", sa.ForeignKey("country.id"), nullable=True),
    sa.Column("bank_name", sa.String(64), nullable=True),
    sa.Column("account_number", sa.String(64), nullable=True),
    sa.Column("internal_account_number", sa.String(64), nullable=True),
    sa.Column("holder_name", sa.String(64), nullable=False),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column(
        "purpose_id", sa.ForeignKey("donation_purpose.id"), nullable=True
    ),
    sa.Column(
        "primary_payment_type_id",
        sa.Integer,
        sa.ForeignKey("payment_type.id"),
        nullable=True,
    ),
    sa.Column("reserve_payment_type_id", sa.Integer, nullable=True),
    CREATED_AT_COLUMN(),
    UPDATED_AT_COLUMN(),
    CREATED_BY_OPERATOR_COLUMN(),
)
