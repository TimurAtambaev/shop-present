"""Модуль с представлением регистрации и сброса пароля."""
import asyncio
import json
from datetime import datetime, timedelta

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from localization.service import LanguageService
from sqlalchemy import and_
from starlette import status
from starlette.responses import Response

from dataset.config import settings
from dataset.core.auth import create_reset_token
from dataset.core.container import Container
from dataset.core.mail.utils import send_mail
from dataset.graphql_.user.utils import is_email_exists
from dataset.mail_templates import (
    EmailConfirmationTemplate,
    PasswordChangedTemplate,
)
from dataset.middlewares import request_var
from dataset.rest.models.auth_reg import Registration
from dataset.rest.models.profile import ProfileResetPassword
from dataset.rest.views.base import BaseView, JWTView
from dataset.rest.views.utils import email_validate
from dataset.tables.country import CountryManager
from dataset.tables.user import User

router = InferringRouter()


@cbv(router)
class Registration(BaseView):
    """Представление регистрации."""

    @router.post("/registration", responses={200: {}})
    @inject
    async def register(
        self,
        reg_data: Registration,
        language_service: LanguageService = Depends(  # noqa: B008
            Provide[Container.localization.service]
        ),
    ):  # noqa: ANN201
        """Зарегистрировать пользователя."""
        email = reg_data.email = reg_data.email.lower()
        email_validate(email)
        if await is_email_exists(email):
            error = await language_service.get_error_text(
                "email_exist", request_var.get()["language"]
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error
            )
        redis = self.request.app.state.redis
        attempts = await redis.keys(f"{email}*")
        if len(attempts) >= settings.NUMBER_OF_ATTEMPTS:
            attempts_interval = timedelta(hours=settings.HOURS_TO_ATTEMPTS)
            first_attempt_time = min(
                [
                    datetime.fromisoformat(await redis.get(key))
                    for key in attempts
                ]
            )
            hours_to_next_attempt = str(
                (attempts_interval - (datetime.now() - first_attempt_time))
            )
            hours_to_next_attempt = (
                hours_to_next_attempt[0]
                if hours_to_next_attempt[1] == ":"
                else hours_to_next_attempt[:2]
            )
            return Response(
                status_code=status.HTTP_403_FORBIDDEN,
                content=hours_to_next_attempt,
            )
        data = reg_data.dict()

        if data.get("is_female"):
            data["is_female"] = data.pop("is_female")

        is_offer_acceptance_status = data.pop("is_offer_acceptance_status")

        (
            data["reset_token"],
            data["reset_token_valid_till"],
        ) = create_reset_token()
        lang = data["language"] = self.request["language"]
        data["currency_id"] = settings.EURO_ID
        if data.get("password") != data.pop("password_repeat"):
            error = await language_service.get_error_text(
                "password_mismatch", lang
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error
            )

        data["password"] = settings.HASHER.hash(data.pop("password"))

        try:
            assert (
                await CountryManager.get_by_id(
                    self.request.app, data.get("country")
                )
            ).get("is_active")

            data["country_id"] = data.pop("country")
        except AssertionError as error_exc:
            error = await language_service.get_error_text(
                "invalid_country", lang
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error
            ) from error_exc

        if not data.pop("is_age_offer_acceptance_status"):
            error = await language_service.get_error_text("not_18", lang)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error
            )

        if not is_offer_acceptance_status:
            error = await language_service.get_error_text(
                "terms_and_conditions", lang
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error
            )

        del data["re_token"]
        data["reset_token_valid_till"] = None

        #  Сохраняем в редисе попытку регистрации и время пыпытки
        await redis.setex(
            f"{email}_{data['reset_token']}",
            settings.RESET_LIFETIME,
            str(datetime.now()),
        )
        #  Сохраняем в редисе введенные при регистрации данные пользователя с
        #  привязкой к токену, который отправляется в ссылке в письме
        await redis.setex(
            data["reset_token"], settings.RESET_LIFETIME, json.dumps(data)
        )
        asyncio.create_task(
            send_mail(
                email,
                EmailConfirmationTemplate(
                    self.request.app,
                    email=email,
                    name=data["name"],
                    reset_token=data.get("reset_token"),
                ),
                lang,
            )
        )
        return Response(status_code=status.HTTP_200_OK)


@cbv(router)
class ResetPassword(JWTView):
    """Представление сброса и обновления пароля."""

    @router.post("/new-password")
    async def reset_password(self, info: ProfileResetPassword) -> dict:
        """Сбросить пароль пользователя, сохранить новый пароль."""
        user = await User.query.where(
            and_(
                User.reset_token == info.reset_token,
                User.reset_token_valid_till >= datetime.utcnow(),
            )
        ).gino.first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expired_reset_token",
            )
        try:
            await user.update(
                password=settings.HASHER.hash(info.password)
            ).apply()
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=err
            )
        tokens = await self.get_pair_token_response(user)
        asyncio.create_task(
            send_mail(
                user.verified_email,
                PasswordChangedTemplate(
                    self.request.app, name=user.name, email=user.verified_email
                ),
                user.language,
            )
        )
        return tokens  # noqa R504
