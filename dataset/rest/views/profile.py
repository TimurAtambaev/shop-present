"""Модуль для редактирования настроек профиля."""
import asyncio
from typing import Optional

from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import and_
from starlette import status
from starlette.responses import Response

from dataset.config import settings
from dataset.core.mail.utils import send_mail
from dataset.mail_templates import (
    PasswordChangedTemplate,
    ShareReferLinkTemplate,
)
from dataset.rest.models.profile import (
    LanguageModel,
    ProfileChangePassword,
    ProfileInfo,
    ProfileModel,
)
from dataset.rest.models.referal import EmailReferal
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.commento import update_commenter
from dataset.rest.views.utils import email_validate
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.user import User

router = InferringRouter()


async def get_active_dream_info(user_id: int) -> bool:
    """Получить информацию о наличии активной мечты у пользователя."""
    return bool(
        await Dream.query.where(
            and_(
                Dream.user_id == user_id,
                Dream.status == DreamStatus.ACTIVE.value,
            )
        )
        .with_only_columns((Dream.id,))
        .gino.first()
    )


@cbv(router)
class ProfileView(BaseView):
    """Представление для работы с настройками."""

    @router.patch(
        "/profile-change", dependencies=[Depends(AuthChecker(is_auth=True))]
    )
    async def profile_change(
        self, info: ProfileModel = Depends(ProfileModel.as_form)  # noqa B008
    ):  # noqa ANN201
        """Запрос на изменение личных данных пользователя."""
        (
            await User.update.values(**info.dict())
            .where(User.id == self.request.user.id)
            .gino.status()
        )
        user = await User.get(self.request.user.id)
        await update_commenter(user)

        return Response(status_code=status.HTTP_200_OK)

    @router.patch(
        "/password-change", dependencies=[Depends(AuthChecker(is_auth=True))]
    )
    async def password_change(
        self,
        info: ProfileChangePassword,
    ):  # noqa ANN201
        """Запрос на изменение пароля пользователя."""
        user = self.request.user
        try:
            old_pass_is_valid = settings.HASHER.verify(
                user.password, info.old_password
            )
        except VerifyMismatchError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        if old_pass_is_valid and info.password == info.password_repeat:
            (
                await User.update.values(
                    password=settings.HASHER.hash(info.password)
                )
                .where(User.id == user.id)
                .gino.status()
            )
            asyncio.create_task(
                send_mail(
                    user.email,
                    PasswordChangedTemplate(
                        self.request.app,
                        name=user.name,
                        email=user.verified_email,
                    ),
                    user.language,
                )
            )

    @router.get(
        "/profile",
        response_model=ProfileInfo,
        dependencies=[Depends(AuthChecker(is_auth=True))],
    )
    async def get_profile_info(self) -> ProfileInfo:
        """Запрос на получение данных профиля."""
        return ProfileInfo(
            **self.request.user.to_dict(),
            has_active_dream=await get_active_dream_info(self.request.user.id),
        )

    @router.post(
        "/email-refer", dependencies=[Depends(AuthChecker(is_auth=True))]
    )
    async def simple_send(self, email: EmailReferal) -> None:
        """Запрос на отправление реферального кода."""
        email_validate(email.email)
        sender = self.request.user
        asyncio.create_task(
            send_mail(
                email.email,
                ShareReferLinkTemplate(
                    self.request.app,
                    refer_code=sender.refer_code,
                    name=sender.name,
                    email=email.email,
                ),
                sender.language,
            )
        )

    @router.post("/change-language")
    async def change_language(self, lang: LanguageModel) -> Optional[dict]:
        """Change user language."""
        if self.request.user:
            await self.request.user.update(language=lang.language).apply()

        self.response.set_cookie("language", lang.language)
        return {"result": True}
