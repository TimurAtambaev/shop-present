"""Модуль для работы с отзывами."""
from typing import Union

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from fastapi_pagination import Page, Params
from fastapi_pagination.bases import AbstractPage
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter

from dataset.core.container import Container
from dataset.rest.models.review import ResponseReviewModel
from dataset.rest.views.base import BaseView
from dataset.services.review import ReviewService

router = InferringRouter()


@cbv(router)
class ReviewView(BaseView):
    """Представление для работы с отзывами."""

    @router.get("/reviews", response_model=Page[ResponseReviewModel])
    @inject
    async def get_reviews(
        self,
        params: Params = Depends(),  # noqa B008
        review_service: ReviewService = Depends(  # noqa: B008
            Provide[Container.review_service]
        ),
    ) -> Union[AbstractPage, dict]:
        """Получение списка отзывов для лендинга."""
        return await review_service.get_reviews(
            params, self.request["language"], True
        )
