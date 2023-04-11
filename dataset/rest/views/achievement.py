"""Запрос на список достижений."""
from typing import List, Sequence

from fastapi import Depends
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter

from dataset.migrations import db
from dataset.rest.models.achievement import ResponseAchievementModel
from dataset.rest.permissions import AuthChecker
from dataset.rest.views.base import BaseView
from dataset.tables.achievement import (
    DESCRIPTIONS,
    NAMES,
    Achievement,
    AchievementType,
)

router = InferringRouter()


async def create_achievement(user_id: int) -> Sequence[Achievement]:
    """Создать достижение."""
    my_achievement = (
        await Achievement.query.where(Achievement.user_id == user_id)
        .order_by(Achievement.id.asc())
        .gino.all()
    )
    if my_achievement:
        return my_achievement
    types = [
        AchievementType.UFANDAO_MEMBER,
        AchievementType.UFANDAO_FRIEND,
        AchievementType.UFANDAO_FUNDRAISER,
        AchievementType.TOP_FUNDRAISER,
        AchievementType.DREAM_MAKER,
    ]

    my_achievement = []
    async with db.transaction():
        for type_name in types:
            achievement = await Achievement.create(
                user_id=user_id,
                title=NAMES.get(type_name.value),
                description=DESCRIPTIONS.get(type_name.value),
                type_name=type_name.value,
            )
            my_achievement.append(achievement)

    return my_achievement


@cbv(router)
class AchievementView(BaseView):
    """Запрос на список достижений."""

    @router.get(
        "/achievements/my",
        dependencies=[Depends(AuthChecker(is_auth=True))],
        response_model=List[ResponseAchievementModel],
    )
    async def achievement_list(self) -> Sequence[Achievement]:
        """Получить список достижений."""
        return await create_achievement(self.request.user.id)
