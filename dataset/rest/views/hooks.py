"""Хука добавления поля imrix_id в модель пользователя."""
from asyncpg import UniqueViolationError
from fastapi import HTTPException
from fastapi.params import Depends
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from starlette import status
from starlette.responses import Response

from dataset.config import settings
from dataset.migrations import db
from dataset.rest.models.hooks import UserUpdate
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.rest.views.utils import recount_refs, refresh_dreams_view
from dataset.tables.user import User
from dataset.utils.hooks import create_user_refer_code, update_dream_status

router = InferringRouter()


@cbv(router)
class ImrixId(BaseView):
    """Добавление поля imrix_id в модель пользователя."""

    @router.post(
        "/update-user", dependencies=[Depends(AuthChecker(is_auth=True))]
    )
    async def user_imrix_id(self, user_data: UserUpdate):  # noqa ANN201
        """Добавление imrix_id, реферального токена пользователя."""
        user = self.request.user
        await self.update_imrix_id(user_data)

        async with db.transaction():
            if user.referer and not user.refer_code:
                await recount_refs(self.request.app.state.redis, user.referer)

            if user_data.user_valid_till or user_data.user_trial_till:
                await update_dream_status(self.request.app.state.redis, user)
                await create_user_refer_code(self.request.app, user)

            if user_data.user_valid_till:
                await self.update_user_valid_till(user_data)

            if user_data.user_trial_till:
                await self.update_user_trial_till(user_data)

        await refresh_dreams_view()

        return Response(status_code=status.HTTP_201_CREATED)

    async def update_user_valid_till(self, user_data: UserUpdate) -> None:
        """Функция добавления user_valid_till для пользователя."""
        await (
            User.update.values(paid_till=user_data.user_valid_till)
            .where(User.id == self.request.user.id)
            .gino.status()
        )

    async def update_user_trial_till(self, user_data: UserUpdate) -> None:
        """Функция добавления trial_till для пользователя."""
        await (
            User.update.values(trial_till=user_data.user_trial_till)
            .where(User.id == self.request.user.id)
            .gino.status()
        )

    async def update_imrix_id(self, user_data: UserUpdate) -> None:
        """Функция добавления imrix_id для существующего пользователя."""
        try:
            await (
                User.update.values(imrix_id=user_data.imrix_id)
                .where(User.id == self.request.user.id)
                .gino.status()
            )
        except UniqueViolationError:
            raise HTTPException(status.HTTP_403_FORBIDDEN)


class ConvertDisplay(int):
    """Перевод финансовых полей в реальный размер для отображения."""

    @classmethod
    def __get_validators__(cls) -> int:
        """Получить валидаторы."""
        yield cls.conversion

    @classmethod
    def conversion(cls, v: int) -> int:
        """Конвертировать поле для отображения."""
        return v / settings.FINANCE_RATIO


class ConvertOperation(int):
    """Перевод финансовых полей в размер x100 для операций и хранения в БД."""

    @classmethod
    def __get_validators__(cls) -> int:
        """Получить валидаторы."""
        yield cls.conversion

    @classmethod
    def conversion(cls, v: int) -> int:
        """Конвертировать поле для хранения и операций."""
        return cls(float(v) * settings.FINANCE_RATIO)
