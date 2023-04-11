"""Graphql type, objects, queries, mutations and etc related to payment data."""
from copy import deepcopy
from typing import Dict, Optional

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from aiohttp.web_exceptions import HTTPInternalServerError
from argon2.exceptions import VerifyMismatchError
from gino import GinoConnection
from gino.transaction import GinoTransaction
from graphene import ResolveInfo
from sqlalchemy import asc, desc, select
from sqlalchemy.engine import RowProxy
from trafaret import Trafaret

from dataset.config import settings
from dataset.core.err_msgs import INVALID_PAYMENT_TYPE
from dataset.core.graphql import (
    DatabaseHelper,
    InputValidationMixin,
    LanguageHelper,
    authorized_only,
    build_data_from_result_for_one_row,
    is_field_requested,
    require_superuser,
)
from dataset.graphql_.payment_type import PaymentType
from dataset.integrations.integration import ExternalApplication
from dataset.tables.application import application
from dataset.tables.country import CountryManager, PublicCountry
from dataset.tables.donation import (
    donation_purpose,
    donation_purpose_language,
)
from dataset.tables.order import order
from dataset.tables.payment_data import payment_data, payment_data_history
from dataset.tables.payment_type import payment_type


async def remember_payment_data(
    info: ResolveInfo, payment_data_: RowProxy, user_id: int
) -> None:
    """Create record in user history based on user record."""
    payment_history_data = {
        "payment_data_id": payment_data_.id,
        "country_id": payment_data_.country_id,
        "user_id": user_id,
        "bank_name": payment_data_.bank_name,
        "account_number": payment_data_.account_number,
        "internal_account_number": payment_data_.internal_account_number,
        "holder_name": payment_data_.holder_name,
        "created_by_operator_id": payment_data_.created_by_operator_id,
        "created_at": payment_data_.created_at,
        "updated_at": payment_data_.updated_at,
        "purpose_id": payment_data_.purpose_id,
        "primary_payment_type_id": payment_data_.primary_payment_type_id,
        "reserve_payment_type_id": payment_data_.reserve_payment_type_id,
    }

    _tx: GinoTransaction
    async with (await DatabaseHelper.transaction(info)) as _tx:
        conn: GinoConnection = _tx.connection
        last_version = (
            await conn.scalar(
                select(
                    [payment_data_history.c.version],
                    payment_data_history.c.payment_data_id == payment_data_.id,
                ).order_by(desc(payment_data_history.c.version))
            )
            or 0
        )

        payment_history_data["version"] = last_version + 1

        await conn.status(
            payment_data_history.insert().values(
                **payment_history_data,
            )
        )


class PaymentData(graphene.ObjectType):
    """Payment data object to represent data from db for payment data.

    and payment data history
    """

    country = graphene.Field(PublicCountry)
    bank_name = graphene.String()
    account_number = graphene.String()
    internal_account_number = graphene.String()
    holder_name = graphene.String()
    notes = graphene.String()
    order_id = graphene.Int()
    total_donations_amount = graphene.Float()
    pending_donations_amount = graphene.Float()
    primary_payment_type = graphene.Field(PaymentType)
    reserve_payment_type = graphene.Field(PaymentType)

    async def resolve_country(self, info: ResolveInfo) -> Optional[dict]:
        """Resolve reference to country if object contains country_id."""
        country_id = (
            self.get("country_id")
            if isinstance(self, dict)
            else self.country_id
        )

        if country_id is None:
            return None

        return CountryManager.get_by_id(info, country_id)

    async def resolve_purpose(self, info: ResolveInfo) -> Optional[RowProxy]:
        """Resolve reference to purpose if object contains purpose_id."""
        purpose_id = (
            self.get("purpose_id")
            if isinstance(self, dict)
            else self.purpose_id
        )

        if purpose_id is None:
            return None

        return await DatabaseHelper.fetch_one(
            info,
            sa.select(
                [donation_purpose.c.id, donation_purpose_language.c.title]
            )
            .select_from(
                donation_purpose.join(
                    donation_purpose_language,
                    sa.and_(
                        donation_purpose_language.c.donation_purpose_id
                        == donation_purpose.c.id,
                        donation_purpose_language.c.language
                        == await LanguageHelper.get_language(info),
                    ),
                )
            )
            .where(donation_purpose.c.id == purpose_id),
        )

    async def resolve_primary_payment_type(
        self, info: ResolveInfo
    ) -> Optional[RowProxy]:
        """Resolve reference to primary payment type."""
        payment_type_id = (
            self.get("primary_payment_type_id")
            if isinstance(self, dict)
            else self.primary_payment_type_id
        )

        if payment_type_id is None:
            return None

        return await DatabaseHelper.fetch_one(
            info,
            sa.select([payment_type.c.id, payment_type.c.title]).where(
                payment_type.c.id == payment_type_id
            ),
        )

    async def resolve_reserve_payment_type(
        self, info: ResolveInfo
    ) -> Optional[RowProxy]:
        """Resolve reference to primary payment type."""
        payment_type_id = (
            self.get("reserve_payment_type_id")
            if isinstance(self, dict)
            else self.reserve_payment_type_id
        )

        if payment_type_id is None:
            return None

        return await DatabaseHelper.fetch_one(
            info,
            sa.select([payment_type.c.id, payment_type.c.title]).where(
                payment_type.c.id == payment_type_id
            ),
        )


class PaymentDataInput(graphene.InputObjectType, InputValidationMixin):
    """Input for Application referent level."""

    bank_name = graphene.String(required=False, allow_blank=False)
    account_number = graphene.String(
        required=True, min_length=12, max_length=64
    )
    internal_account_number = graphene.String(
        required=False, min_length=8, max_length=64
    )
    holder_name = graphene.String(required=True, allow_blank=False)
    country_id = graphene.Int()
    notes = graphene.String(required=False)
    purpose_id = graphene.Int(required=True)
    primary_payment_type_id = graphene.Int(required=True)
    reserve_payment_type_id = graphene.Int(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("bank_name", optional=True): T.String(allow_blank=True),
                T.Key("account_number"): T.String(
                    allow_blank=False, min_length=5, max_length=64
                ),
                T.Key("internal_account_number", optional=True): T.String(
                    allow_blank=True, max_length=64
                ),
                T.Key("holder_name"): T.String(),
                T.Key("country_id", optional=True): T.Int(),
                T.Key("notes", optional=True): T.String(allow_blank=True),
                T.Key("purpose_id"): T.Int(),
                T.Key("primary_payment_type_id"): T.Int(),
                T.Key("reserve_payment_type_id", optional=True): T.Int(),
            }
        )

    @classmethod
    async def validate(cls, value: Dict) -> Dict:
        """Validate data."""
        in_data = deepcopy(value)
        in_data["account_number"] = in_data.get("account_number", "").strip()
        in_data["internal_account_number"] = in_data.get(
            "internal_account_number", ""
        ).strip()
        if in_data["internal_account_number"]:
            try:
                T.String(min_length=5, max_length=64).check(
                    in_data["internal_account_number"]
                )
            except T.DataError as error_exc:
                raise ValueError(
                    f'"internal_account_number": {error_exc.as_dict()}'
                ) from error_exc

        return await super().validate(in_data)


class PaymentDataOrderUpdateAdminInput(PaymentDataInput):
    """Input for creating/updating orders payment data."""

    order_id = graphene.Int()

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return super().trafaret() + T.Dict(
            {
                T.Key("order_id"): T.Int(gt=0),
            }
        )


class PaymentDataOrderUpdateInput(PaymentDataInput):
    """Input for creating/updating orders payment data."""

    order_id = graphene.Int()
    password = graphene.String(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return super().trafaret() + T.Dict(
            {
                T.Key("order_id"): T.Int(gt=0),
                T.Key("password", optional=True): T.String(allow_blank=True),
            }
        )


class PaymentDataOrderUpdate(graphene.Mutation):
    """Mutation adds payment data to order."""

    class Input:
        """Mutation input."""

        input = graphene.Argument(  # noqa A003
            PaymentDataOrderUpdateInput, required=True
        )

    payment_data = graphene.Field(PaymentData)

    @authorized_only
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Mutation handler."""
        data = await PaymentDataOrderUpdateInput.validate(input)
        password = data.pop("password", None) or ""

        country_ = await CountryManager.get_by_id(info, _user.country_id)
        exists_payment_type = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([payment_type.c.id]).where(
                    sa.and_(
                        payment_type.c.id
                        == data.get("primary_payment_type_id"),
                        payment_type.c.id.in_(country_["payment_types"]),
                    )
                )
            ).select(),
        )
        if not exists_payment_type:
            error = await LanguageHelper.t(info, INVALID_PAYMENT_TYPE)
            raise RuntimeError(error)

        if data.get("internal_account_number") and not data.get(
            "reserve_payment_type_id"
        ):
            error = await LanguageHelper.t(
                info, "errors.backend.payment_type.no_reserve_payment"
            )
            raise RuntimeError(error)

        if not data.get("internal_account_number") and data.get(
            "reserve_payment_type_id"
        ):
            del data["reserve_payment_type_id"]
            del data["internal_account_number"]

        order_data = await DatabaseHelper.fetch_one(
            info,
            sa.select([order])
            .where(order.c.id == data.get("order_id"))
            .where(order.c.user_id == _user.id),
        )

        if not order_data:
            error = await LanguageHelper.t(
                info, "errors.backend.order.invalid_order"
            )
            raise RuntimeError(error)

        exists_purpose = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([donation_purpose.c.id]).where(
                    sa.and_(
                        donation_purpose.c.id == data.get("purpose_id"),
                        donation_purpose.c.is_active == True,  # noqa E712
                    )
                )
            ).select(),
        )

        if not exists_purpose:
            raise RuntimeError(
                await LanguageHelper.t(
                    info,
                    "errors.backend.donation.purpose_not_exist",
                    msg_vars={"id": data.get("purpose_id")},
                )
            )

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            pd_id = await _tx.connection.scalar(
                sa.select([payment_data.c.id], for_update=True).where(
                    payment_data.c.order_id == data.get("order_id")
                )
            )

            data["created_at"] = sa.func.now()
            data["updated_at"] = sa.func.now()

            if pd_id:
                try:
                    settings.HASHER.verify(_user.password, password)
                except VerifyMismatchError as error_exc:
                    error = await LanguageHelper.t(
                        info, "errors.backend.user.invalid_password"
                    )
                    raise Exception(error) from error_exc

                await _tx.connection.status(
                    payment_data.update()
                    .values(**data)
                    .where(payment_data.c.id == pd_id)
                )
            else:
                # Send request to ImRix when payment Data is filled for the first time
                app = await DatabaseHelper.fetch_one(
                    info,
                    select([application])
                    .where(application.c.id == order_data.application_id)
                    .limit(1)
                    .order_by(asc(application.c.id)),
                )

                if not app:
                    error = await LanguageHelper.t(
                        info, "errors.backend.order.invalid_application"
                    )
                    raise RuntimeError(error)

                try:
                    integration = ExternalApplication(
                        app.integration_url, app.integration_token
                    )
                    await integration.prepare_for_payment(
                        order_data.product_id
                    )
                except RuntimeError as error_exc:
                    error = await LanguageHelper.t(
                        info, "errors.backend.payment_data.update_error"
                    )
                    raise HTTPInternalServerError(reason=error) from error_exc

                # Update payment Data
                await _tx.connection.status(
                    payment_data.insert().values(
                        **data,
                    )
                )
                pd_id = _tx.connection.scalar(
                    sa.select([sa.func.currval("payment_data_id_seq")])
                )

            pd_row = await _tx.connection.one(
                sa.select([payment_data], payment_data.c.id == pd_id)
            )

            result = build_data_from_result_for_one_row(pd_row, {})

            if is_field_requested(info, "paymentData.purpose"):
                result["purpose"] = await _tx.connection.one(
                    sa.select(
                        [
                            donation_purpose.c.id,
                            donation_purpose_language.c.title,
                        ]
                    )
                    .select_from(
                        donation_purpose.join(
                            donation_purpose_language,
                            sa.and_(
                                donation_purpose_language.c.donation_purpose_id
                                == donation_purpose.c.id,
                                donation_purpose_language.c.language
                                == await LanguageHelper.get_language(info),
                            ),
                        )
                    )
                    .where(donation_purpose.c.id == pd_row["purpose_id"])
                )

            if is_field_requested(info, "paymentData.primaryPaymentType"):
                result["primary_payment_type"] = await _tx.connection.one(
                    sa.select([payment_type.c.id, payment_type.c.title]).where(
                        payment_type.c.id == pd_row["primary_payment_type_id"]
                    )
                )

            if is_field_requested(info, "paymentData.reservePaymentType"):
                result[
                    "reserve_payment_type"
                ] = await _tx.connection.one_or_none(
                    sa.select([payment_type.c.id, payment_type.c.title]).where(
                        payment_type.c.id == pd_row["reserve_payment_type_id"]
                    )
                )

            await remember_payment_data(info, pd_row, _user.id)

            return {"payment_data": result}


class PaymentDataPublicMutation(graphene.ObjectType):
    """Payment data related mutations for public api."""

    payment_data_order_update = PaymentDataOrderUpdate.Field()


class PaymentDataOrderUpdateAdmin(graphene.Mutation):
    """Mutation adds payment data to order."""

    class Input:
        """Mutation input."""

        input = graphene.Argument(  # noqa A003
            PaymentDataOrderUpdateAdminInput, required=True
        )

    payment_data = graphene.Field(PaymentData)

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Mutation handler."""
        data = await PaymentDataOrderUpdateAdminInput.validate(input)

        order_data = await DatabaseHelper.fetch_one(
            info, sa.select([order]).where(order.c.id == data.get("order_id"))
        )

        if not order_data:
            error = await LanguageHelper.t(
                info, "errors.backend.order.invalid_order"
            )
            raise RuntimeError(error)

        exists_purpose = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([donation_purpose.c.id]).where(
                    sa.and_(
                        donation_purpose.c.id == data.get("purpose_id"),
                        donation_purpose.c.is_active == True,  # noqa E712
                    )
                )
            ).select(),
        )

        if not exists_purpose:
            raise RuntimeError(
                await LanguageHelper.t(
                    info,
                    "errors.backend.donation.purpose_not_exist",
                    msg_vars={"id": data.get("purpose_id")},
                )
            )

        exists_payment_type = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([payment_type.c.id]).where(
                    payment_type.c.id == data.get("primary_payment_type_id")
                )
            ).select(),
        )

        if not exists_payment_type:
            error = await LanguageHelper.t(info, INVALID_PAYMENT_TYPE)
            raise RuntimeError(error)

        if data.get("reserve_payment_type_id") and data.get(
            "internal_account_number"
        ):
            exists_reserve_payment_type = await DatabaseHelper.scalar(
                info,
                sa.exists(
                    sa.select([payment_type.c.id]).where(
                        payment_type.c.id
                        == data.get("reserve_payment_type_id")
                    )
                ).select(),
            )
            if not exists_reserve_payment_type:
                error = await LanguageHelper.t(info, INVALID_PAYMENT_TYPE)
                raise RuntimeError(error)

        if data.get("internal_account_number") and not data.get(
            "reserve_payment_type_id"
        ):
            error = await LanguageHelper.t(
                info, "errors.backend.payment_type.no_reserve_payment"
            )
            raise RuntimeError(error)

        if not data.get("internal_account_number") and data.get(
            "reserve_payment_type_id"
        ):
            del data["reserve_payment_type_id"]
            del data["internal_account_number"]

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            pd_id = await _tx.connection.scalar(
                sa.select([payment_data.c.id], for_update=True).where(
                    payment_data.c.order_id == data.get("order_id")
                )
            )

            data["created_at"] = sa.func.now()
            data["updated_at"] = sa.func.now()

            if pd_id:
                await _tx.connection.status(
                    payment_data.update()
                    .values(**data)
                    .where(payment_data.c.id == pd_id)
                )
            else:
                # Send request to ImRix when payment Data is filled for the first time
                app = await DatabaseHelper.fetch_one(
                    info,
                    select([application])
                    .where(application.c.id == order_data.application_id)
                    .limit(1)
                    .order_by(asc(application.c.id)),
                )

                if not app:
                    error = await LanguageHelper.t(
                        info, "errors.backend.order.invalid_application"
                    )
                    raise RuntimeError(error)

                try:
                    integration = ExternalApplication(
                        app.integration_url, app.integration_token
                    )
                    await integration.prepare_for_payment(
                        order_data.product_id
                    )
                except RuntimeError as error_exc:
                    error = await LanguageHelper.t(
                        info, "errors.backend.payment_data.update_error"
                    )
                    raise HTTPInternalServerError(reason=error) from error_exc

                # Update payment Data
                await _tx.connection.status(
                    payment_data.insert().values(
                        **data,
                    )
                )
                pd_id = _tx.connection.scalar(
                    sa.select([sa.func.currval("payment_data_id_seq")])
                )

            pd_row = await _tx.connection.one(
                sa.select([payment_data], payment_data.c.id == pd_id)
            )

            result = build_data_from_result_for_one_row(pd_row, {})

            if is_field_requested(info, "paymentData.purpose"):
                purpose = await _tx.connection.one(
                    sa.select(
                        [
                            donation_purpose.c.id,
                            donation_purpose_language.c.title,
                        ]
                    )
                    .select_from(
                        donation_purpose.join(
                            donation_purpose_language,
                            sa.and_(
                                donation_purpose_language.c.donation_purpose_id
                                == donation_purpose.c.id,
                                donation_purpose_language.c.language
                                == await LanguageHelper.get_language(info),
                            ),
                        )
                    )
                    .where(donation_purpose.c.id == pd_row["purpose_id"])
                )
                result["purpose"] = purpose

            if is_field_requested(info, "paymentData.primaryPaymentType"):
                result["primary_payment_type"] = await _tx.connection.one(
                    sa.select([payment_type.c.id, payment_type.c.title]).where(
                        payment_type.c.id == pd_row["primary_payment_type_id"]
                    )
                )

            if is_field_requested(info, "paymentData.reservePaymentType"):
                result["reserve_payment_type"] = (
                    await _tx.connection.one_or_none(
                        sa.select(
                            [payment_type.c.id, payment_type.c.title]
                        ).where(
                            payment_type.c.id
                            == pd_row["reserve_payment_type_id"]
                        )
                    )
                    or None
                )

            await remember_payment_data(info, pd_row, order_data.user_id)

            return {"payment_data": result}


class PaymentDataAdminMutation(graphene.ObjectType):
    """Payment data related mutations for public api."""

    payment_data_order_update = PaymentDataOrderUpdateAdmin.Field()
