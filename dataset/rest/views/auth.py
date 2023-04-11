"""Модуль с рест авторизацией."""
import json
from typing import Type, Union

import sqlalchemy as sa
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Response
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from gino.transaction import GinoTransaction
from starlette import status

from dataset.config import settings
from dataset.core.auth import prepare_token_from_app
from dataset.core.graphql import DatabaseHelper
from dataset.core.log import LOGGER
from dataset.rest.models.auth_reg import (
    AdminAuth,
    Auth,
    ConfirmToken,
    TokenPair,
)
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import JWTView
from dataset.rest.views.commento import (
    add_commenter_session,
    delete_commenter_session,
)
from dataset.tables.application import oauth2_token
from dataset.tables.operator import Operator
from dataset.tables.user import User
from dataset.utils.tokens import create_token_pair

router = InferringRouter()


@cbv(router)
class TokenObtainPairView(JWTView):
    """Представление для получения пары токенов."""

    @router.get("/admin-auth")
    async def admin_auth(self, token: str) -> dict:
        """Авторизоваться из админки под пользователем."""
        token_row = await DatabaseHelper.fetch_one(
            self.request.app,
            oauth2_token.select()
            .where(oauth2_token.c.token == prepare_token_from_app(token))
            .where(oauth2_token.c.is_revoked == False)  # noqa E712
            .where(oauth2_token.c.expires_at > sa.func.now()),
        )

        if not token_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token not found",
            )

        choosen_user = await User.get(token_row.user_id)

        if not choosen_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found",
            )

        _tx: GinoTransaction
        async with (await DatabaseHelper.transaction(self.request.app)) as _tx:
            try:
                await _tx.connection.status(
                    oauth2_token.delete().where(
                        oauth2_token.c.id == token_row.id
                    )
                )
            except Exception as error:
                LOGGER.error(error)  # noqa G200
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=error
                )

        access, refresh = create_token_pair(choosen_user)
        self.response.set_cookie(
            "refresh",
            refresh,
            httponly=True,
            secure=settings.GS_ENVIRONMENT == "prod",
            samesite=None,
            max_age=settings.REFRESH_LIFETIME,
        )
        commentertoken = await add_commenter_session(
            choosen_user, refresh=False
        )
        return {"token": access, "commentoCommenterToken": commentertoken}

    @router.post(
        "/token",
        responses={
            401: {"description": "Unauthorized"},
            200: {"model": TokenPair},
        },
    )
    async def user_obtain(self, auth_data: Auth) -> dict:
        """Запрос на получение пары токенов для пользователей."""
        return await self._obtain(auth_data)

    @router.post(
        "/admin/token",
        responses={
            401: {"description": "Unauthorized"},
            200: {"model": TokenPair},
        },
    )
    async def admin_obtain(self, auth_data: AdminAuth) -> dict:
        """Запрос на получение пары токенов для операторов."""
        return await self._obtain(auth_data)

    async def _obtain(self, auth_data: Union[Auth, AdminAuth]):  # noqa ANN201
        """Запрос на получение пары токенов и комментертокена."""
        try:
            active_user = await self.get_active_user_by_creds(
                auth_data.username, auth_data.password
            )
        except VerifyMismatchError:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        return await self.get_pair_token_response(active_user)

    @router.post(
        "/token/refresh", responses={400: {}}, response_model=TokenPair
    )
    async def user_refresh(self) -> dict:
        """Запрос на обновление пары токенов."""
        return await self._refresh(User)

    @router.post(
        "/admin/token/refresh", responses={400: {}}, response_model=TokenPair
    )
    async def operator_refresh(self) -> dict:
        """Запрос на обновление пары токенов."""
        return await self._refresh(Operator)

    async def _refresh(
        self, user_cls: Union[Type[User], Operator] = User
    ) -> dict:
        """Запрос на обновление пары токенов."""
        payload = await self.get_refresh_payload()
        return await self.refresh_token(payload, user_cls)

    async def refresh_token(
        self, payload: dict, user_cls: Union[User, Operator] = User
    ) -> dict:
        """Обновить пару токенов."""
        await self.ban_token(payload["jti"])
        await self.ban_token(payload["access_jti"])
        active_user = await self.get_active_user_by_id(payload["ufandao_id"])
        return await self.get_pair_token_response(active_user, refresh=True)

    @router.post(
        "/logout",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={200: {}},
    )
    async def user_logout(self) -> None:
        """Логаут юзера."""
        return await self.logout()

    @router.post(
        "/admin/logout",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        responses={200: {}},
    )
    async def operator_logout(self) -> None:
        """Логаут оператора."""
        return await self.logout()

    async def logout(self) -> None:
        """Запрос на логаут."""
        payload = await self.get_refresh_payload()
        active_user = await self.get_active_user_by_id(payload["ufandao_id"])
        if active_user:
            await delete_commenter_session(active_user)

        await self.ban_token(payload.get("jti", ""))
        await self.ban_token(payload.get("access_jti", ""))

    @router.post(
        "/first-auth",
        responses={
            401: {"description": "expired token"},
            200: {"model": TokenPair},
        },
    )
    async def user_confirm_reg_auth(
        self, auth_data: ConfirmToken
    ):  # noqa ANN201
        """Запрос на получение токенов для авторизации.

        После подтверждения регистрации.
        """
        user_data = await self.request.app.state.redis.get(auth_data.token)
        if not user_data:
            return Response(
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        user_data = json.loads(user_data)
        user = await User.query.where(
            User.verified_email == user_data["email"]
        ).gino.first()
        if not user:
            return Response(
                status_code=status.HTTP_404_NOT_FOUND, content="user not found"
            )

        return await self.get_pair_token_response(user)
