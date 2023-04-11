"""Graphql type, objects, queries, mutations and etc related to payment types."""

import graphene
from graphene import ResolveInfo
from sqlalchemy import select

from dataset.core.graphql import (
    DatabaseHelper,
    LanguageHelper,
    authorized_only,
    authorized_without_content_manager,
    build_data_from_result,
)
from dataset.tables.country import CountryManager
from dataset.tables.payment_type import payment_type


class PaymentType(graphene.ObjectType):
    """Payment type object."""

    id = graphene.Int()  # noqa A003
    title = graphene.String()


class PaymentTypeAdmin(graphene.ObjectType):
    """Payment type object for operator."""

    id = graphene.Int()  # noqa A003
    title = graphene.String()
    created_by_operator_id = graphene.Int()

    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()


class PaymentTypeQuery(graphene.ObjectType):
    """Payment type list query."""

    payment_types = graphene.List(PaymentType)

    @authorized_only
    async def resolve_payment_types(
        self, info: ResolveInfo, _user: object
    ) -> dict.values:
        """Payment type list query resolver. Returns list of payment types."""
        country_ = await CountryManager.get_by_id(info, _user.country_id)

        if not country_ or not country_.get("is_active"):
            raise RuntimeError(
                await LanguageHelper.t(info, "errors.backend.country.invalid")
            )

        result = build_data_from_result(
            await DatabaseHelper.fetch_all(
                info,
                select([payment_type])
                .where(payment_type.c.id.in_(country_["payment_types"]))
                .order_by(payment_type.c.id),
            ),
            {},
        )

        return result.values()


class PaymentTypeQueryAdmin(graphene.ObjectType):
    """Payment type list query for Operators."""

    payment_types = graphene.List(PaymentTypeAdmin)

    @authorized_without_content_manager
    async def resolve_payment_types(self, info: ResolveInfo) -> dict.values:
        """Payment type list query resolver.

        Returns list of payment types for Operator.
        """
        result = build_data_from_result(
            await DatabaseHelper.fetch_all(
                info, select([payment_type]).order_by(payment_type.c.id)
            ),
            {},
        )

        return result.values()
