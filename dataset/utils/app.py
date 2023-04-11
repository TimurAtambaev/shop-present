"""Libs for application object."""
from graphene import ResolveInfo
from sqlalchemy import asc, select

from dataset.core.graphql import DatabaseHelper
from dataset.tables.application import application, referent_level


class ApplicationLib:
    """Lib for user object."""

    @classmethod
    async def get_first_app(cls, info: ResolveInfo) -> dict:
        """Return first active application ( sort by id asc )."""
        app = await DatabaseHelper.fetch_one(
            info,
            select([application])
            .where(application.c.is_active == True)  # noqa E712
            .limit(1)
            .order_by(asc(application.c.id)),
        )
        if not app:
            return {}

        app_levels = {
            item.number: item
            for item in await DatabaseHelper.fetch_all(
                info,
                select([referent_level]).where(
                    referent_level.c.application_id == app.id
                ),
            )
        }

        return {"application": app, "levels": app_levels}
