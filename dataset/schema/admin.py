"""Admin schema setup."""
import graphene

from dataset.graphql_.operator import OperatorMutation, OperatorQuery
from dataset.graphql_.order import OrderAdminMutation
from dataset.graphql_.payment_data import PaymentDataAdminMutation
from dataset.graphql_.payment_type import PaymentTypeQueryAdmin
from dataset.graphql_.user import UserAdminMutation, UserAdminQuery
from dataset.schema.queries import StatisticQuery
from dataset.tables.country import CountryAdminQuery


class Query(
    UserAdminQuery,
    OperatorQuery,
    CountryAdminQuery,
    PaymentTypeQueryAdmin,
    StatisticQuery,
):
    """Queries for operators."""

    class Meta:
        """Metadata."""

        name = "Query"


class Mutation(
    OperatorMutation,
    UserAdminMutation,
    OrderAdminMutation,
    PaymentDataAdminMutation,
):
    """Mutations for operators."""

    class Meta:
        """Metadata."""

        name = "Mutation"


SCHEMA = graphene.Schema(query=Query, mutation=Mutation)
