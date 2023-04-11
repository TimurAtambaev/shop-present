"""Reusable code for user."""
from typing import Optional

import graphene
from graphene import ResolveInfo
from sqlalchemy import or_

from dataset.tables.country import CountryManager, PublicCountry
from dataset.tables.user import AchievementCode
from dataset.tables.user import User as UserModel


async def is_email_exists(email: str) -> bool:
    """Check if user with provided email already exists in db."""
    return await UserModel.query.where(
        or_(UserModel.email == email, UserModel.verified_email == email)
    ).gino.scalar()


UserAchievementCode = graphene.Enum(
    "AchievementCode",
    [
        (
            s.name,
            s.value,
        )
        for s in AchievementCode
    ],
)


class UserAchievement(graphene.ObjectType):
    """User achievements object."""

    code = graphene.Field(UserAchievementCode)
    is_complete = graphene.Boolean()
    progress = graphene.Float()


class User(graphene.ObjectType):  # noqa F811
    """Graphql model for user."""

    id = graphene.Int()  # noqa A003
    name = graphene.String()
    surname = graphene.String()
    email = graphene.String()
    unverified_email = graphene.String()
    country = graphene.Field(PublicCountry)
    language = graphene.String()
    birth_date = graphene.Date()
    is_verified = graphene.Boolean()
    is_female = graphene.Boolean()
    is_active = graphene.Boolean()
    achievements = graphene.List(UserAchievement)
    orders = graphene.List("dataset.graphql_.order.Order")
    created_by_operator_id = graphene.Int()
    phone = graphene.String()
    avatar = graphene.String()

    async def resolve_id(self, *args: tuple) -> None or int:
        """Resolve id."""
        if isinstance(self, dict):
            if self.get("id") is not None:
                return self.get("id")
            if self.get("user_id") is not None:
                return self.get("user_id")
            return None
        if hasattr(self, "id"):
            return self.id
        if hasattr(self, "user_id"):
            return self.user_id
        return None

    async def resolve_unverified_email(self, *args: tuple) -> tuple:
        """Resolve email field display."""
        return self.get("email") if isinstance(self, dict) else self.email

    async def resolve_email(self, *args: tuple) -> tuple:
        """Resolve email display. Tries to return verified email if exists."""
        vemail = (
            self.get("verified_email")
            if isinstance(self, dict)
            else getattr(self, "verified_email", None)
        )

        email = (
            self.get("email")
            if isinstance(self, dict)
            else getattr(self, "email", None)
        )

        if vemail:
            return vemail

        return email  # noqa R504

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

    async def resolve_is_verified(self, *args: tuple) -> tuple:
        """Resolve is verified field. Return true if verified email exists."""
        vemail = (
            self.get("verified_email")
            if isinstance(self, dict)
            else getattr(self, "verified_email", None)
        )

        return vemail is not None
