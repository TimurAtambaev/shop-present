"""Модуль c тестовыми роутами."""
from datetime import datetime

from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from pydantic import BaseModel
from sqlalchemy import and_
from starlette import status
from starlette.responses import Response

from dataset.migrations import db
from dataset.rest.views.achievement import create_achievement
from dataset.rest.views.base import BaseView
from dataset.rest.views.utils import receive_achievement
from dataset.tables.dream import Dream, DreamStatus
from dataset.tables.user import User

router = InferringRouter()


class UserUnsubscribe(BaseModel):
    """Модель обновленного юзера."""

    id: int  # noqa A003
    paid_till: datetime


# TODO удалить после теста
@cbv(router)
class TestDreamView(BaseView):
    """Представление для с роутами для теста мечт."""

    async def change_dream_status(
        self, dream_id: int, from_: int, to: int
    ) -> None:
        """Сменить  статус у мечты."""
        await (
            Dream.update.values(status=to)
            .where(and_(Dream.id == dream_id, Dream.status == from_))
            .gino.status()
        )

    @router.get("/skip-2-4-dream-part")
    async def skip_2_4_part(self, dream_id: int) -> None:
        """Пропустить этап 2/4."""
        async with db.transaction():
            await self.change_dream_status(
                dream_id,
                DreamStatus.HALF.value,
                DreamStatus.THREE_QUARTERS.value,
            )

    @router.get("/skip-4-4-dream-part")
    async def skip_4_4_part(self, dream_id: int) -> None:
        """Пропустить этап 4/4."""
        async with db.transaction():
            await self.change_dream_status(
                dream_id, DreamStatus.WHOLE.value, DreamStatus.ACTIVE.value
            )

    @router.post("/change-count")
    async def change_count(self, user_id: int, count: int) -> None:
        """Установить конкретное кол-во refer_count для пользователя."""
        async with db.transaction():
            await (
                User.update.values(refer_count=count)
                .where(User.id == user_id)
                .gino.status()
            )
            user = await User.query.where(User.id == user_id).gino.first()

            await create_achievement(user.id)
            await receive_achievement(self.request.app.state.redis, user)

    @router.post("/unsubscribed-user")
    async def change_user_status(self, data: UserUnsubscribe):  # noqa ANN201
        """Сбросить оплаченную подписку у пользователя."""
        user = await User.query.where(User.id == data.id).gino.first()
        if user:
            await user.update(paid_till=data.paid_till).apply()
        return Response(status_code=status.HTTP_200_OK)
