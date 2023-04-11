"""Модуль с базовыми представлениями."""
import os
from datetime import datetime
from typing import Union

import jwt as pyjwt
import sqlalchemy as sa
from argon2.exceptions import VerifyMismatchError
from facebook_business import FacebookAdsApi, FacebookSession
from facebook_business.adobjects.user import User
from facebook_business.exceptions import FacebookRequestError
from fastapi import HTTPException, Request
from gino import GinoConnection
from gino.transaction import GinoTransaction
from jwt import PyJWTError
from sqlalchemy.engine import RowProxy
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_400_BAD_REQUEST

from dataset.config import settings
from dataset.core.auth import check_token_blacklist
from dataset.core.graphql import DatabaseHelper
from dataset.core.utils import jwt_decode
from dataset.exceptions import BlacklistedError, TokenGoneOffError
from dataset.migrations import db
from dataset.rest.models.facebook import FacebookModel
from dataset.rest.views.commento import add_commenter_session
from dataset.tables import user
from dataset.tables.operator import Operator
from dataset.tables.user import User as GinoUser
from dataset.tables.user import blacklist
from dataset.utils.tokens import create_token_pair


class BaseView:
    """Базовый класс представления."""

    request: Request
    response: Response


class JWTView(BaseView):
    """Базовое представление для выдачи и бана токенов."""

    request: Request
    response: Response

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        """Инициализация представления с классом пользователя/оператора."""
        from dataset.routes import REST_ADMIN_URL

        super().__init__(*args, **kwargs)
        self.user_cls = GinoUser
        if REST_ADMIN_URL.match(self.request.url.path) is not None:
            self.user_cls = Operator

    async def get_refresh_payload(self) -> dict:
        """Получить payload из refresh токена."""
        token = self.request.cookies.get("refresh", "")
        payload = await self.read_token(token)
        if not await self.validate_token(payload):
            raise HTTPException(status_code=400)

        return payload

    async def read_token(self, token: str) -> dict:
        """Прочитать данные из токена."""
        # TODO переделать
        try:
            payload = jwt_decode(token, key="", verify=False)
        except PyJWTError:
            raise HTTPException(status_code=400, detail="Invalid token")
        active_user = await self.get_active_user_by_id(payload["ufandao_id"])
        if not active_user:
            raise HTTPException(status_code=404)

        key = settings.JWT_KEY

        pyjwt.decode(token, key=key, verify=bool(key))

        return {**payload, "token": token}

    async def validate_token(self, payload: dict) -> bool:
        """Провалидировать токен."""
        try:
            if payload["exp"] < datetime.utcnow():
                raise TokenGoneOffError
            exist = await check_token_blacklist(
                self.request.app, payload["jti"]
            )
            if exist:
                raise BlacklistedError
        except (TokenGoneOffError, BlacklistedError):
            return False

        return True

    async def ban_token(self, jti: str) -> None:
        """Забанить токен."""
        transaction = await DatabaseHelper.transaction(self.request.app)
        transact: GinoTransaction
        async with transaction as transact:
            conn: GinoConnection = transact.connection
            await conn.status(blacklist.insert().values(jti=jti))

    async def get_active_user_by_creds(
        self,
        username: str,
        password: str,
    ) -> Union[GinoUser, Operator]:
        """Получить пользователя по логину/паролю."""
        query = self.user_cls.query.where(
            self.user_cls.is_active == True  # noqa E712
        )
        if self.user_cls == GinoUser:
            query = query.where(
                self.user_cls.verified_email == sa.func.lower(username)
            )
        elif self.user_cls == Operator:
            query = query.where(self.user_cls.email == sa.func.lower(username))
        active_user = await query.gino.first()
        try:
            if active_user is None:
                raise VerifyMismatchError()
            settings.HASHER.verify(active_user.password, password)
        except VerifyMismatchError:
            raise VerifyMismatchError("Wrong credentials")

        return active_user

    async def get_active_user_by_id(
        self, user_id: int
    ) -> Union[GinoUser, Operator]:
        """Получить пользователя по логину."""
        return await (
            self.user_cls.query.where(self.user_cls.id == user_id).where(
                self.user_cls.is_active == True  # noqa E712
            )
        ).gino.first()

    async def get_pair_token_response(
        self, active_user: user, refresh: bool = False
    ) -> dict:
        """Получить ответ с токенами."""
        access_token, refresh_token = create_token_pair(active_user)
        self.response.set_cookie(
            "refresh",
            refresh_token,
            httponly=True,
            secure=settings.GS_ENVIRONMENT == "prod",
            samesite=None,
            max_age=settings.REFRESH_LIFETIME,
        )
        commentertoken = await add_commenter_session(active_user, refresh)
        return {
            "access": access_token,
            "refresh": refresh_token,
            "commentoCommenterToken": commentertoken,
        }


class BaseFacebookAuth(JWTView):
    """Базовое представление интеграции с фб."""

    app_id = os.getenv("FB_APP_ID", "262720925652539")
    app_secret = os.getenv("FB_APP_SECRET", "0a2a0453e728c0359d47b027a7e6853d")

    async def integrate(self, fb_data: FacebookModel):  # noqa ANN201
        """Запустить интеграцию с фб."""
        session = FacebookSession(
            app_id=self.app_id,
            app_secret=self.app_secret,
            access_token=fb_data.token,
        )
        api = FacebookAdsApi(session)
        fb_user = User(fbid="me", api=api)
        try:
            user_data = fb_user.api_get(
                fields=[
                    User.Field.first_name,
                    User.Field.last_name,
                    User.Field.email,
                    "picture",
                ]
            )
        except FacebookRequestError as error:
            return JSONResponse(
                {"error": error.body()}, status_code=HTTP_400_BAD_REQUEST
            )
        data = user_data.export_all_data()

        db_user = await self.get_active_user_by_creds(
            int(data.get("id")), data.get("email", "")
        )

        return await self.handle(db_user, data)

    async def handle(self, db_user: RowProxy, user_data: dict) -> None:
        """Обработать данные в зависимости от сценария представления."""
        raise NotImplementedError

    async def get_active_user_by_creds(
        self, fb_id: int, email: str
    ) -> RowProxy:
        """Получить пользователя по почте или фб id."""
        user_obj = await GinoUser.query.where(
            GinoUser.verified_email == email
        ).gino.first()

        fb_linked = await GinoUser.query.where(
            GinoUser.fb_id == fb_id
        ).gino.first()

        return fb_linked or user_obj

    async def link_fb_with_user(self, user_id: str, fb_id: int) -> None:
        """Связать аккаунт накометы с фб."""
        async with db.transaction():
            await GinoUser.update.values(fb_id=fb_id).where(
                GinoUser.id == user_id
            ).gino.status()
