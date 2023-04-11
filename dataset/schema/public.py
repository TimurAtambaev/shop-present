"""Public schema setup."""
import graphene

from dataset.graphql_.application import ApplicationPublicMutation
from dataset.graphql_.user import UserPublicMutation, UserPublicQuery
from dataset.tables.country import CountryPublicQuery


class Query(
    UserPublicQuery,
    CountryPublicQuery,
):
    """Queries for public app."""

    class Meta:
        """Metadata."""

        name = "Query"


class Mutation(
    UserPublicMutation,
    ApplicationPublicMutation,
):
    """Mutations for public app."""

    class Meta:
        """Metadata."""

        name = "Mutation"


SCHEMA = graphene.Schema(
    query=Query,
    mutation=Mutation,
)
