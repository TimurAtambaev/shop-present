"""Application related graphql_ objects, queries, mutations."""
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Dict

import graphene
import sqlalchemy as sa
import trafaret as T  # noqa N812
from argon2.exceptions import VerifyMismatchError
from gino.transaction import GinoTransaction
from graphql import ResolveInfo
from trafaret import Trafaret

from dataset.config import settings
from dataset.core.auth import prepare_token
from dataset.core.graphql import (
    DatabaseHelper,
    InputValidationMixin,
    app_from_info,
    authorized_only,
)
from dataset.integrations.aws import AWS as AWSIntegration  # noqa N811
from dataset.middlewares import request_var
from dataset.tables.application import (
    application,
    oauth2_authorization_code,
    oauth2_token,
)
from dataset.tables.user import User
from dataset.utils.common import get_ru_url


class Application(graphene.ObjectType):
    """Graphql model for application."""

    id = graphene.Int()  # noqa A003
    name = graphene.String()
    description = graphene.String()
    color = graphene.String()
    logo = graphene.String()
    parent_key_name = graphene.String()
    key_name = graphene.String()
    is_active = graphene.Boolean()
    client_id = graphene.String()
    client_secret = graphene.String()
    redirect_uri = graphene.String()
    integration_url = graphene.String()
    integration_token = graphene.String()


class AuthorizationCodeInput(graphene.InputObjectType, InputValidationMixin):
    """Input for AuthorizationCode mutation."""

    application_id = graphene.Int(
        required=True, description="Application identifier"
    )
    dream_id = graphene.Int(required=False, description="Dream identifier")
    page = graphene.String(required=False, description="Name of redirect page")

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("application_id"): T.Int(gt=0),
                T.Key("dream_id", optional=True): T.Int(gt=0),
                T.Key("page", optional=True): T.String(),
            }
        )


class AuthorizationTokenInput(graphene.InputObjectType, InputValidationMixin):
    """Input for AuthorizationCode mutation."""

    client_id = graphene.String(required=True, description="Client identifier")
    client_secret = graphene.String(required=True, description="Client secret")
    code = graphene.String(required=True, description="Authorization code")

    @classmethod
    def trafaret(cls) -> Trafaret:
        """Template init."""
        return T.Dict(
            {
                T.Key("client_id"): T.String(allow_blank=False),
                T.Key("client_secret"): T.String(allow_blank=False),
                T.Key("code"): T.String(allow_blank=False),
            }
        )


class AuthorizationCode(graphene.Mutation):
    """Mutation to get OAuth2 authorization code for given order."""

    class Input:
        """Mutation input description."""

        input = graphene.Argument(  # noqa A003
            AuthorizationCodeInput, required=True
        )

    redirect_uri = graphene.String(required=False)
    code = graphene.String(required=False)

    @authorized_only
    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
        _user: User,
    ) -> dict:
        """Mutation resolver."""
        _input = input.copy()
        data = await AuthorizationCodeInput.validate(_input)
        application_id = data.get("application_id")
        dream_id = data.get("dream_id")

        exists = await DatabaseHelper.scalar(
            info,
            sa.exists(
                sa.select([application.c.id]).where(
                    application.c.id == application_id
                )
            ).select(),
        )
        if not exists:
            language_service = app_from_info(
                info
            ).localization_container.service()
            error = await language_service.get_error_text(
                "id_not_exist", request_var.get()["language"]
            )
            raise RuntimeError(error)
        redirect_uri = (
            await DatabaseHelper.scalar(
                info,
                query=sa.select(
                    [application.c.redirect_uri],
                    application.c.id == application_id,
                ),
            )
        ) + "?"

        if dream_id:
            page = data.get("page")
            redirect_uri = f"{redirect_uri}dream_id={dream_id}&page={page}"
        redirect_uri = get_ru_url(redirect_uri, _user.country_id)

        code = token_urlsafe(nbytes=150)
        auth_code_data = {
            "application_id": application_id,
            "user_id": _user.id,
            "code": prepare_token(info, code),
            "is_used": False,
            "expires_at": datetime.utcnow() + timedelta(minutes=5),
        }

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(info)) as _tx:
            await _tx.connection.status(
                oauth2_authorization_code.delete().where(
                    sa.and_(
                        oauth2_authorization_code.c.user_id == _user.id,
                        oauth2_authorization_code.c.application_id
                        == application_id,
                    )
                )
            )
            await _tx.connection.status(
                oauth2_authorization_code.insert().values(
                    **auth_code_data,
                )
            )
            return {
                "code": code,
                "redirect_uri": f"{redirect_uri}{'' if redirect_uri.endswith('?') else '&'}auth_code={code}",
            }


class AuthorizationToken(graphene.Mutation):
    """Mutation to get OAuth2 authorization token for given code."""

    class Input:
        """Mutation input description."""

        input = graphene.Argument(  # noqa A003
            AuthorizationTokenInput, required=True
        )

    token = graphene.String(required=True)

    async def mutate(
        self,
        info: ResolveInfo,
        input: Dict,  # noqa A002
    ) -> Dict:
        """Mutation resolver."""
        _input = input.copy()
        data = await AuthorizationTokenInput.validate(_input)
        client_id = data.get("client_id")
        client_secret = data.get("client_secret")
        code = data.get("code")
        language_service = app_from_info(info).localization_container.service()

        client_secret_hash = await DatabaseHelper.scalar(
            info,
            query=sa.select(
                [application.c.oauth2_client_secret],
                application.c.oauth2_client_identifier == client_id,
            ),
        )
        if not client_secret_hash:
            raise RuntimeError(
                await language_service.get_error_text(
                    "invalid_auth", request_var.get()["language"]
                )
            )
        try:
            settings.HASHER.verify(client_secret_hash, client_secret)
        except VerifyMismatchError as error_exc:
            raise RuntimeError(
                await language_service.get_error_text(
                    "invalid_auth", request_var.get()["language"]
                )
            ) from error_exc
        auth_code_row = await DatabaseHelper.fetch_one(
            info,
            oauth2_authorization_code.select()
            .where(
                oauth2_authorization_code.c.code == prepare_token(info, code)
            )
            .where(oauth2_authorization_code.c.expires_at > datetime.utcnow()),
        )
        if not auth_code_row:
            raise RuntimeError(
                await language_service.get_error_text(
                    "invalid_auth", request_var.get()["language"]
                )
            )
        if auth_code_row.is_used:
            _tx: GinoTransaction
            async with (await DatabaseHelper.transaction(info)) as _tx:
                conn = _tx.connection
                await conn.status(
                    oauth2_token.update()
                    .values(is_revoked=True)
                    .where(
                        sa.and_(
                            oauth2_token.c.user_id == auth_code_row.user_id,
                            oauth2_token.c.application_id
                            == auth_code_row.application_id,
                        )
                    )
                )

            raise RuntimeError(
                await language_service.get_error_text(
                    "invalid_auth", request_var.get()["language"]
                )
            )

        token = token_urlsafe(nbytes=150)
        _tx: GinoTransaction
        auth_token_data = {
            "user_id": auth_code_row.user_id,
            "application_id": auth_code_row.application_id,
            "token": prepare_token(info, token),
            "is_revoked": False,
            "issued_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7),
        }
        async with (await DatabaseHelper.transaction(info)) as _tx:
            conn = _tx.connection

            await conn.status(
                oauth2_token.insert().values(
                    **auth_token_data,
                )
            )
            await conn.status(
                oauth2_authorization_code.update()
                .values(is_used=True)
                .where(
                    oauth2_authorization_code.c.code
                    == prepare_token(info, code)
                )
            )

            return {"token": token}


class ApplicationPublicMutation(graphene.ObjectType):
    """Applications related public mutations."""

    authorization_code = AuthorizationCode.Field()
    application_token = AuthorizationToken.Field()
