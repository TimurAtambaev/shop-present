"""Модуль для работы с новостями."""
from datetime import datetime
from typing import List, Union

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Query
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.gino import paginate
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter
from sqlalchemy import func
from sqlalchemy.sql import Select
from starlette import status

from dataset.config import settings
from dataset.rest.models.news import NewsModel
from dataset.rest.views.base import BaseView
from dataset.tables.operator import Operator
from dataset.tables.post import Post

router = InferringRouter()


@cbv(router)
class NewsView(BaseView):
    """Представление для работы с новостями."""

    @router.get("/news", response_model=Page[NewsModel])
    async def get_news(
        self,
        tags: List[str] = Query(None),  # noqa B008
        is_published: bool = Query(None),  # noqa B008
        language: str = Query(None),  # noqa: B008
        params: Params = Depends(),  # noqa B008
    ) -> Union[AbstractPage, dict]:
        """Получение списка новостей."""
        query = Post.query.where(
            Post.published_date <= datetime.today().date()
        )
        where_language = self.request["language"]

        # проверяем наличие новостей до проверки оператора,
        #  иначе сломаем админку
        if not (await self._check_lang_news(query, where_language)):
            where_language = settings.DEFAULT_LANGUAGE

        if isinstance(self.request.user, Operator):
            query = Post.query
            where_language = language or where_language
        if tags:
            tags = tags.pop().split(",")
            query = query.where(Post.tags.contains(tags))
        if is_published is not None:
            query = query.where(Post.is_published == is_published)
        query = (
            query.where(Post.language == where_language)
            .order_by(Post.published_date.desc())
            .order_by(Post.created_at.desc())
        )
        return await paginate(query, params)

    @router.get("/news/{item_id}", response_model=NewsModel)
    async def get_news_id(self, item_id: int) -> Post:
        """Получить конкретную новость."""
        news_item = await Post.get(item_id)
        if (
            not news_item
            or not news_item.is_published
            or news_item.published_date > datetime.today().date()
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return news_item

    async def _check_lang_news(self, query: Select, language: str) -> bool:
        """Проверка наличия новостей на переданном языке."""
        query = query.where(
            sa.and_(
                Post.language == language,
                Post.published_date <= datetime.today().date(),
                Post.is_published == True,  # noqa: E712
            )
        )
        total = (
            await func.count()
            .select()
            .select_from(query.alias())
            .gino.scalar()
        )

        return total > 0
