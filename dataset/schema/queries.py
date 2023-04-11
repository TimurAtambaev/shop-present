"""Common queries reused in all schemas."""
import graphene
import trafaret as T  # noqa N812
from graphene import ResolveInfo

from dataset.core.graphql import authorized_without_content_manager
from dataset.utils.user import UserLib


class CountryStatistic(graphene.ObjectType):
    """Graphql model for country statisctic."""

    id = graphene.Int()  # noqa A003
    country_name = graphene.String()
    active_users = graphene.Int()


class Dashboard(graphene.ObjectType):
    """Graphql model for dashboard data."""

    active_users = graphene.Int()
    country_statistic = graphene.List(CountryStatistic)


class StatisticQuery(graphene.ObjectType):
    """Graphql object to return localization data."""

    dashboard = graphene.Field(Dashboard)

    @authorized_without_content_manager
    async def resolve_dashboard(self, info: ResolveInfo) -> dict:
        """Dashboard statistic data resolver."""
        data = await UserLib.get_total_users_by_country(info)
        result = {  # noqa SIM904
            "active_users": await UserLib.get_total_users(info)
        }
        result["country_statistic"] = [
            {
                "id": users_in_country["country_id"],
                "country_name": users_in_country["country_name"],
                "active_users": users_in_country["total_users"],
            }
            for users_in_country in data
        ]

        return result
