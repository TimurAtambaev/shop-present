"""Graphql type, objects, queries, mutations and etc related to user For Operators."""
import re
import urllib
from datetime import datetime, timedelta
from secrets import token_urlsafe

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from aiohttp.web_exceptions import HTTPInternalServerError
from asyncpg import UniqueViolationError
from gino.transaction import GinoTransaction
from graphql import ResolveInfo
from sqlalchemy import func
from trafaret import Trafaret

from dataset.config import settings
from dataset.core.auth import prepare_token
from dataset.core.graphql import (
    DatabaseHelper,
    IDInputType,
    InputValidationMixin,
    ListInputType,
    ListResultType,
    app_from_info,
    authorized_without_content_manager,
    require_superuser,
)
from dataset.core.log import LOGGER
from dataset.graphql_.user.utils import User
from dataset.middlewares import request_var
from dataset.migrations import db
from dataset.rest.views.utils import refresh_dreams_view
from dataset.tables.application import oauth2_token
from dataset.tables.country import CountryManager
from dataset.tables.user import User as GinoUser
from dataset.utils.app import ApplicationLib


class UsersList(ListResultType):
    """Graphql object to return list of users."""

    result = graphene.List(User)


class UserSearchInput(ListInputType):
    """Graphql object to request list of users."""

    query = graphene.String()
    is_active = graphene.Boolean(required=False)
    id = graphene.String(required=False)  # noqa A003
    email = graphene.String(required=False)
    status = graphene.String(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return super().trafaret() + T.Dict(
            {
                T.Key("query"): T.String(allow_blank=True, max_length=128),
                T.Key("is_active", optional=True): T.Bool(),
                T.Key("id", optional=True): T.String(),
                T.Key("email", optional=True): T.String(),
                T.Key("status", optional=True): T.String(),
            }
        )


class UserChangeEmailInput(graphene.InputObjectType, InputValidationMixin):
    """Input for change user email by Operator."""

    id = graphene.Int(required=True)  # noqa A003
    email = graphene.String(required=True)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict({T.Key("email"): T.String(), T.Key("id"): T.Int()})


class UserCreateInput(graphene.InputObjectType, InputValidationMixin):
    """Input for User Create mutation."""

    name = graphene.String(required=True)
    surname = graphene.String(required=True)
    email = graphene.String(required=True)
    password = graphene.String(required=True, min_length=8)
    birth_date = graphene.Date()
    country = graphene.Int()
    currency_id = graphene.Int()
    is_female = graphene.Boolean(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("name", optional=True): T.String(
                    min_length=settings.LEN_NAME, allow_blank=False
                ),
                T.Key("surname", optional=True): T.String(
                    min_length=settings.LEN_NAME, allow_blank=False
                ),
                T.Key("email"): T.Regexp(r"^[^@]+@[^@]+$", re.I),
                T.Key("password"): T.String(min_length=settings.LEN_PASSWORD),
                T.Key("birth_date"): T.Date(),
                T.Key("country"): T.Int(),
                T.Key("currency_id", optional=True): T.Int(),
                T.Key("is_female", optional=True): T.Bool(),
            }
        )


class UserCreateMutation(graphene.Mutation):
    """Mutation to create new user."""

    class Input:
        """Input description."""

        input = graphene.Argument(UserCreateInput, required=True)  # noqa A003

    user = graphene.Field(User, required=True)  # noqa F811

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
    ) -> dict:
        """User creation."""
        data = await UserCreateInput.validate(input)
        language_service = app_from_info(info).localization_container.service()
        data["verified_email"] = data.pop("email").lower()
        data["is_active"] = True
        data["password"] = settings.HASHER.hash(data.get("password"))
        data["created_at"] = sa.func.now()
        data["updated_at"] = sa.func.now()
        data["created_by_operator_id"] = (
            info.context.get("request").get("user").id
        )
        data["updated_by_operator_id"] = (
            info.context.get("request").get("user").id
        )

        if data.get("is_female"):
            data["is_female"] = data.pop("is_female")

        country = (
            await CountryManager.get_by_id(info, data.get("country"))
        ).get("is_active")
        data["country_id"] = data.pop("country")
        if not data.get("currency_id"):
            data["currency_id"] = settings.EURO_ID
        if not country:
            error = await language_service.get_error_text(
                "invalid_country", request_var.get()["language"]
            )
            raise RuntimeError(error)

        min_date = datetime.utcnow().date() - timedelta(days=(365 * 18) + 4)
        if data.get("birth_date") > min_date:
            error = await language_service.get_error_text(
                "not_18", request_var.get()["language"]
            )
            raise RuntimeError(error)
        exist_user = await GinoUser.query.where(
            sa.or_(
                func.lower(GinoUser.email) == data["verified_email"],
                func.lower(GinoUser.verified_email) == data["verified_email"],
            )
        ).gino.first()

        if exist_user:
            error = await language_service.get_error_text(
                "email_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            try:
                user_ = await GinoUser.create(**data)
            except UniqueViolationError as error_exc:
                error = await language_service.get_error_text(
                    "email_exist", request_var.get()["language"]
                )
                raise RuntimeError(error) from error_exc

            return {"user": user_}


class UserChangeEmailMutation(graphene.Mutation):
    """Mutation to authorize operator."""

    class Input:
        """Mutation input."""

        input = graphene.Argument(  # noqa A003
            UserChangeEmailInput, required=True
        )

    user = graphene.Field(User, required=True)  # noqa F811

    @authorized_without_content_manager
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Proceeds validation."""
        language_service = app_from_info(info).localization_container.service()
        data = await UserChangeEmailInput.validate(input)

        user_id: int = data.pop("id")
        email = data.pop("email")

        data["email"] = email.lower()
        data["updated_by_operator_id"] = _user.id
        data["updated_at"] = sa.func.now()

        req_user = await GinoUser.get(user_id)

        if not req_user:
            error = await language_service.get_error_text(
                "id_not_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        data["verified_email"] = data["email"]

        exists = await GinoUser.query.where(
            sa.or_(
                sa.func.lower(GinoUser.email) == email.lower(),
                sa.func.lower(GinoUser.verified_email) == email.lower(),
            )
        ).gino.first()
        if exists:
            error = await language_service.get_error_text(
                "email_in_use", request_var.get()["language"]
            )
            raise RuntimeError(error)

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            try:
                user_ = await GinoUser.get(user_id)
                await user_.update(**data).apply()
            except UniqueViolationError as exn:
                LOGGER.error(exn)  # noqa G200
                error = await language_service.get_error_text()
                raise HTTPInternalServerError(reason=error) from exn

        return {"user": user_}


class UserChangeInput(graphene.InputObjectType, InputValidationMixin):
    """Input for User Change mutation."""

    id = graphene.Int(required=True)  # noqa A003
    name = graphene.String()
    surname = graphene.String()
    country = graphene.Int(required=False)
    language = graphene.String(required=False)
    birth_date = graphene.Date(required=False)
    is_female = graphene.Boolean(required=False)
    phone = graphene.String(required=False)

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("id"): T.Int(),
                T.Key("name", optional=True): T.String(
                    min_length=settings.LEN_NAME, allow_blank=False
                ),
                T.Key("surname", optional=True): T.String(
                    min_length=settings.LEN_NAME, allow_blank=False
                ),
                T.Key("country", optional=True) >> "country_id": T.Int(),
                T.Key("language", optional=True): T.String(
                    min_length=1, allow_blank=False
                ),
                T.Key("birth_date", optional=True): T.Date(),
                T.Key("is_female", optional=True): T.Bool(),
                T.Key("phone", optional=True): T.String(allow_blank=True),
            }
        )


class UserChangeMutation(graphene.Mutation):
    """Mutation to update user data."""

    class Input:
        """Input description."""

        input = graphene.Argument(UserChangeInput, required=True)  # noqa A003

    user = graphene.Field(User, required=True)  # noqa F811

    @require_superuser
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Change user mutation."""
        language_service = app_from_info(info).localization_container.service()
        data = await UserChangeInput.validate(input)

        user_id = data.pop("id")
        exist_user = await GinoUser.get(user_id)

        if not exist_user:
            error = await language_service.get_error_text(
                "id_not_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        if data.get("country_id") and not (
            await CountryManager.get_by_id(info, data.get("country_id"))
        ).get("is_active"):
            error = await language_service.get_error_text(
                "invalid_country", request_var.get()["language"]
            )
            raise RuntimeError(error)

        if data.get("birth_date"):
            min_date = datetime.utcnow().date() - timedelta(
                days=(365 * 18) + 4
            )  # 18 years
            if data.get("birth_date") > min_date:
                error = await language_service.get_error_text(
                    "not_18", request_var.get()["language"]
                )
                raise RuntimeError(error)

        profile_data = {k: v for k, v in data.items() if v is not None}

        if profile_data:
            profile_data["updated_at"] = sa.func.now()
            profile_data["updated_by_operator_id"] = _user.id
            _tx: GinoTransaction
            async with db.transaction() as _tx:  # noqa F841
                await exist_user.update(**profile_data).apply()

        return {"user": exist_user}


class BlockUserMutation(graphene.Mutation):
    """Mutation to block user."""

    class Input:
        """Mutation input."""

        input = graphene.Argument(IDInputType, required=True)  # noqa A003

    user = graphene.Field(User, required=True)  # noqa F811

    @authorized_without_content_manager
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Mutation for block user."""
        await IDInputType.validate(input)
        language_service = app_from_info(info).localization_container.service()
        user_id: int = input.pop("id")

        exist_user = await GinoUser.get(user_id)
        if not exist_user:
            error = await language_service.get_error_text(
                "id_not_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        if not exist_user.is_active:
            raise RuntimeError(
                await language_service.get_error_text(
                    "blocked", request_var.get()["language"]
                )
            )

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            await exist_user.update(
                is_active=False,
                updated_by_operator_id=_user.id,
                updated_at=sa.func.now(),
            ).apply()
        await refresh_dreams_view()
        return {"user": exist_user}


class UnblockUserMutation(graphene.Mutation):
    """Mutation to block user."""

    class Input:
        """Mutation input."""

        input = graphene.Argument(IDInputType, required=True)  # noqa A003

    user = graphene.Field(User, required=True)  # noqa F811

    @authorized_without_content_manager
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
        _user: object,
    ) -> dict:
        """Mutation for unblock user."""
        await IDInputType.validate(input)
        language_service = app_from_info(info).localization_container.service()
        user_id: int = input.pop("id")

        exist_user = await GinoUser.get(user_id)

        if not exist_user:
            error = await language_service.get_error_text(
                "id_not_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        if exist_user.is_active:
            error = await language_service.get_error_text(
                "active", request_var.get()["language"]
            )
            raise RuntimeError(error)

        _tx: GinoTransaction
        async with db.transaction() as _tx:  # noqa F841
            await exist_user.update(
                is_active=True,
                updated_by_operator_id=_user.id,
                updated_at=sa.func.now(),
            ).apply()
        await refresh_dreams_view()
        return {"user": exist_user}


class LoginAsLinkMutation(graphene.Mutation):
    """Mutation to generate link with temporary token to get user token."""

    class Input:
        """Input description."""

        input = graphene.Argument(IDInputType, required=True)  # noqa A003

    link = graphene.String()

    @authorized_without_content_manager
    async def mutate(
        self,
        info: ResolveInfo,
        input: dict,  # noqa A002
    ) -> dict:
        """Get link with temporary token resolver."""
        data = await IDInputType.validate(input)
        app = app_from_info(info)
        language_service = app.localization_container.service()

        # get first active app ( sort by id asc )
        application = await ApplicationLib.get_first_app(info)
        if not application:
            error = await language_service.get_error_text(
                "invalid_application", request_var.get()["language"]
            )
            raise RuntimeError(error)

        user_id: int = data.pop("id")
        exist_user = await GinoUser.get(user_id)

        if not exist_user:
            error = await language_service.get_error_text(
                "id_not_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)

        _tx: GinoTransaction
        token = token_urlsafe(nbytes=150)
        auth_token_data = {
            "user_id": user_id,
            "application_id": application["application"].id,
            "token": prepare_token(info, token),
            "is_revoked": False,
            "issued_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7),
        }

        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn = _tx.connection
            try:
                await conn.status(
                    oauth2_token.insert().values(**auth_token_data)
                )
                return {
                    "link": urllib.parse.urlunparse(
                        (
                            "https",
                            settings.GS_APP_DOMAIN,
                            f"/admin-auth/{token}",
                            None,
                            "",
                            "",
                        )
                    )
                }
            except UniqueViolationError as exn:
                LOGGER.error(exn)  # noqa G200
                error = await language_service.get_error_text(
                    "update_error", request_var.get()["language"]
                )
                raise HTTPInternalServerError(reason=error) from exn
