"""Сервис для управления отзывами."""
from typing import Optional, Union

from asyncpg import StringDataRightTruncationError
from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.gino import paginate
from gino import GinoException
from loguru import logger

from dataset.tables.review import Review


class CreateReviewError(Exception):
    """Ошибка создания отзыва в БД."""


class UpdateReviewError(Exception):
    """Ошибка обновления отзыва в БД."""


class ReviewService:
    """Сервис для управления отзывами."""

    async def get_reviews(
        self,
        params: Params,
        lang: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Union[AbstractPage, dict]:
        """Получить список отзывов из БД."""
        query = (
            Review.query.where(Review.lang == lang) if lang else Review.query
        )
        if is_active:
            query = query.where(Review.is_active == True)  # noqa E712
        return await paginate(query.order_by(Review.sort), params)

    async def create_review(self, review: dict) -> Review:
        """Создать отзыв в БД."""
        try:
            return await Review.create(**review)
        except (GinoException, StringDataRightTruncationError) as exc:
            logger.error(exc)
            raise CreateReviewError from exc

    async def update_review(self, review_id: int, review: dict) -> Review:
        """Обновить отзыв в БД."""
        try:
            return (
                await Review.update.values(**review)
                .where(Review.id == review_id)
                .returning(*Review.__table__.columns)
                .gino.first()
            )
        except (GinoException, StringDataRightTruncationError) as exc:
            logger.error(exc)
            raise UpdateReviewError from exc
