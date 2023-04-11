"""API category."""
from typing import List

import localization
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import and_

from dataset.config import settings
from dataset.rest.models.category import CategoryWithRndImage
from dataset.rest.views.base import BaseView
from dataset.tables.dream import Category

router = InferringRouter()


@cbv(router)
class CategoryView(BaseView):
    """Получение списка всех категорий."""

    @router.get("/category", response_model=List[CategoryWithRndImage])
    async def get_category(self) -> List:
        """Получение списка категорий."""
        lang_table = localization.get_language_table(self.request)
        return (
            await Category.join(
                lang_table, lang_table.c.title == Category.title_cat
            )
            .select()
            .where(
                and_(
                    lang_table.c.block == settings.CATEGORIES_BLOCK,
                    lang_table.c.lang == self.request["language"],
                )
            )
            .order_by(Category.id)
            .gino.load(
                Category.load(
                    id=Category.id,
                    image=Category.image,
                    title_cat=lang_table.c.value,
                )
            )
            .all()
        )
