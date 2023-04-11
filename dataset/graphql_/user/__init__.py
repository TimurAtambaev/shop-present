"""Graphql type, objects, queries, mutations and etc related to users."""
from typing import Optional

import graphene
import sqlalchemy as sa
from dependency_injector.wiring import Provide, inject
from graphene import ResolveInfo
from localization.service import LanguageService
from sqlalchemy import and_, asc, cast, desc

from dataset.core.container import Container
from dataset.core.graphql import (
    DatabaseHelper,
    IDInputType,
    anonymous,
    authorized_only,
    authorized_without_content_manager,
    build_data_from_result,
    build_joint_query_from_info,
    is_field_requested,
)
from dataset.graphql_.user.public import (
    ResetTokenInput,
    Result,
    SupportRequest,
    UserEmailConfirmationMutation,
    UserRestorePasswordMutation,
)
from dataset.middlewares import request_var
from dataset.rest.models.utils import SortChoices
from dataset.tables.application import application
from dataset.tables.donation import Donation as donation  # noqa N813
from dataset.tables.order import order
from dataset.tables.payment_data import payment_data_history
from dataset.tables.user import User as GinoUser
from dataset.tables.user import user_history

from .admin import (
    BlockUserMutation,
    LoginAsLinkMutation,
    UnblockUserMutation,
    UserChangeEmailMutation,
    UserChangeMutation,
    UserCreateMutation,
    UserSearchInput,
    UsersList,
)
from .utils import User


class UserPublicMutation(graphene.ObjectType):
    """User related public mutations."""

    verify_email = UserEmailConfirmationMutation.Field()
    restore_password = UserRestorePasswordMutation.Field()
    support_request = SupportRequest.Field()


class UserPublicQuery(graphene.ObjectType):
    """User related public queries."""

    me = graphene.Field(User)

    check_reset_token = graphene.Field(
        Result,
        input=graphene.Argument(ResetTokenInput, required=True),
        description="Check reset token",
    )

    @anonymous
    @inject
    async def resolve_check_reset_token(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        language_service: LanguageService = Provide[
            Container.localization.service
        ],
    ) -> dict:
        """Return true if reset token correct."""
        data = await ResetTokenInput.validate(input)
        reset_token: str = data.get("reset_token")

        user_ = await GinoUser.query.where(
            and_(
                GinoUser.reset_token == reset_token,
                GinoUser.is_active == True,  # noqa E712
                GinoUser.reset_token_valid_till >= sa.func.now(),
            )
        ).gino.fisrt()

        if user_ is None:
            error = await language_service.get_error_text(
                "invalid_reset_token", request_var.get()["language"]
            )
            raise RuntimeError(error)

        return {"result": True}

    @authorized_only
    async def resolve_me(
        self,
        info: ResolveInfo,
        _user: object,
    ) -> dict:
        """Return authorized user profile."""
        return _user.to_dict()


def sort_users(
    id: Optional[SortChoices] = None,  # noqa A002
    email: Optional[SortChoices] = None,
    status: Optional[SortChoices] = None,
) -> list:
    """Сортировка полей."""
    sort_type = {SortChoices.asc.value: asc, SortChoices.desc.value: desc}
    query_data = (
        (id, sort_type[id](GinoUser.id) if id else None),
        (email, sort_type[email](GinoUser.email) if email else None),
        (status, sort_type[status](GinoUser.is_active) if status else None),
    )
    return [query for value, query in query_data if query is not None]


class UserAdminMutation(graphene.ObjectType):
    """User related public mutations."""

    user_change_email = UserChangeEmailMutation.Field()
    block_user = BlockUserMutation.Field()
    unblock_user = UnblockUserMutation.Field()
    user_create = UserCreateMutation.Field()
    user_change = UserChangeMutation.Field()
    login_as_link = LoginAsLinkMutation.Field()


class UserAdminQuery(graphene.ObjectType):
    """Graphql user related queries."""

    users = graphene.Field(
        UsersList,
        input=graphene.Argument(UserSearchInput, required=True),
        description="List of users",
    )
    user = graphene.Field(
        User,
        input=graphene.Argument(IDInputType, required=True),
        description="Get user by ID",
    )

    @authorized_without_content_manager
    async def resolve_users(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Resolve request for list of users."""
        await UserSearchInput.validate(input)
        query = input.get("query", "").lower()
        is_active = input.get("is_active")
        limit = input.get("limit", 20)
        offset = input.get("offset", 0)
        id = input.get("id", None)  # noqa A001
        email = input.get("email", None)
        status = input.get("status", None)

        sort = sort_users(id, email, status)
        whereclause = []

        if is_active is not None:
            whereclause.append(GinoUser.is_active == is_active)

        if query:
            whereclause.append(
                sa.or_(
                    cast(GinoUser.id, sa.String) == query,
                    sa.func.lower(GinoUser.name).like(f"%{query}%"),
                    sa.func.lower(GinoUser.surname).like(f"%{query}%"),
                    sa.func.lower(GinoUser.email).like(f"%{query}%"),
                    sa.func.lower(GinoUser.verified_email).like(f"%{query}%"),
                )
            )

        whereclause = sa.and_(*whereclause)

        count = await DatabaseHelper.scalar(
            info,
            sa.select(
                [sa.func.count(sa.distinct(GinoUser.id))], whereclause
            ).select_from(
                GinoUser.join(
                    order, full=True, onclause=(GinoUser.id == order.c.user_id)
                )
            ),
        )

        result = build_data_from_result(
            await DatabaseHelper.fetch_all(
                info,
                sa.select([GinoUser], whereclause)
                .select_from(
                    GinoUser.join(
                        order,
                        full=True,
                        onclause=(GinoUser.id == order.c.user_id),
                    )
                )
                .offset(offset)
                .limit(limit)
                .order_by(*sort if sort else ())
                .group_by(GinoUser.id),
            ),
            {"orders": []},
        )

        if is_field_requested(info, "result.orders"):
            whereclause = order.c.user_id.in_(
                [u.get("id") for u in result.values()]
            )
            query = sa.select([order], whereclause)

            if is_field_requested(info, "orders.application"):
                query = build_joint_query_from_info(
                    info,
                    "orders",
                    whereclause,
                    order,
                    {
                        "application": application,
                    },
                )

            query = query.order_by(sa.desc(order.c.created_at))

            order_map = build_data_from_result(
                await DatabaseHelper.fetch_all(info, query),
                {"application": application, "donations": []},
            )

            if is_field_requested(info, "result.orders.donations"):
                query = build_joint_query_from_info(
                    info,
                    "result.orders.donations",
                    donation.c.order_id.in_(order_map.keys()),
                    donation,
                    {
                        "recipient_id": user_history,
                    },
                ).order_by(donation.c.order_id)

                for don in build_data_from_result(
                    await DatabaseHelper.fetch_all(info, query),
                    {
                        "payment_data": payment_data_history,
                        "recipient": user_history,
                    },
                ).values():
                    order_map[don.get("order_id")]["donations"].append(don)

            for ordr in order_map.values():
                orders = []
                orders.extend(result[ordr.get("user_id")]["orders"])
                orders.append(ordr)
                result[ordr.get("user_id")]["orders"] = orders

        return {"count": count, "result": result.values()}
