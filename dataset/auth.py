"""App authorization handlers (middlewares)."""
import re
from datetime import datetime
from typing import Dict, Optional, Union
from urllib.parse import ParseResult, urlparse

import jwt as pyjwt
import sqlalchemy as sa
from fastapi import Request
from gino import NoResultFound
from loguru import logger
from starlette import status
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
)
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket

from dataset.config import settings
from dataset.core.auth import (
    prepare_token_from_app,
    read_jwt_token,
    read_token,
)
from dataset.exceptions import BlacklistedError
from dataset.routes import (
    ADMIN_URL_PATTERN,
    GQL_PUBLIC_URL_PATTERN,
    REST_ADMIN_URL,
    REST_PUBLIC_URL_PATTERN,
    USERS_EXPORT_URL,
)
from dataset.tables.application import application, oauth2_token
from dataset.tables.operator import Operator
from dataset.tables.user import User


def unauthorized_response() -> JSONResponse:
    """Get prebuilt unauthorized response object."""
    return JSONResponse(
        {"errors": [{"message": "Unauthorized"}]},
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


async def verify_token(
    request: Request, table: sa.table, token: str = None
) -> Optional[Dict[str, any]]:
    """Сheck JWT token and return it's payload.

    if it presents in request header. Otherwise returns None.
    """
    # TODO блокировать протухший токен
    try:
        payload = await read_jwt_token(request, token=token)
    except (pyjwt.DecodeError, BlacklistedError) as error:
        raise PermissionError from error

    user_id = int(payload.get("ufandao_id"))
    if user_id is None:
        raise PermissionError

    user = await table.query.where(table.id == user_id).gino.first()
    if not user:
        raise PermissionError

    secret_key = settings.JWT_KEY
    if payload["iss"] == "imrix":
        secret_key = settings.JWT_IMRIX_KEY
    try:
        payload = await read_jwt_token(request, token=token, key=secret_key)
    except pyjwt.DecodeError as error:
        logger.error(error)  # noqa G200
        raise PermissionError from error
    return payload  # noqa R504


async def authorize_user(
    request: Union[Request, WebSocket], token: str = None
):  # noqa ANN201
    """Авторизовать пользователя в запрос."""
    payload = await verify_token(request, User, token)
    assert payload is not None

    user_id = int(payload.get("ufandao_id"))
    expires = payload.get("exp")

    if not user_id or not expires or expires <= datetime.utcnow():
        return unauthorized_response()

    app_user = await (
        User.query.where(sa.and_(User.id == user_id, User.is_active))
    ).gino.first()
    if not app_user:
        raise NoResultFound

    return app_user


class BasicAuthBackend(AuthenticationBackend):
    """Basic auth backend."""

    async def authenticate(self, request: Request) -> tuple:
        """Authenticate."""
        handlers = (
            self.validate_ws_user_auth,
            self.validate_operator_auth,
            self.validate_user_auth,
            self.validate_application_auth,
        )
        for handle in handlers:
            user = await handle(request)
            if user:
                break

        scope = "authenticated" if user else "not_authenticated"
        return AuthCredentials([scope]), user

    async def validate_ws_user_auth(self, websocket: WebSocket) -> None:
        """Validate user auth."""
        if not websocket.scope["type"] == "websocket":  # noqa SIM201
            return None
        token = websocket.query_params.get("ws_token")
        try:
            return await authorize_user(websocket, token=token)
        except AssertionError:
            return None
        except (IndexError, PermissionError):
            raise AuthenticationError("Invalid basic auth credentials1")

    async def validate_user_auth(self, request: Request) -> None:
        """Validate user's access token in header and assings user to request.

        Throws 401 error if invalid access token provided or user couldn't be
        found.
        """
        url: ParseResult = urlparse(str(request.url))

        if not any(
            (
                re.match(GQL_PUBLIC_URL_PATTERN, url.path),
                re.match(REST_PUBLIC_URL_PATTERN, url.path),
            )
        ) or url.path in [
            request.app.url_path_for("user_refresh"),
            request.app.url_path_for("get_exchange_rate"),
        ]:
            return None
        try:
            return await authorize_user(request)
        except AssertionError:
            return None
        except PermissionError:
            raise AuthenticationError("Invalid basic auth credentials2")

    async def validate_operator_auth(
        self, request: Request
    ) -> Optional[Operator]:
        """Validate operator's access token in header.

        And assings user to request.
        Throws 401 error if invalid access token provided or user couldn't be
        found.
        """
        url: ParseResult = urlparse(str(request.url))

        try:
            payload = await read_jwt_token(request)
        except Exception:
            payload = {}

        if (
            not payload.get("is_operator")
            and (
                ADMIN_URL_PATTERN.match(url.path) is None
                and USERS_EXPORT_URL not in url.path
                and REST_ADMIN_URL.match(url.path) is None
            )
            or (
                USERS_EXPORT_URL in url.path
                and request.scope["method"] == "OPTIONS"
            )
            or request.app.url_path_for("operator_refresh") == url.path
        ):
            return None

        try:
            payload = await verify_token(request, Operator)
            assert payload is not None
        except AssertionError:
            return None
        except PermissionError:
            raise AuthenticationError("Invalid basic auth credentials3")

        user_id = payload.get("ufandao_id")
        expires = payload.get("exp")

        if not user_id or not expires or expires <= datetime.utcnow():
            raise AuthenticationError("Invalid basic auth credentials4")

        app_user = await Operator.query.where(
            sa.and_(
                Operator.id == user_id, Operator.is_active == True  # noqa E712
            )
        ).gino.first()
        if not app_user:
            raise AuthenticationError("Invalid basic auth credentials5")
        return app_user

    async def validate_application_auth(
        self, request: Request
    ) -> Optional[User]:
        """
        Validate access token in header and assings order to request.

        Throws 401 error if invalid access token provided
        or application couldn't be found.
        """
        engine = request.app.state.db
        url: ParseResult = urlparse(str(request.url))

        url_pattern = re.compile(GQL_PUBLIC_URL_PATTERN)
        if re.match(url_pattern, url.path) is None:
            return None
        try:
            token = read_token(request, "BEARER")
        except AssertionError:
            return None
        try:
            token_row = await engine.one(
                oauth2_token.select()
                .where(oauth2_token.c.token == prepare_token_from_app(token))
                .where(oauth2_token.c.is_revoked == False)  # noqa E712
                .where(oauth2_token.c.expires_at > sa.func.now())
            )

            application_ = await engine.one(
                application.select().where(
                    application.c.id == token_row.application_id
                )
            )

            user_ = await User.query.where(
                sa.and_(User.id == token_row.user_id, User.is_active)
            ).gino.first()

            request.app.state.application = application_
            return user_  # noqa R504
        except NoResultFound:
            raise AuthenticationError("Invalid basic auth credentials6")
