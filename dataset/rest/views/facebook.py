"""Модуль с представлениями для интеграции с фб."""
import uuid

from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from gino import GinoConnection
from gino.transaction import GinoTransaction
from loguru import logger
from sqlalchemy.engine import RowProxy
from starlette.responses import Response
from starlette.status import HTTP_404_NOT_FOUND

from dataset.config import settings
from dataset.core.graphql import DatabaseHelper
from dataset.rest.models.auth_reg import TokenPair
from dataset.rest.models.facebook import (
    FacebookModel,
    FacebookRegistrationModel,
)
from dataset.rest.views.base import BaseFacebookAuth
from dataset.tables.user import User

router = InferringRouter()


@cbv(router)
class FacebookAuth(BaseFacebookAuth):
    """Представление авторизации через FB."""

    @router.post(
        "/fb/auth",
        responses={404: {"404": "User not found"}, 200: {"200": TokenPair}},
    )
    async def post(self, fb_data: FacebookModel):  # noqa ANN201
        """Запрос на авторизацию из FB."""
        try:
            return await self.integrate(fb_data)
        except Exception as err:
            logger.error(err)  # noqa: G200
            raise err

    async def handle(self, db_user: RowProxy, user_data):  # noqa ANN201
        """Отработать сценарий авторизации."""
        if not db_user:
            return Response(status_code=HTTP_404_NOT_FOUND)
        if not db_user.fb_id:
            await self.link_fb_with_user(db_user.id, int(user_data.get("id")))
            return Response(status_code=HTTP_404_NOT_FOUND)
        return await self.get_pair_token_response(db_user)


@cbv(router)
class RegistrationFacebookAuth(BaseFacebookAuth):
    """Представление регистрации через FB."""

    @router.post("/fb/register", response_model=TokenPair)
    async def post_facebook(
        self, fb_data: FacebookRegistrationModel
    ):  # noqa ANN201
        """Запрос на регистрацию через FB."""
        try:
            return await self.integrate(fb_data)
        except Exception as err:
            logger.error(err)  # noqa: G200
            raise err

    async def handle(self, db_user: RowProxy, user_data: dict):  # noqa ANN201
        """Отработать сценарий регистрации."""
        try:
            if not db_user:
                await self.create_user(user_data)
                db_user = await User.query.where(
                    User.fb_id == int(user_data.get("id"))
                ).gino.first()
            return await self.get_pair_token_response(db_user)
        except Exception as err:
            logger.error(err)  # noqa: G200
            raise err

    async def create_user(self, user_data: dict) -> None:
        """Создать пользователя."""
        try:
            avatar = user_data["picture"]["data"]["url"]
        except KeyError:
            avatar = None
        data = {
            "verified_email": user_data.get("email"),
            "name": user_data.get("first_name"),
            "surname": user_data.get("last_name"),
            "avatar": avatar,
            "fb_id": int(user_data.get("id")),
            "password": uuid.uuid4().hex,
            "currency_id": settings.EURO_ID,
        }
        try:
            transaction = await DatabaseHelper.transaction(self.request.app)
            transact: GinoTransaction
            async with transaction as transact:
                conn: GinoConnection = transact.connection
                await conn.status(User.insert().values(**data))
        except Exception as err:
            logger.error(err)  # noqa: G200
            raise err
